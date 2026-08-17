"""spectrl.v1 token format: a single CBOR document plus a CRC-32 checksum.

A token is ``spectrl.v1.<base64url(cbor)>.<checksum>``: one CBOR document
(RFC 8949) holding the integer-keyed header map *and* each array's compressed
blob inline as a CBOR byte string (descriptor key ``"d"``), encoded
deterministically (cbor2 canonical, RFC 8949 §4.2). The required fourth part is
CRC-32/ISO-HDLC over the ASCII text before the checksum, encoded as eight
lowercase hexadecimal characters. No CBOR parsing is needed to verify it.
"""

from __future__ import annotations

import binascii
import dataclasses
import re
import struct

import cbor2
import numpy as np

from ._format import (
    CHECKSUM_HEX_CHARS,
    MAX_ARRAY_LENGTH,
    MAX_BLOB_BYTES,
    MAX_CBOR_DEPTH,
    MAX_CBOR_ITEMS,
    MAX_SAFE_INTEGER,
    MAX_TOKEN_BYTES,
)
from .codecs import get_codec
from .codecs._zlibutil import bounded_decompress
from .cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ARRAY_NON_STANDARD,
    TYPE_FLOAT64,
    decode_tail,
    decode_unit_tail,
)
from .errors import SpectrlDecodeError
from .header import (
    DESC_ARRAY,
    DESC_COMP,
    DESC_DATA,
    DESC_FP,
    DESC_NAME,
    DESC_TYPE,
    DESC_UNIT,
    build_header_dict,
    parse_header_dict,
)
from .model import ArrayEncoding, DecodedSpectrum, InlineSpectrum
from .peaks import _validate_arrays, build_array_blobs, canonical_sort
from .proforma import validate_interp
from .token import MAGIC, b64url_decode, b64url_encode


def _canonical(doc: dict) -> bytes:
    """Deterministic (canonical) CBOR encoding of the header document."""
    return cbor2.dumps(doc, canonical=True)


def token_checksum(body: str) -> str:
    """CRC-32/ISO-HDLC of the ASCII token body as eight lowercase hex digits."""
    return f"{binascii.crc32(body.encode('ascii')) & 0xFFFFFFFF:0{CHECKSUM_HEX_CHARS}x}"


def _without_user_params(spec: InlineSpectrum) -> InlineSpectrum:
    """Drop free-text user params at spectrum and scan level.

    Header key 8 and scan-map key 2 are OPTIONAL and omitted when empty, so the
    result is a conforming token that simply carries no vendor free-text.
    """
    if not spec.user_params and not any(s.user_params for s in spec.scans):
        return spec
    scans = [dataclasses.replace(s, user_params=[]) if s.user_params else s for s in spec.scans]
    return dataclasses.replace(spec, user_params=[], scans=scans)


def encode_cbor(
    spec: InlineSpectrum,
    *,
    lossless: bool = False,
    drop_user_params: bool = False,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
) -> str:
    """Encode an InlineSpectrum to a spectrl.v1 (CBOR) token string."""
    _validate_arrays(spec)
    if drop_user_params:
        spec = _without_user_params(spec)
    spec = canonical_sort(spec)
    if spec.interp is not None:
        validate_interp(spec.interp)

    blobs, descriptors = build_array_blobs(
        spec,
        lossless=lossless,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=allow_unsafe_lossy_custom,
    )
    # Embed each compressed blob inline as a CBOR byte string; there are no
    # separate token segments, so there is no `seg` index.
    for desc, blob in zip(descriptors, blobs, strict=True):
        desc[DESC_DATA] = blob

    doc = build_header_dict(spec, descriptors)
    body = f"{MAGIC}.{b64url_encode(_canonical(doc))}"
    return f"{body}.{token_checksum(body)}"


# Hard ceiling on any single array blob's decompressed size (bytes); the
# per-token bound derived from the declared array length is usually far smaller.


def _read_arg(buf: bytes, pos: int, ai: int) -> tuple[int, int]:
    if ai < 24:
        return ai, pos
    widths = {24: 1, 25: 2, 26: 4, 27: 8}
    if ai not in widths:
        raise ValueError("indefinite-length and reserved CBOR items are not supported")
    width = widths[ai]
    end = pos + width
    if end > len(buf):
        raise ValueError("truncated CBOR length")
    return int.from_bytes(buf[pos:end], "big"), end


