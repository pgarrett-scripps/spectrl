"""Acceptance criterion 3: Determinism and checksum verification."""

import binascii

import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum
from spectrl.model import InlineSpectrum


def _make_spec(seed=42, n=20):
    rng = np.random.default_rng(seed)
    mz = np.sort(rng.uniform(100.0, 1000.0, n))
    intensity = rng.uniform(1e3, 1e6, n)
    return InlineSpectrum(default_array_length=n, mz=mz, intensity=intensity, id="scan=1")


def test_deterministic_token():
    """Same input produces byte-identical token across calls."""
    spec = _make_spec()
    t1 = encode_spectrum(spec)
    t2 = encode_spectrum(spec)
    assert t1 == t2


def test_deterministic_unordered_input():
    """Input with peaks out of order produces same token as pre-sorted input."""
    spec = _make_spec(n=10)
    # Shuffle
    idx = np.array([5, 3, 9, 0, 7, 1, 8, 2, 6, 4])
    shuffled = InlineSpectrum(
        default_array_length=10,
        mz=spec.mz[idx],
        intensity=spec.intensity[idx],
        id=spec.id,
    )
    t_sorted = encode_spectrum(spec)
    t_shuffled = encode_spectrum(shuffled)
    assert t_sorted == t_shuffled


def test_checksum_stored_in_token():
    token = encode_spectrum(_make_spec())
    decoded = decode_token(token)
    assert len(decoded.checksum) == 8
    assert decoded.checksum == decoded.checksum.lower()


def test_token_is_four_parts():
    """A spectrl.v1 token is identifier + version + CBOR document + checksum."""
    token = encode_spectrum(_make_spec())
    parts = token.split(".")
    assert parts[:2] == ["spectrl", "v1"]
    assert len(parts) == 4
    assert len(parts[3]) == 8


def test_checksum_is_crc32_of_prefix():
    token = encode_spectrum(_make_spec())
    body, stored = token.rsplit(".", 1)
    assert stored == f"{binascii.crc32(body.encode('ascii')) & 0xFFFFFFFF:08x}"


def test_missing_checksum_is_rejected():
    token = encode_spectrum(_make_spec())
    body = token.rsplit(".", 1)[0]
    with pytest.raises(ValueError, match="exactly four"):
        decode_token(body)


def test_checksum_verified_on_decode():
    """Tampering the payload causes ValueError on decode."""
    token = encode_spectrum(_make_spec())
    body, stored = token.rsplit(".", 1)
    # Perturb the tail of the CBOR payload; the stored checksum no longer matches.
    tampered = body[:-3] + ("AAA" if body[-3:] != "AAA" else "BBB") + "." + stored
    with pytest.raises(ValueError, match="checksum mismatch"):
        decode_token(tampered)


def test_checksum_matches_re_encode():
    """Decoded checksum equals checksum from a fresh encode of same data."""
    spec = _make_spec()
    t1 = encode_spectrum(spec)
    decoded = decode_token(t1)
    t2 = encode_spectrum(spec)
    decoded2 = decode_token(t2)
    assert decoded.checksum == decoded2.checksum
