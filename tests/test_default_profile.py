"""Default lossy profile: per-array smallest-size choice among exact and bounded candidates."""

import zlib

import numpy as np
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, encoding_plan
from spectrl.peaks import _default_array, _default_candidates

F32, F64 = 1000521, 1000523
MZ = np.linspace(400, 1400, 64)


def _size(blob, compression):
    return len(blob) if compression == "raw" else len(zlib.compress(blob, 6))


def _intensity_plan(intensity, compression="zlib", mz=None):
    mz = MZ[: len(intensity)] if mz is None else mz
    spec = InlineSpectrum(len(intensity), mz=mz, intensity=intensity)
    return encoding_plan(spec, compression=compression)[1]


def test_integer_counts_choose_exact_scale_one_words():
    counts = np.array([0, 1, 2, 5, 18, 42, 91, 250, 1000, 3, 0, 7] * 4, dtype=np.float64)
    for compression in ("raw", "zlib"):
        plan = _intensity_plan(counts, compression)
        assert plan["encoding"] == [3, 1, {"scale": 1, "width": 2}]
        spec = InlineSpectrum(len(counts), mz=MZ[: len(counts)], intensity=counts)
        decoded = decode_token(encode_spectrum(spec, compression=compression))
        assert np.array_equal(decoded.intensity, counts)


def test_candidate_order_and_integer_gate():
    a = np.array([1.5, 2.0, 3.0])
    kinds = [make() for _, make in _default_candidates("intensity", a, False, 5.0, 3600.0)]
    assert [k[0] for k in kinds] == [1, 4, 3]
    assert kinds[1][2] == {"bits": 12, "width": 4} and kinds[2][2].get("log") is True
    counts = np.array([1.0, 2.0, 2.0**53 - 1])
    assert [make()[0] for _, make in _default_candidates("intensity", counts, False, 5.0, 3600.0)] == [1, 3, 4, 3]
    too_big = np.array([1.0, 2.0**53])
    assert [make()[0] for _, make in _default_candidates("intensity", too_big, False, 5.0, 3600.0)] == [1, 4, 3]
    assert [make()[0] for _, make in _default_candidates("mz", MZ, False, 5.0, 3600.0)] == [2, 3]
    assert len(list(_default_candidates("intensity", a, True, 5.0, 3600.0))) == 1
    assert len(list(_default_candidates("intensity", -a, False, 5.0, 3600.0))) == 1


def _tiny_minimum(seed=7, n=48):
    rng = np.random.default_rng(seed)
    a = rng.lognormal(5, 1.5, n).astype(np.float32)
    a[0] = np.float32(1.2e-38)
    a[3] = 0
    return a


@pytest.mark.parametrize("compression", ["raw", "zlib"])
def test_tiny_minimum_never_larger_than_lossless(compression):
    intensity = _tiny_minimum()
    spec = InlineSpectrum(len(intensity), mz=MZ[: len(intensity)], intensity=intensity)
    lossy = encode_spectrum(spec, compression=compression)
    exact = encode_spectrum(spec, compression=compression, lossless=True)
    dtype, enc, blob, _ = _default_array("intensity", intensity, False, 5.0, 3600.0, compression)
    assert _size(blob, compression) <= _size(intensity.astype("<f4").tobytes(), compression)
    assert len(lossy) <= len(exact) + 16  # descriptor parameters are the only possible overhead


def test_tie_keeps_the_earlier_exact_candidate():
    # float32 words at 12 bits need 4 bytes, the same as exact float32 bytes.
    intensity = _tiny_minimum()
    assert _intensity_plan(intensity, "raw")["encoding"] == [1, 1]


def test_raw_and_zlib_measure_differently():
    intensity = _tiny_minimum()
    assert _intensity_plan(intensity, "raw")["encoding"] == [1, 1]
    assert _intensity_plan(intensity, "zlib")["encoding"][0] == 4


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("compression", ["raw", "zlib"])
def test_default_never_exceeds_exact_candidate(seed, compression):
    from spectrl.pipeline import encode_pipeline

    rng = np.random.default_rng(seed)
    n = int(rng.integers(1, 200))
    kind = seed % 4
    if kind == 0:
        a = rng.lognormal(rng.uniform(0, 12), rng.uniform(0.1, 4), n)
    elif kind == 1:
        a = np.floor(rng.lognormal(3, 2, n))
    elif kind == 2:
        a = rng.lognormal(0, 30, n)
        a[rng.integers(0, n)] = 0
    else:
        a = rng.lognormal(4, 1, n).astype(np.float32)
    mz = np.sort(rng.uniform(100, 2000, n))
    for key, array, exact_enc in (("intensity", a, [1, 1]), ("mz", mz, [2, 1])):
        exact_type = F32 if array.dtype == np.float32 else F64
        exact = _size(encode_pipeline(array, exact_type, exact_enc)[0], compression)
        dtype, enc, blob, fidelity = _default_array(key, array, False, 5.0, 3600.0, compression)
        assert _size(blob, compression) <= exact
        assert fidelity in (0, 1) and (fidelity == 0) == (enc == exact_enc)
