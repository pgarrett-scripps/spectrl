"""Edge cases: numpress array-size boundaries, ordering, value extremes, URL bindings."""

from __future__ import annotations

import numpy as np
import pytest

from spectrl import (
    decode_token,
    encode_spectrum,
    extract_token,
    to_data_uri,
    to_fragment,
    to_query,
    top_n,
)
from spectrl.model import InlineSpectrum


def _spec(mz, intensity, **kw) -> InlineSpectrum:
    mz = np.asarray(mz, dtype=float)
    return InlineSpectrum(default_array_length=len(mz), mz=mz, intensity=np.asarray(intensity, dtype=float), **kw)


# ── numpress array-size boundaries (linear: 0/1/2/n have distinct code paths) ──


@pytest.mark.parametrize("lossless", [False, True])
@pytest.mark.parametrize("n", [0, 1, 2, 3, 4, 50])
def test_peak_count_boundaries(n: int, lossless: bool):
    mz = np.linspace(100.0, 100.0 + n, n)
    intensity = np.full(n, 1.0e4)
    token = encode_spectrum(_spec(mz, intensity), lossless=lossless)
    d = decode_token(token)
    assert d.default_array_length == n
    if n == 0:
        assert d.mz is None or len(d.mz) == 0
    else:
        assert len(d.mz) == n
        np.testing.assert_allclose(d.mz, mz, atol=1e-3)


def test_metadata_only_spectrum():
    """A spectrum with no peak arrays still encodes/decodes (metadata-only)."""
    spec = InlineSpectrum(default_array_length=0)
    d = decode_token(encode_spectrum(spec))
    assert d.mz is None and d.intensity is None
    assert d.default_array_length == 0


# ── ordering / canonical form ─────────────────────────────────────────────────


def test_unsorted_input_is_canonicalised():
    spec = _spec([300.0, 100.0, 200.0], [3.0, 1.0, 2.0])
    d = decode_token(encode_spectrum(spec, lossless=True))
    np.testing.assert_array_equal(d.mz, [100.0, 200.0, 300.0])
    np.testing.assert_array_equal(d.intensity, [1.0, 2.0, 3.0])


def test_duplicate_mz_stable():
    spec = _spec([200.0, 100.0, 200.0, 100.0], [1.0, 2.0, 3.0, 4.0], charge=np.array([1.0, 2.0, 3.0, 4.0]))
    d = decode_token(encode_spectrum(spec, lossless=True))
    np.testing.assert_array_equal(d.mz, [100.0, 100.0, 200.0, 200.0])
    # stable sort preserves original relative order within equal keys
    np.testing.assert_array_equal(d.intensity, [2.0, 4.0, 1.0, 3.0])


def test_same_spectrum_same_token():
    a = encode_spectrum(_spec([100.0, 200.0], [1e4, 2e4]))
    b = encode_spectrum(_spec([200.0, 100.0], [2e4, 1e4]))  # unsorted, same content
    assert a == b


# ── value extremes ────────────────────────────────────────────────────────────


def test_large_intensities_slof_clamp():
    """Intensities beyond the default slof range still decode within tolerance."""
    intensity = np.array([1.0e8, 5.0e8, 9.9e8])
    spec = _spec([100.0, 200.0, 300.0], intensity)
    d = decode_token(encode_spectrum(spec))
    rel = np.abs(d.intensity - intensity) / intensity
    assert np.all(rel < 0.02), f"max rel error {rel.max()}"


def test_descriptor_fp_matches_blob_fp():
    """When the slof fp is clamped for large intensities, the descriptor must
    record the fp the blob actually uses, not the requested default."""
    import struct
    import zlib

    import cbor2

    from spectrl.cv import ARRAY_INTENSITY
    from spectrl.header import DESC_ARRAY, DESC_DATA, DESC_FP
    from spectrl.token import b64url_decode

    intensity = np.array([1.0e8, 5.0e8, 9.9e8])
    token = encode_spectrum(_spec([100.0, 200.0, 300.0], intensity))
    doc = cbor2.loads(b64url_decode(token.split(".")[1]))
    desc = next(d for d in doc[6] if d[DESC_ARRAY] == ARRAY_INTENSITY)
    blob_fp = struct.unpack(">d", zlib.decompress(desc[DESC_DATA])[:8])[0]
    assert desc[DESC_FP] == blob_fp
    # Whole number, carried as a CBOR integer rather than a float64.
    assert isinstance(desc[DESC_FP], int)


def test_descriptor_omits_fp_when_it_is_the_codec_default():
    """Absent fp means the codec's canonical default; only a clamp records one."""
    import cbor2

    from spectrl.header import DESC_FP
    from spectrl.token import b64url_decode

    token = encode_spectrum(_spec([100.0, 200.0, 300.0], np.array([1.0e3, 2.0e3, 3.0e3])))
    doc = cbor2.loads(b64url_decode(token.split(".")[1]))
    assert all(DESC_FP not in d for d in doc[6])


def test_clamped_fp_cannot_overflow_the_slof_uint16_range():
    """Flooring the clamped fp must round down, never up, or slof overflows."""
    import math

    from spectrl.codecs.numpress import _SLOF_UINT16_MAX, _safe_slof_fp

    for peak in (9.9e8, 1.0e9, 5.0e9, 1.0e12):
        data = np.array([1.0, peak])
        fp = _safe_slof_fp(data, 3600)
        assert isinstance(fp, int)
        assert math.log(peak + 1) * fp <= _SLOF_UINT16_MAX


def test_zero_intensity_roundtrips():
    spec = _spec([100.0, 200.0], [0.0, 1e4])
    d = decode_token(encode_spectrum(spec))
    assert abs(d.intensity[0]) < 1.0  # log(0+1)=0 → recovers ~0


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_nan_inf_rejected(bad: float):
    spec = _spec([100.0, 200.0], [1e4, bad])
    with pytest.raises(ValueError, match="NaN or Inf"):
        encode_spectrum(spec)


# ── top_n ──────────────────────────────────────────────────────────────────────


def test_top_n_keeps_most_intense_and_resorts():
    spec = _spec([100.0, 200.0, 300.0, 400.0], [5.0, 50.0, 10.0, 90.0])
    trimmed = top_n(spec, 2)
    assert trimmed.default_array_length == 2
    # keeps 90 (m/z 400) and 50 (m/z 200), re-sorted ascending by m/z
    np.testing.assert_array_equal(trimmed.mz, [200.0, 400.0])
    np.testing.assert_array_equal(trimmed.intensity, [50.0, 90.0])


# ── URL bindings ────────────────────────────────────────────────────────────────


def test_url_bindings_roundtrip():
    token = encode_spectrum(_spec([100.0, 200.0], [1e4, 2e4]))
    assert extract_token(to_fragment(token, "https://v.example/s")) == token
    assert extract_token(to_query(token, "https://v.example/s")) == token
    assert extract_token(to_data_uri(token)) == token


def test_extract_token_no_token_raises():
    with pytest.raises(ValueError):
        extract_token("https://example.com/nothing-here")