def _validate_cbor_item(buf: bytes, pos: int, depth: int, budget: list[int]) -> int:
    """Validate one definite-length CBOR item and return its end position.

    This raw pass runs before cbor2 so duplicate map keys and trailing bytes are
    observable instead of being silently collapsed or ignored by the library.
    """
    if depth > MAX_CBOR_DEPTH:
        raise ValueError(f"CBOR nesting exceeds {MAX_CBOR_DEPTH}")
    if pos >= len(buf):
        raise ValueError("truncated CBOR item")
    budget[0] += 1
    if budget[0] > MAX_CBOR_ITEMS:
        raise ValueError(f"CBOR item count exceeds {MAX_CBOR_ITEMS}")

    ib = buf[pos]
    mt, ai = ib >> 5, ib & 0x1F
    arg, pos = _read_arg(buf, pos + 1, ai)
    if mt in (0, 1):
        return pos
    if mt in (2, 3):
        end = pos + arg
        if end > len(buf):
            raise ValueError("truncated CBOR string")
        return end
    if mt == 4:
        if arg > MAX_CBOR_ITEMS:
            raise ValueError("CBOR array is too large")
        for _ in range(arg):
            pos = _validate_cbor_item(buf, pos, depth + 1, budget)
        return pos
    if mt == 5:
        if arg > MAX_CBOR_ITEMS:
            raise ValueError("CBOR map is too large")
        seen: set[tuple[type, str]] = set()
        for _ in range(arg):
            key_start = pos
            pos = _validate_cbor_item(buf, pos, depth + 1, budget)
            try:
                key = cbor2.loads(buf[key_start:pos])
                identity = (type(key), repr(key))
            except Exception as e:
                raise ValueError(f"invalid CBOR map key: {e}") from e
            if identity in seen:
                raise ValueError(f"duplicate CBOR map key {key!r}")
            seen.add(identity)
            pos = _validate_cbor_item(buf, pos, depth + 1, budget)
        return pos
    if mt == 6:
        return _validate_cbor_item(buf, pos, depth + 1, budget)
    if mt == 7:
        return pos
    raise ValueError(f"invalid CBOR major type {mt}")


def validate_cbor_document(raw: bytes) -> None:
    if len(raw) > MAX_TOKEN_BYTES:
        raise ValueError(f"CBOR payload exceeds {MAX_TOKEN_BYTES} bytes")
    end = _validate_cbor_item(raw, 0, 0, [0])
    if end != len(raw):
        raise ValueError("trailing bytes after the CBOR document")


def _is_wire_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_header_shape(doc: dict) -> None:
    if 0 not in doc:
        raise SpectrlDecodeError("spectrl header is missing defaultArrayLength (key 0)")
    expected = {
        1: str,
        2: dict,
        3: dict,
        4: list,
        5: list,
        6: list,
        7: str,
        8: list,
    }
    for key, cls in expected.items():
        if key in doc and not isinstance(doc[key], cls):
            raise SpectrlDecodeError(f"spectrl header key {key} must be {cls.__name__}")


