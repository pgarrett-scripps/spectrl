"""Deterministic boundary and randomized invariants beyond saved conformance vectors."""

import numpy as np
import pytest

from spectrl import (
    InlineSpectrum,
    decode_token,
    encode_spectrum,
    encoding_report,
    fit_to_budget,
    spectrum_from_dict,
    spectrum_to_dict,
    top_n,
)


@pytest.mark.parametrize("dtype", ["<f4", ">f4", "<f8", ">f8", "<i4", ">i4"])
@pytest.mark.parametrize("encoding", [0, 1, 2])
def test_auxiliary_endianness_preserves_width_bits_json_and_quality(dtype, encoding):
    kind = np.dtype(dtype).kind
    values = [-(2**31), 2**31 - 1, 0, 1] if kind == "i" else [-0.0, 0.0, 1.25, np.finfo(dtype).tiny]
    original = np.array(values, dtype=dtype)
    source = InlineSpectrum(4, mz=[4, 3, 2, 1], extra_arrays={"MS:1003008": original})
    options = {"lossless": True, "array_encodings": {"MS:1003008": encoding}}
    decoded = decode_token(encode_spectrum(source, **options))
    expected = original[::-1].astype(original.dtype.newbyteorder("="))
    actual = decoded.extra_arrays["MS:1003008"]
    assert actual.dtype == expected.dtype
    assert actual.tobytes() == expected.tobytes()
    assert encoding_report(source, **options)["all_arrays_exact"]
    restored = spectrum_from_dict(spectrum_to_dict(source))
    assert decode_token(encode_spectrum(restored, **options)).extra_arrays["MS:1003008"].tobytes() == expected.tobytes()
    assert original.tobytes() == np.array(values, dtype=dtype).tobytes()


@pytest.mark.parametrize("dtype", [np.int32, np.float32, np.float64])
def test_top_n_matches_python_ranking_at_boundaries_and_random_ties(dtype):
    rng = np.random.default_rng(20260919)
    for count in [1, 2, 7, 31]:
        values = rng.integers(-4, 5, count).astype(dtype)
        values[0] = -(2**31)
        if count > 1:
            values[-1] = 2**30
        mz = rng.integers(1, 5, count).astype(np.float64)
        source = InlineSpectrum(
            count, mz=mz, intensity=values, extra_arrays={"position": np.arange(count, dtype=np.int32)}
        )
        ranked = sorted(range(count), key=lambda i: (-float(values[i]), float(mz[i]), i))
        for n in range(count):
            expected = sorted(ranked[:n], key=lambda i: (float(mz[i]), i))
            selected = top_n(source, n)
            assert selected.extra_arrays["position"].tolist() == expected
            np.testing.assert_array_equal(selected.intensity, values[expected])
            assert selected.intensity.dtype == source.intensity.dtype
        np.testing.assert_array_equal(source.intensity, values)


def test_budget_trimming_does_not_select_minimum_int32_over_positive_peaks():
    values = np.arange(100, dtype=np.int32)
    values[0] = -(2**31)
    source = InlineSpectrum(100, mz=np.sort(np.random.default_rng(42).uniform(100, 1000, 100)), intensity=values)
    result = fit_to_budget(source, 500, lossless=True, allow_peak_trimming=True)
    assert 0 < result["kept_peaks"] < 100
    decoded = decode_token(result["token"])
    np.testing.assert_array_equal(decoded.intensity, values[-result["kept_peaks"] :])


@pytest.mark.parametrize("n", [0, 1, 10])
def test_selection_rejects_inconsistent_input_even_for_empty_or_noop_requests(n):
    with pytest.raises(ValueError, match="length"):
        top_n(InlineSpectrum(2, mz=[1, 2], intensity=[1]), n)


@pytest.mark.parametrize("compression", ["raw", "zlib"])
@pytest.mark.parametrize("encoding", [0, 1, 2])
def test_random_finite_bit_patterns_roundtrip_after_sorting(compression, encoding):
    rng = np.random.default_rng(7301)
    for code, unsigned in [("f4", "u4"), ("f8", "u8"), ("i4", "u4")]:
        bits = rng.integers(0, np.iinfo(unsigned).max, 128, dtype=unsigned)
        values = bits.view(code)
        values = values[np.isfinite(values)]
        count = len(values)
        mz = rng.integers(0, 9, count).astype(np.float64)
        original = InlineSpectrum(count, mz=mz, extra_arrays={"custom": values})
        restored = decode_token(
            encode_spectrum(original, lossless=True, compression=compression, array_encodings={"custom": encoding})
        )
        expected = values[np.argsort(mz, kind="stable")]
        assert restored.extra_arrays["custom"].dtype == values.dtype
        assert restored.extra_arrays["custom"].tobytes() == expected.tobytes()
