"""Public token and resolved-encoding inspection helpers."""

from __future__ import annotations

import cbor2

from .cbor_format import encode_cbor, token_checksum, validate_cbor_document
from .cv import decode_tail, decode_unit_tail
from .header import DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_FP, DESC_NAME, DESC_TYPE, DESC_UNIT
from .model import ArrayEncoding, InlineSpectrum
from .token import MAGIC, b64url_decode


def inspect_token(token: str) -> list[dict[str, object]]:
    """Return resolved metadata for every array in a verified token."""
    prefix = f"{MAGIC}."
    if not token.startswith(prefix):
        raise ValueError(f"Not a {MAGIC} token")
    payload, checksum = token[len(prefix) :].split(".")
    if token_checksum(f"{MAGIC}.{payload}") != checksum:
        raise ValueError("spectrl token checksum mismatch")
    raw = b64url_decode(payload)
    validate_cbor_document(raw)
    doc = cbor2.loads(raw)
    out: list[dict[str, object]] = []
    for desc in doc.get(6, []):
        tail = desc[DESC_ARRAY]
        item: dict[str, object] = {
            "accession": decode_tail(tail),
            "name": desc.get(DESC_NAME),
            "type_accession": decode_tail(desc[DESC_TYPE]),
            "compression_accession": decode_tail(desc[DESC_COMP]),
            "fixed_point": desc.get(DESC_FP),
            "compressed_bytes": len(desc.get(DESC_DATA, b"")),
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
) -> list[dict[str, object]]:
    """Resolve automatic codecs, fixed points, types, and units for a spectrum."""
    token = encode_cbor(
        spec,
        lossless=lossless,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=allow_unsafe_lossy_custom,
    )
    return inspect_token(token)
