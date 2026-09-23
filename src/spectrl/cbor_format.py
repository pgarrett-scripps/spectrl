"""V3 whole-document payload compression with a CRC-32 checksum.

The five parts are identifier, version, payload mode, base64url payload, and
checksum. Array blobs remain independently encoded inside the CBOR document.
"""

from __future__ import annotations

import binascii
import dataclasses
import math
import re

import cbor2
import numpy as np

from ._format import (
    CHECKSUM_HEX_CHARS,
    MAX_ARRAY_LENGTH,
    MAX_CBOR_DEPTH,
    MAX_CBOR_ITEMS,
    MAX_SAFE_INTEGER,
    MAX_TOKEN_BYTES,
)
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
    DESC_DATA,
    DESC_NAME,
    DESC_TYPE,
    DESC_UNIT,
    build_header_dict,
    parse_header_dict,
)
from .limits import DecodeLimits, resolve_limits
from .model import ArrayEncoding, DecodedSpectrum, InlineSpectrum
from .peaks import _validate_arrays, build_array_blobs, canonical_sort
from .token import FORMAT_VERSION, MAGIC, b64url_decode, b64url_encode


def _canonical(doc: dict) -> bytes:
    """Deterministic (canonical) CBOR encoding of the header document."""
    return cbor2.dumps(_canonical_numbers(doc), canonical=True)


def _canonical_numbers(value):
    """Use one wire representation for equal safe numeric metadata values.

    JavaScript has one Number type. Normalize integral floats (including signed
    zero) to integers, but leave numeric array byte strings and map keys alone.
    """
    if isinstance(value, float) and abs(value) <= MAX_SAFE_INTEGER and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_numbers(item) for item in value]
    return value


def token_checksum(body: str) -> str:
    """CRC-32/ISO-HDLC of the ASCII token body as eight lowercase hex digits."""
    return f"{binascii.crc32(body.encode('ascii')) & 0xFFFFFFFF:0{CHECKSUM_HEX_CHARS}x}"


def frame_payload(raw: bytes, compression: str = "zlib") -> str:
    """Frame the selected payload encoding, defaulting to zlib."""
    from .payload import compress_payload

    mode, payload = compress_payload(raw, compression, MAX_TOKEN_BYTES)
    body = f"{MAGIC}.{mode}.{b64url_encode(payload)}"
    return f"{body}.{token_checksum(body)}"


def _without_user_params(spec):
    import copy

    result = copy.deepcopy(spec)
    removed = 0

    def visit(value):
        nonlocal removed
        if dataclasses.is_dataclass(value):
            for field in dataclasses.fields(value):
                if field.name == "user_params":
                    removed += len(getattr(value, field.name))
                    setattr(value, field.name, [])
                elif field.name == "array_user_params":
                    removed += sum(len(x) for x in getattr(value, field.name).values())
                    setattr(value, field.name, {})
                elif field.name not in {"extensions", "array_extensions"}:
                    visit(getattr(value, field.name))
        elif isinstance(value, dict):
            if "user_params" in value:
                removed += len(value["user_params"])
                del value["user_params"]
            for key, child in value.items():
                if key not in {"parameters", "extensions", "array_extensions"}:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(result)
    if removed:
        result.processing.append(
            {"operation": "spectrl:metadata-omission", "revision": 1, "parameters": {"userParamsRemoved": removed}}
        )
    return result


