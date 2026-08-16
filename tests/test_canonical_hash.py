"""Acceptance criterion 3: Determinism and hash verification."""

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


def test_hash_stored_in_token():
    token = encode_spectrum(_make_spec())
    decoded = decode_token(token)
    assert decoded.hash is not None
    assert len(decoded.hash) == 16  # 12 bytes → 16 base64url chars


def test_token_is_three_parts():
    """A spectrl2 token is magic + one base64url CBOR document + trailing hash."""
    token = encode_spectrum(_make_spec())
    parts = token.split(".")
    assert parts[0] == "spectrl2"
    assert len(parts) == 3
    assert len(parts[2]) == 16  # 12 bytes → 16 base64url chars


def test_hash_is_plain_sha256_of_prefix():
    """Any tool with sha256 can verify a token: hash the text before the last dot."""
    import base64
    import hashlib

    token = encode_spectrum(_make_spec())
    body, stored = token.rsplit(".", 1)
    digest = hashlib.sha256(body.encode("ascii")).digest()[:12]
    assert stored == base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def test_unhashed_token_decodes():
    """A two-part token simply carries no hash; decode succeeds with hash=None."""
    token = encode_spectrum(_make_spec())
    body = token.rsplit(".", 1)[0]
    decoded = decode_token(body)
    assert decoded.hash is None


def test_hash_verified_on_decode():
    """Tampering the payload causes ValueError on decode."""
    token = encode_spectrum(_make_spec())
    body, stored = token.rsplit(".", 1)
    # Perturb the tail of the CBOR payload; the stored hash no longer matches.
    tampered = body[:-3] + ("AAA" if body[-3:] != "AAA" else "BBB") + "." + stored
    with pytest.raises(ValueError, match="hash mismatch"):
        decode_token(tampered)


def test_hash_matches_re_encode():
    """Decoded hash equals hash from a fresh encode of same data."""
    spec = _make_spec()
    t1 = encode_spectrum(spec)
    decoded = decode_token(t1)
    t2 = encode_spectrum(spec)
    decoded2 = decode_token(t2)
    assert decoded.hash == decoded2.hash