def _validate_descriptor(desc: object, seen_arrays: set[tuple[int, str | None]]) -> None:
    if not isinstance(desc, dict):
        raise SpectrlDecodeError("array descriptor must be a map")
    for key in (DESC_TYPE, DESC_ARRAY, DESC_COMP, DESC_DATA):
        if key not in desc:
            raise SpectrlDecodeError(f"array descriptor is missing required key {key}")
    type_tail, array_tail, comp_tail = desc[DESC_TYPE], desc[DESC_ARRAY], desc[DESC_COMP]
    if not all(_is_wire_int(v) for v in (type_tail, array_tail, comp_tail)):
        raise SpectrlDecodeError("array descriptor type, array, and comp must be integers")
    from .cv import (
        COMP_BYTE_SHUFFLED_ZSTD,
        COMP_NUMLIN_ZLIB,
        COMP_NUMLIN_ZSTD,
        COMP_NUMPIC_ZLIB,
        COMP_NUMPIC_ZSTD,
        COMP_NUMSLOF_ZLIB,
        COMP_NUMSLOF_ZSTD,
        COMP_ZLIB,
        COMP_ZSTD,
        TYPE_FLOAT32,
        TYPE_INT32,
    )

    if type_tail not in (TYPE_FLOAT64, TYPE_FLOAT32, TYPE_INT32):
        raise SpectrlDecodeError(f"unsupported array data type {type_tail}")
    supported = {
        COMP_NUMLIN_ZLIB,
        COMP_NUMLIN_ZSTD,
        COMP_NUMSLOF_ZLIB,
        COMP_NUMSLOF_ZSTD,
        COMP_NUMPIC_ZLIB,
        COMP_NUMPIC_ZSTD,
        COMP_ZLIB,
        COMP_ZSTD,
        COMP_BYTE_SHUFFLED_ZSTD,
    }
    if comp_tail not in supported:
        raise SpectrlDecodeError(f"unsupported compression codec {comp_tail}")
    raw_codecs = {COMP_ZLIB, COMP_ZSTD, COMP_BYTE_SHUFFLED_ZSTD}
    if comp_tail not in raw_codecs and type_tail != TYPE_FLOAT64:
        raise SpectrlDecodeError("Numpress descriptors must declare float64")
    fp_codecs = {COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD}
    if DESC_FP in desc and (not _is_wire_int(desc[DESC_FP]) or desc[DESC_FP] <= 0 or desc[DESC_FP] > MAX_SAFE_INTEGER):
        raise SpectrlDecodeError("array descriptor fp must be a positive integer")
    if comp_tail in fp_codecs and DESC_FP not in desc:
        raise SpectrlDecodeError("Numpress linear and slof descriptors require fp")
    if comp_tail in {COMP_NUMPIC_ZLIB, COMP_NUMPIC_ZSTD, *raw_codecs} and DESC_FP in desc:
        raise SpectrlDecodeError("array descriptor fp is not valid for this codec")
    if not isinstance(desc[DESC_DATA], bytes):
        raise SpectrlDecodeError("array descriptor data must be a byte string")
    name = desc.get(DESC_NAME)
    if array_tail == ARRAY_NON_STANDARD:
        if not isinstance(name, str) or not name:
            raise SpectrlDecodeError("a non-standard array requires a non-empty name")
    elif name is not None:
        raise SpectrlDecodeError("a standard array descriptor must not carry a name")
    if DESC_UNIT in desc:
        try:
            raw_unit = desc[DESC_UNIT]
            valid = (
                (_is_wire_int(raw_unit) and raw_unit >= 0)
                or (isinstance(raw_unit, str) and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+", raw_unit)))
                or (
                    isinstance(raw_unit, list)
                    and len(raw_unit) == 2
                    and isinstance(raw_unit[0], str)
                    and bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", raw_unit[0]))
                    and _is_wire_int(raw_unit[1])
                    and raw_unit[1] >= 0
                )
            )
            if not valid:
                raise ValueError("bad unit form")
            decode_unit_tail(raw_unit)
        except (TypeError, ValueError) as exc:
            raise SpectrlDecodeError("array descriptor unit must be a valid CV unit accession") from exc
    identity = (array_tail, name)
    if identity in seen_arrays:
        raise SpectrlDecodeError(f"duplicate array descriptor {identity!r}")
    seen_arrays.add(identity)


def _validate_numpress_fp(desc: dict, max_bytes: int) -> None:
    from .codecs.zstd import bounded_zstd_decompress
    from .cv import COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD

    comp = desc[DESC_COMP]
    if comp not in (COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD):
        return
    raw = (
        bounded_decompress(desc[DESC_DATA], max_bytes)
        if comp in (COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB)
        else bounded_zstd_decompress(desc[DESC_DATA], max_bytes)
    )
    if len(raw) < 8:
        raise SpectrlDecodeError("Numpress stream is missing its fixed point")
    embedded = struct.unpack(">d", raw[:8])[0]
    declared = desc[DESC_FP]
    if not np.isfinite(embedded) or embedded <= 0 or embedded != declared:
        raise SpectrlDecodeError(
            f"Numpress fixed point mismatch: descriptor declares {declared!r}, stream contains {embedded!r}"
        )


def decode_cbor(token: str) -> DecodedSpectrum:
    """Decode a spectrl.v1 token, verifying the trailing CRC-32 checksum.

    Raises SpectrlDecodeError (a ValueError subclass) on any malformed,
    corrupted, or unsupported input.
    """
    if not isinstance(token, str):
        raise SpectrlDecodeError("a spectrl token must be a string")
    if not token.isascii():
        raise SpectrlDecodeError("a spectrl token must contain only ASCII characters")

    prefix = f"{MAGIC}."
    if not token.startswith(prefix):
        raise SpectrlDecodeError(f"Not a {MAGIC} token: {token[:16]!r}")
    parts = token[len(prefix) :].split(".")
    if len(parts) != 2:
        raise SpectrlDecodeError("a spectrl token has exactly four '.'-separated parts")
    payload, stored = parts
    if not re.fullmatch(r"[0-9a-f]{8}", stored):
        raise SpectrlDecodeError("spectrl token checksum must be eight lowercase hexadecimal characters")
    expected = token_checksum(f"{MAGIC}.{payload}")
    if expected != stored:
        raise SpectrlDecodeError(
            f"spectrl token checksum mismatch: stored={stored!r}, computed={expected!r}. Token may be corrupted."
        )

    raw = b64url_decode(payload)
    try:
        validate_cbor_document(raw)
        doc = cbor2.loads(raw)
    except Exception as e:
        raise SpectrlDecodeError(f"spectrl payload is not valid CBOR: {e}") from e
    if not isinstance(doc, dict):
        raise SpectrlDecodeError("spectrl payload is not a CBOR map.")
    _validate_header_shape(doc)

    try:
        decoded = parse_header_dict(doc)
        n = decoded.default_array_length
    except SpectrlDecodeError:
        raise
    except Exception as e:
        raise SpectrlDecodeError(f"malformed spectrl header: {e}") from e

    if not _is_wire_int(n) or n < 0 or n > MAX_ARRAY_LENGTH:
        raise SpectrlDecodeError(f"invalid declared array length (key 0): {n!r}")

    decoded.checksum = stored

    descriptors = doc.get(6, [])
    if not isinstance(descriptors, list):
        raise SpectrlDecodeError("binaryDataArrayList (key 6) must be an array")
    seen_arrays: set[tuple[int, str | None]] = set()
    for desc in descriptors:
        _validate_descriptor(desc, seen_arrays)

    # Bound decompression by the declared array length (float64 worst case plus
    # numpress framing slack) so a small token cannot expand without limit.
    max_bytes = min(64 + 16 * max(n, 0), MAX_BLOB_BYTES)

    for desc in descriptors:
        try:
            _validate_numpress_fp(desc, max_bytes)
            type_tail = desc.get(DESC_TYPE, TYPE_FLOAT64)
            arr = get_codec(desc[DESC_COMP]).decode(desc[DESC_DATA], type_tail, max_bytes)
            tail, name = desc[DESC_ARRAY], desc.get(DESC_NAME)
            unit = decode_unit_tail(desc[DESC_UNIT]) if DESC_UNIT in desc else None
        except SpectrlDecodeError:
            raise
        except Exception as e:
            raise SpectrlDecodeError(f"malformed array blob: {e}") from e
        if len(arr) != n:
            raise SpectrlDecodeError(
                f"array {desc.get(DESC_ARRAY)!r} decoded to {len(arr)} values, but the header declares {n} (key 0)."
            )
        if arr.dtype.kind == "f" and not bool(np.isfinite(arr).all()):
            raise SpectrlDecodeError(f"array {tail!r} contains NaN or infinite values")
        if tail == ARRAY_MZ and len(arr) and float(arr.min()) < 0:
            raise SpectrlDecodeError("m/z array contains negative values")
        if tail == ARRAY_MZ:
            decoded.mz = arr
            unit_key = "mz"
        elif tail == ARRAY_INTENSITY:
            decoded.intensity = arr
            unit_key = "intensity"
        elif tail == ARRAY_CHARGE:
            decoded.charge = arr
            unit_key = "charge"
        elif tail == ARRAY_NON_STANDARD:
            unit_key = name if name is not None else decode_tail(tail)
            decoded.extra_arrays[unit_key] = arr
        else:
            unit_key = decode_tail(tail)
            decoded.extra_arrays[unit_key] = arr
        if unit is not None:
            decoded.array_units[unit_key] = unit

    return decoded