def encode_cbor(
    spec: InlineSpectrum,
    *,
    lossless: bool = False,
    drop_user_params: bool = False,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
    compression: str = "zlib",
) -> str:
    """Encode an InlineSpectrum to a spectrl.v3 (CBOR) token string."""
    _validate_arrays(spec)
    if drop_user_params:
        spec = _without_user_params(spec)
    spec = canonical_sort(spec)

    blobs, descriptors = build_array_blobs(
        spec,
        lossless=lossless,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=allow_unsafe_lossy_custom,
        compression=compression,
    )
    # Embed each numerically encoded blob as a CBOR byte string.
    for desc, blob in zip(descriptors, blobs, strict=True):
        desc[DESC_DATA] = blob

    doc = build_header_dict(spec, descriptors)
    raw = _canonical(doc)
    validate_cbor_document(raw)
    token = frame_payload(raw, compression)
    # Verify what we just produced against the wire ceilings only: a caller
    # encoding a legitimately huge spectrum is not the untrusted-input case the
    # default budgets exist for.
    read_token_document(token, limits=DecodeLimits.unlimited())
    return token


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

    start = pos
    ib = buf[pos]
    mt, ai = ib >> 5, ib & 0x1F
    arg, pos = _read_arg(buf, pos + 1, ai)
    if mt in (0, 1):
        if arg + (mt == 1) > MAX_SAFE_INTEGER:
            raise ValueError("CBOR integer exceeds the safe integer range")
        return pos
    if mt in (2, 3):
        end = pos + arg
        if end > len(buf):
            raise ValueError("truncated CBOR string")
        if mt == 3:
            buf[pos:end].decode("utf-8", errors="strict")
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
            if pos >= len(buf) or buf[pos] >> 5 not in (0, 1, 3):
                raise ValueError("CBOR map keys must be integers or text")
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
        raise ValueError("CBOR tags are not supported")
    if mt == 7:
        if ai not in (20, 21, 22, 25, 26, 27):
            raise ValueError("unsupported CBOR simple value")
        if ai in (25, 26, 27):
            value = cbor2.loads(buf[start:pos])
            if not math.isfinite(value):
                raise ValueError("CBOR numbers must be finite")
            # Section 1 requires writers to encode every mathematically integral
            # safe value as a CBOR integer, both signs of zero included. Enforcing
            # that on read keeps one wire form per value, so `3` and `3.0` cannot
            # both spell the same document, and leaves JavaScript readers -- which
            # cannot tell the two apart after parsing -- nothing to disagree about.
            if value.is_integer() and abs(value) <= MAX_SAFE_INTEGER:
                raise ValueError("integral values within the safe integer range must be CBOR integers")
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
    for key in doc:
        if not _is_wire_int(key) or key not in range(13):
            raise SpectrlDecodeError(f"unsupported spectrl header key: {key!r}")
    if 0 not in doc:
        raise SpectrlDecodeError("spectrl header is missing defaultArrayLength (key 0)")
    expected = {
        1: str,
        2: list,
        3: dict,
        4: list,
        5: list,
        6: list,
        7: list,
        8: dict,
        9: dict,
        10: list,
        11: dict,
        12: dict,
    }
    for key, cls in expected.items():
        if key in doc and not isinstance(doc[key], cls):
            raise SpectrlDecodeError(f"spectrl header key {key} must be {cls.__name__}")


