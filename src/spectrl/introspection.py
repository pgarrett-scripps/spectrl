"""Public token and resolved-encoding inspection helpers."""

from __future__ import annotations

from .cbor_format import encode_cbor, read_token_document
from .cv import decode_tail, decode_unit_tail
from .header import DESC_ARRAY, DESC_DATA, DESC_NAME, DESC_TYPE, DESC_UNIT
from .limits import DecodeLimits
from .model import ArrayEncoding, InlineSpectrum
from .pipeline import ENCODINGS


def inspect_token(token: str, *, limits: DecodeLimits | None = None) -> list[dict[str, object]]:
    """Return resolved metadata for every array in a verified token."""
    doc, _ = read_token_document(token, limits=limits)
    out: list[dict[str, object]] = []
    for desc in doc.get(6, []):
        tail = desc[DESC_ARRAY]
        item: dict[str, object] = {
            "accession": decode_tail(tail),
            "name": desc.get(DESC_NAME),
            "type_accession": decode_tail(desc[DESC_TYPE]),
            "encoding": desc[2],
            "fidelity": "exact" if desc[7] == 0 else "lossy",
            "available": tuple(desc[2][:2]) in ENCODINGS,
            "encoded_bytes": len(desc.get(DESC_DATA, b"")),
        }
        if DESC_UNIT in desc:
            item["unit_accession"] = decode_unit_tail(desc[DESC_UNIT])
        out.append(item)
    return out


def encoding_plan(
    spec: InlineSpectrum,
    *,
    lossless: bool = False,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
    compression: str = "zlib",
) -> list[dict[str, object]]:
    """Resolve automatic codecs, fixed points, types, and units for a spectrum.

    The default profile's choice depends on the payload compression, so pass
    the same ``compression`` the token will use.
    """
    token = encode_cbor(
        spec,
        lossless=lossless,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=allow_unsafe_lossy_custom,
        compression=compression,
    )
    # A token this call just wrote is trusted; see encode_cbor's self-check.
    return inspect_token(token, limits=DecodeLimits.unlimited())
