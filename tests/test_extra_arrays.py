"""Auxiliary (extra) per-peak arrays: named CV arrays + non-standard MS:1000786."""

from __future__ import annotations

import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum, top_n
from spectrl.model import InlineSpectrum


def _spec(extra):
    return InlineSpectrum(
        default_array_length=4,
        mz=np.array([150.0, 300.0, 450.0, 600.0]),
        intensity=np.array([8.0e4, 5.0e4, 3.0e4, 1.0e4]),
        extra_arrays=extra,
    )


@pytest.mark.parametrize("lossless", [False, True])
def test_named_and_nonstandard_roundtrip(lossless):
    spec = _spec(
        {
            "MS:1000517": np.array([10.0, 20.0, 30.0, 40.0]),  # signal-to-noise (named CV)
            "iso_score": np.array([0.9, 0.8, 0.7, 0.6], dtype=np.float32),  # non-standard float32
            "flags": np.array([1, 0, 1, 0], dtype=np.int32),  # non-standard int32
        }
    )
    d = decode_token(encode_spectrum(spec, lossless=lossless))
    e = d.extra_arrays
    assert set(e) == {"MS:1000517", "iso_score", "flags"}
    assert e["MS:1000517"].dtype == np.float64 and np.allclose(e["MS:1000517"], [10, 20, 30, 40])
    assert e["iso_score"].dtype == np.float32 and np.allclose(e["iso_score"], [0.9, 0.8, 0.7, 0.6], atol=1e-6)
    assert e["flags"].dtype == np.int32 and list(e["flags"]) == [1, 0, 1, 0]


def test_multiple_non_standard_arrays_disambiguated_by_name():
    spec = _spec(
        {
            "score_a": np.array([1.0, 2.0, 3.0, 4.0]),
            "score_b": np.array([5.0, 6.0, 7.0, 8.0]),
        }
    )
    d = decode_token(encode_spectrum(spec))
    assert np.allclose(d.extra_arrays["score_a"], [1, 2, 3, 4])
    assert np.allclose(d.extra_arrays["score_b"], [5, 6, 7, 8])


def test_extra_arrays_permuted_by_canonical_sort():
    # m/z given out of order; the extra array must follow the same permutation.
    spec = InlineSpectrum(
        default_array_length=3,
        mz=np.array([300.0, 100.0, 200.0]),
        intensity=np.array([3.0, 1.0, 2.0]),
        extra_arrays={"snr": np.array([30.0, 10.0, 20.0])},
    )
    d = decode_token(encode_spectrum(spec))
    assert np.allclose(d.mz, [100, 200, 300])
    assert np.allclose(d.extra_arrays["snr"], [10, 20, 30])  # rode along with the sort


def test_top_n_trims_extra_arrays():
    spec = InlineSpectrum(
        default_array_length=4,
        mz=np.array([100.0, 200.0, 300.0, 400.0]),
        intensity=np.array([1.0, 9.0, 2.0, 8.0]),
        extra_arrays={"snr": np.array([11.0, 99.0, 22.0, 88.0])},
    )
    trimmed = top_n(spec, 2)  # keep the two most intense (idx 1 and 3)
    d = decode_token(encode_spectrum(trimmed))
    assert np.allclose(d.mz, [200, 400])
    assert np.allclose(d.extra_arrays["snr"], [99, 88])


def test_no_extra_arrays_is_empty():
    spec = InlineSpectrum(default_array_length=2, mz=np.array([1.0, 2.0]), intensity=np.array([3.0, 4.0]))
    d = decode_token(encode_spectrum(spec))
    assert d.extra_arrays == {}


def test_extra_float_nan_rejected():
    spec = _spec({"snr": np.array([1.0, np.nan, 3.0, 4.0])})
    with pytest.raises(ValueError, match="NaN or Inf"):
        encode_spectrum(spec)