def _validate_descriptor(desc: object, seen_arrays: set[tuple[int, str | None]]) -> None:
    if not isinstance(desc, dict):
        raise SpectrlDecodeError("array descriptor must be a map")
    from .context import decode_record, validate_extensions
    from .cv import TYPE_FLOAT32, TYPE_INT32
    from .header import _decode_param_map, _decode_user_params, _require_list
    from .pipeline import ENCODINGS, descriptor, operation

    if any(type(key) is not int or key not in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11) for key in desc):
        raise SpectrlDecodeError("unsupported array descriptor key")
    for key in (0, 1, 2, 5, 7):
        if key not in desc:
            raise SpectrlDecodeError(f"array descriptor is missing required key {key}")
    type_tail, array_tail = desc[0], desc[1]
    if type(type_tail) is not int or type_tail not in (TYPE_FLOAT64, TYPE_FLOAT32, TYPE_INT32):
        raise SpectrlDecodeError("unsupported array data type")
    if type(array_tail) is not int or not 0 <= array_tail <= 9999999:
        raise SpectrlDecodeError("invalid array accession")
    if type(desc[7]) is not int or desc[7] not in (0, 1):
        raise SpectrlDecodeError("invalid fidelity declaration")
    try:
        for key, registry in ((2, ENCODINGS),):
            d = descriptor(desc[key])
            if d != desc[key]:
                raise ValueError("noncanonical operation descriptor")
            if tuple(d[:2]) in registry:
                impl, _ = operation(registry, d)
                if key == 2 and (type_tail not in impl.types or desc[7] != (0 if impl.lossless else 1)):
                    raise ValueError("encoding dtype or fidelity declaration mismatch")
        if 8 in desc:
            params = _decode_param_map(desc[8])
            representation = {
                1000519,
                1000521,
                1000522,
                1000523,
                1000576,
                1000574,
                *range(1002312, 1002315),
                *range(1002746, 1002749),
                *range(1003780, 1003786),
                array_tail,
            }
            if any(
                p.accession.startswith("MS:") and p.accession[3:].isdigit() and int(p.accession[3:]) in representation
                for p in params
            ):
                raise ValueError("array scientific parameters conflict with representation declarations")
        if 9 in desc:
            _decode_user_params(desc[9])
        if 10 in desc:
            for step in _require_list(desc[10], "array processing"):
                decode_record(step, "processing")
        if 11 in desc:
            validate_extensions(desc[11], require_supported=False)
    except (TypeError, ValueError) as exc:
        raise SpectrlDecodeError(str(exc)) from exc
    if not isinstance(desc[5], bytes):
        raise SpectrlDecodeError("array descriptor data must be a byte string")
    name = desc.get(DESC_NAME)
    if DESC_NAME in desc and (not isinstance(name, str) or not name):
        raise SpectrlDecodeError("array name must be a non-empty string")
    if array_tail == ARRAY_NON_STANDARD:
        if not isinstance(name, str) or not name or name in {"mz", "intensity", "charge"}:
            raise SpectrlDecodeError("a non-standard array requires a non-empty name")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+", name):
            raise SpectrlDecodeError("non-standard array name must not be a CV accession")
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
    identity = (array_tail, name if array_tail == ARRAY_NON_STANDARD else None)
    if identity in seen_arrays:
        raise SpectrlDecodeError(f"duplicate array descriptor {identity!r}")
    seen_arrays.add(identity)


def read_token_payload(token: str, *, limits: DecodeLimits | None = None) -> bytes:
    """Verify framing and return bounded, decompressed CBOR bytes.

    Raises SpectrlDecodeError (a ValueError subclass) on any malformed,
    corrupted, or unsupported input.
    """
    limits = resolve_limits(limits)
    if not isinstance(token, str):
        raise SpectrlDecodeError("a spectrl token must be a string")
    if len(token) > limits.max_token_bytes:
        raise SpectrlDecodeError("token exceeds max_token_bytes")
    if len(token) > (MAX_TOKEN_BYTES * 4 + 2) // 3 + len(MAGIC) + 12:
        raise SpectrlDecodeError("spectrl token exceeds the payload size limit")
    if not token.isascii():
        raise SpectrlDecodeError("a spectrl token must contain only ASCII characters")

    magic = MAGIC
    prefix = f"{magic}."
    if not token.startswith(prefix):
        raise SpectrlDecodeError(f"Not a {magic} token: {token[:16]!r}")
    parts = token[len(prefix) :].split(".")
    if len(parts) != 3:
        raise SpectrlDecodeError("a spectrl token has exactly five '.'-separated parts")
    mode, payload, stored = parts
    if mode not in ("r", "z", "b"):
        raise SpectrlDecodeError(f"unsupported payload mode: {mode!r}")
    if not re.fullmatch(r"[0-9a-f]{8}", stored):
        raise SpectrlDecodeError("spectrl token checksum must be eight lowercase hexadecimal characters")
    expected = token_checksum(f"{magic}.{mode}.{payload}")
    if expected != stored:
        raise SpectrlDecodeError(
            f"spectrl token checksum mismatch: stored={stored!r}, computed={expected!r}. Token may be corrupted."
        )

    raw = b64url_decode(payload)
    if len(raw) > MAX_TOKEN_BYTES:
        raise SpectrlDecodeError(f"encoded payload exceeds {MAX_TOKEN_BYTES} bytes")
    if mode != "r":
        try:
            from .payload import decompress_payload

            raw = decompress_payload(raw, mode, MAX_TOKEN_BYTES)
        except Exception as exc:
            raise SpectrlDecodeError(f"invalid compressed CBOR payload: {exc}") from exc
    return raw


