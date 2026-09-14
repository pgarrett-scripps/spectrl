"""Explicit read-only compatibility for the published spectrl.v1 format."""

from dataclasses import dataclass

from .cbor_format import decode_cbor, read_token_document
from .model import DecodedSpectrum


@dataclass(frozen=True)
class LegacySpectrum:
    """A v1 spectrum and its optional legacy ProForma interpretation."""

    spectrum: DecodedSpectrum
    interpretation: str | None


def decode_v1_token(token: str) -> LegacySpectrum:
    """Decode v1 explicitly without moving its interpretation into the v2 model."""
    doc, _ = read_token_document(token, _legacy=True)
    return LegacySpectrum(decode_cbor(token, _legacy=True), doc.get(7))
