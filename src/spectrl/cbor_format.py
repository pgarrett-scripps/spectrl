"""spectrl2 token format: a single CBOR document plus a trailing hash.

A token is ``spectrl2.<base64url(cbor)>[.<hash>]``: one CBOR document
(RFC 8949) holding the integer-keyed header map *and* each array's compressed
blob inline as a CBOR byte string (descriptor key ``"d"``), encoded
deterministically (cbor2 canonical, RFC 8949 §4.2). The optional third part is
the integrity hash: truncated SHA-256 over the ASCII text of the first two
parts, verified on the received text. No CBOR parsing is needed to verify a
token, and the check is independent of the CBOR library that produced it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct

import cbor2
import numpy as np

from ._format import (
    HASH_BYTES,
    MAX_ARRAY_LENGTH,
    MAX_BLOB_BYTES,
    MAX_CBOR_DEPTH,
    MAX_CBOR_ITEMS,
    MAX_TOKEN_BYTES,
)
from .codecs import get_codec
from .codecs._zlibutil import bounded_decompress
from .codecs.numpress import DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP
from .cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ARRAY_NON_STANDARD,
    ION_MOBILITY_ARRAY_TAILS,
    TYPE_FLOAT64,
    decode_tail,
)
from .errors import SpectrlDecodeError
from .header import (
    DESC_ARRAY,
    DESC_COMP,
    DESC_DATA,
    DESC_FP,
    DESC_NAME,
    DESC_TYPE,
    build_header_dict,
    parse_header_dict,
)
from .model import DecodedSpectrum, InlineSpectrum
from .peaks import _validate_arrays, build_array_blobs, canonical_sort
from .proforma import validate_interp
from .token import MAGIC, b64url_decode, b64url_encode


def _canonical(doc: dict) -> bytes:
    """Deterministic (canonical) CBOR encoding of the header document."""
    return cbor2.dumps(doc, canonical=True)


def token_hash(body: str) -> str:
    """The integrity hash of a token body (``magic.payload``, no trailing dot).

    Truncated SHA-256 (first HASH_BYTES bytes) of the ASCII text,
    base64url-encoded. Defined over the text so any tool with sha256 can
    verify a token without decoding it.
    """
    return b64url_encode(hashlib.sha256(body.encode("ascii")).digest()[:HASH_BYTES])


def _without_user_params(spec: InlineSpectrum) -> InlineSpectrum:
    """Drop free-text user params at spectrum and scan level.

    Header key 8 and scan-map key 2 are OPTIONAL and omitted when empty, so the
    result is a conforming token that simply carries no vendor free-text.
    """
    if not spec.user_params and not any(s.user_params for s in spec.scans):
        return spec
    scans = [dataclasses.replace(s, user_params=[]) if s.user_params else s for s in spec.scans]
    return dataclasses.replace(spec, user_params=[], scans=scans)


def encode_cbor(spec: InlineSpectrum, *, lossless: bool = False, drop_user_params: bool = False) -> str:
    """Encode an InlineSpectrum to a spectrl2 (CBOR) token string."""
    _validate_arrays(spec)
    if drop_user_params:
        spec = _without_user_params(spec)
    spec = canonical_sort(spec)
    if spec.interp is not None:
        validate_interp(spec.interp)

    blobs, descriptors = build_array_blobs(spec, lossless=lossless)
    # Embed each compressed blob inline as a CBOR byte string; there are no
    # separate token segments, so there is no `seg` index.
    for desc, blob in zip(descriptors, blobs, strict=True):
        desc[DESC_DATA] = blob

    doc = build_header_dict(spec, descriptors)
    body = f"{MAGIC}.{b64url_encode(_canonical(doc))}"
    return f"{body}.{token_hash(body)}"


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
    from .cv import COMP_NUMLIN_ZLIB, COMP_NUMPIC_ZLIB, COMP_NUMSLOF_ZLIB, COMP_ZLIB, TYPE_FLOAT32, TYPE_INT32

    if type_tail not in (TYPE_FLOAT64, TYPE_FLOAT32, TYPE_INT32):
        raise SpectrlDecodeError(f"unsupported array data type {type_tail}")
    if comp_tail not in (COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB, COMP_NUMPIC_ZLIB, COMP_ZLIB):
        raise SpectrlDecodeError(f"unsupported compression codec {comp_tail}")
    if comp_tail != COMP_ZLIB and type_tail != TYPE_FLOAT64:
        raise SpectrlDecodeError("Numpress descriptors must declare float64")
    if DESC_FP in desc and not _is_wire_int(desc[DESC_FP]):
        raise SpectrlDecodeError("array descriptor fp must be an integer")
    if comp_tail in (COMP_NUMPIC_ZLIB, COMP_ZLIB) and DESC_FP in desc:
        raise SpectrlDecodeError("array descriptor fp is not valid for this codec")
    if not isinstance(desc[DESC_DATA], bytes):
        raise SpectrlDecodeError("array descriptor data must be a byte string")
    name = desc.get(DESC_NAME)
    if array_tail == ARRAY_NON_STANDARD:
        if not isinstance(name, str) or not name:
            raise SpectrlDecodeError("a non-standard array requires a non-empty name")
    elif name is not None:
        raise SpectrlDecodeError("a standard array descriptor must not carry a name")
    identity = (array_tail, name)
    if identity in seen_arrays:
        raise SpectrlDecodeError(f"duplicate array descriptor {identity!r}")
    seen_arrays.add(identity)


def _validate_numpress_fp(desc: dict, max_bytes: int) -> None:
    from .cv import COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB

    comp = desc[DESC_COMP]
    if comp not in (COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB):
        return
    raw = bounded_decompress(desc[DESC_DATA], max_bytes)
    if len(raw) < 8:
        raise SpectrlDecodeError("Numpress stream is missing its fixed point")
    embedded = struct.unpack(">d", raw[:8])[0]
    declared = desc.get(DESC_FP, DEFAULT_NUMLIN_FP if comp == COMP_NUMLIN_ZLIB else DEFAULT_NUMSLOF_FP)
    if not np.isfinite(embedded) or embedded <= 0 or embedded != declared:
        raise SpectrlDecodeError(
            f"Numpress fixed point mismatch: descriptor declares {declared!r}, stream contains {embedded!r}"
        )


def decode_cbor(token: str) -> DecodedSpectrum:
    """Decode a spectrl2 token, verifying the trailing integrity hash if present.

    Raises SpectrlDecodeError (a ValueError subclass) on any malformed,
    corrupted, or unsupported input.
    """
    if not isinstance(token, str):
        raise SpectrlDecodeError("a spectrl token must be a string")
    if not token.isascii():
        raise SpectrlDecodeError("a spectrl token must contain only ASCII characters")

    parts = token.split(".")
    if parts[0] != MAGIC:
        raise SpectrlDecodeError(f"Not a {MAGIC} token: {token[:16]!r}")
    if len(parts) == 2:
        payload, stored = parts[1], None
    elif len(parts) == 3:
        payload, stored = parts[1], parts[2]
    else:
        raise SpectrlDecodeError("a spectrl token has two or three '.'-separated parts")

    if stored is not None:
        # Verify over the received text of the first two parts, exactly as they
        # arrived: no decoding is involved, so the check is independent of the
        # CBOR library (and of base64) on both sides.
        expected = token_hash(f"{parts[0]}.{payload}")
        if expected != stored:
            raise SpectrlDecodeError(
                f"spectrl token hash mismatch: stored={stored!r}, computed={expected!r}. Token may be corrupted."
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

    decoded.hash = stored

    descriptors = doc.get(6, [])
    if not isinstance(descriptors, list):
        raise SpectrlDecodeError("binaryDataArrayList (key 6) must be an array")
    seen_arrays: set[tuple[int, str | None]] = set()
    for desc in descriptors:
        _validate_descriptor(desc, seen_arrays)

    # Bound decompression by the declared array length (float64 worst case plus
    # numpress framing slack) so a small token cannot expand without limit.
    max_bytes = min(64 + 16 * max(n, 0), MAX_BLOB_BYTES)

    im_tails = set(ION_MOBILITY_ARRAY_TAILS.values())
    for desc in descriptors:
        try:
            _validate_numpress_fp(desc, max_bytes)
            type_tail = desc.get(DESC_TYPE, TYPE_FLOAT64)
            arr = get_codec(desc[DESC_COMP]).decode(desc[DESC_DATA], type_tail, max_bytes)
            tail, name = desc[DESC_ARRAY], desc.get(DESC_NAME)
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
        elif tail == ARRAY_INTENSITY:
            decoded.intensity = arr
        elif tail == ARRAY_CHARGE:
            decoded.charge = arr
        elif tail in im_tails:
            decoded.ion_mobility = arr
            decoded.ion_mobility_type = decode_tail(tail)
        elif tail == ARRAY_NON_STANDARD:
            decoded.extra_arrays[name if name is not None else decode_tail(tail)] = arr
        else:
            decoded.extra_arrays[decode_tail(tail)] = arr

    return decoded