def read_token_document(token: str, *, limits: DecodeLimits | None = None) -> tuple[dict, DecodedSpectrum]:
    """Read the CBOR document after framing and bounded payload decompression."""
    limits = resolve_limits(limits)
    raw = read_token_payload(token, limits=limits)
    try:
        validate_cbor_document(raw)
        doc = cbor2.loads(raw)
    except Exception as e:
        raise SpectrlDecodeError(f"spectrl payload is not valid CBOR: {e}") from e
    if not isinstance(doc, dict):
        raise SpectrlDecodeError("spectrl payload is not a CBOR map.")
    _validate_header_shape(doc)

    try:
        from .context import validate_extensions

        validate_extensions(doc.get(11, {}), require_supported=False)
        decoded = parse_header_dict(doc)
        n = decoded.default_array_length
    except SpectrlDecodeError:
        raise
    except Exception as e:
        raise SpectrlDecodeError(f"malformed spectrl header: {e}") from e

    if not _is_wire_int(n) or n < 0 or n > MAX_ARRAY_LENGTH:
        raise SpectrlDecodeError(f"invalid declared array length (key 0): {n!r}")
    if n > limits.max_peaks:
        raise SpectrlDecodeError("declared peak count exceeds max_peaks")

    decoded.checksum = token.rsplit(".", 1)[1]
    decoded.format_version = FORMAT_VERSION

    descriptors = doc.get(6, [])
    if not isinstance(descriptors, list):
        raise SpectrlDecodeError("binaryDataArrayList (key 6) must be an array")
    if len(descriptors) > limits.max_arrays:
        raise SpectrlDecodeError("array count exceeds max_arrays")
    seen_arrays: set[tuple[int, str | None]] = set()
    decoded_bytes = 0
    for desc in descriptors:
        _validate_descriptor(desc, seen_arrays)
        decoded_bytes += n * (8 if desc[DESC_TYPE] == TYPE_FLOAT64 else 4)
        if decoded_bytes > limits.max_decoded_bytes:
            raise SpectrlDecodeError("decoded array bytes exceed max_decoded_bytes")

    return doc, decoded


def decode_cbor(token: str, *, limits: DecodeLimits | None = None) -> DecodedSpectrum:
    """Decode a token after shared framing and metadata validation."""
    doc, decoded = read_token_document(token, limits=limits)
    n = decoded.default_array_length
    from .context import validate_extensions
    from .pipeline import decode_pipeline

    try:
        validate_extensions(decoded.extensions)
    except ValueError as exc:
        raise SpectrlDecodeError(str(exc)) from exc
    descriptors = doc.get(6, [])

    # Bound numeric decoding by the declared array length.

    for desc in descriptors:
        try:
            validate_extensions(desc.get(11, {}))
            type_tail = desc[0]
            arr = decode_pipeline(desc[5], type_tail, n, desc[2], desc[7])
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
        if name is not None:
            decoded.array_names[unit_key] = name
        from .context import decode_record
        from .header import _decode_param_map, _decode_user_params

        if 8 in desc:
            decoded.array_params[unit_key] = _decode_param_map(desc[8])
        if 9 in desc:
            decoded.array_user_params[unit_key] = _decode_user_params(desc[9])
        if 10 in desc:
            decoded.array_processing[unit_key] = [decode_record(x, "processing") for x in desc[10]]
        if 11 in desc:
            decoded.array_extensions[unit_key] = desc[11]
        if desc[7] == 1:
            history = decoded.array_processing.setdefault(unit_key, [])
            history.append({"operation": "spectrl:lossy-encoding", "revision": 1, "parameters": {"encoding": desc[2]}})

    return decoded
