"""Every encoding reconstructs the array's declared type, lossy ones included."""

import zlib

import numpy as np
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, encoding_plan
from spectrl.codecs import quantized
from spectrl.peaks import _default_candidates
from spectrl.pipeline import decode_pipeline, encode_pipeline

F32, F64, I32 = 1000521, 1000523, 1000519
TAILS = {np.float32: F32, np.float64: F64}
EXPLICIT = {
    "raw": 0,
    "byte-shuffle": 1,
    "modular-delta-shuffle": 2,
    "quantized-linear": [3, 1, {"scale": 1000, "width": 4, "delta": True}],
    "quantized-log": [3, 1, {"scale": 3600, "width": 2, "log": True}],
    "rounded-float": [4, 1, {"bits": 12, "width": 4}],
}


def _mz(dtype, n=64, seed=3):
    return np.sort(np.random.default_rng(seed).uniform(150, 1800, n)).astype(dtype)


def _counts(dtype, n=64, seed=4):
    return np.random.default_rng(seed).integers(0, 5000, n).astype(dtype)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("name", list(EXPLICIT))
def test_every_explicit_encoding_decodes_to_the_source_dtype(dtype, name):
    mz, intensity = _mz(dtype), np.random.default_rng(5).lognormal(3, 3, 64).astype(dtype)
    spec = InlineSpectrum(64, mz=mz, intensity=intensity)
    encodings = {"mz": EXPLICIT[name], "intensity": EXPLICIT[name]}
    decoded = decode_token(encode_spectrum(spec, array_encodings=encodings))
    assert [p["type_accession"] for p in encoding_plan(spec, array_encodings=encodings)[:2]] == [
        f"MS:{TAILS[dtype]}"
    ] * 2
    assert decoded.mz.dtype == dtype
    assert decoded.intensity.dtype == dtype


@pytest.mark.parametrize("name", ["raw", "byte-shuffle", "modular-delta-shuffle"])
def test_int32_arrays_keep_int32_under_exact_encodings(name):
    spec = InlineSpectrum(3, mz=np.array([1.0, 2.0, 3.0]), extra_arrays={"flags": np.array([3, 1, 2], dtype=np.int32)})
    decoded = decode_token(encode_spectrum(spec, array_encodings={"flags": EXPLICIT[name]}))
    assert decoded.extra_arrays["flags"].dtype == np.int32


@pytest.mark.parametrize("name", ["quantized-linear", "rounded-float"])
def test_lossy_encodings_declare_float64_for_int32_arrays(name):
    spec = InlineSpectrum(3, mz=np.array([1.0, 2.0, 3.0]), extra_arrays={"flags": np.array([3, 1, 2], dtype=np.int32)})
    token = encode_spectrum(spec, array_encodings={"flags": EXPLICIT[name]}, allow_unsafe_lossy_custom=True)
    assert decode_token(token).extra_arrays["flags"].dtype == np.float64


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize(("key", "array"), [("mz", _mz), ("intensity", _counts)])
def test_every_default_candidate_declares_and_decodes_the_native_type(dtype, key, array):
    source = array(dtype)
    candidates = list(_default_candidates(key, source, False, 0.1, 3600))
    assert len(candidates) == (2 if key == "mz" else 4)
    built = 0
    for tail, make in candidates:
        assert tail == TAILS[dtype]
        try:
            enc = make()
        except ValueError:
            # Only the float32 ppm candidate fails its checked bound here.
            assert (key, dtype) == ("mz", np.float32)
            continue
        blob, fidelity = encode_pipeline(source, tail, enc)
        assert decode_pipeline(blob, tail, len(source), enc, fidelity).dtype == dtype
        built += 1
    assert built == len(candidates) - ((key, dtype) == ("mz", np.float32))


@pytest.mark.parametrize(
    "params",
    [
        {"scale": 1000, "width": 4},
        {"scale": 7.25, "width": 2, "delta": True},
        {"scale": 3600, "width": 2, "log": True},
        {"scale": 5_000_000, "width": 4, "log": True, "delta": True},
    ],
)
def test_float32_decode_rounds_the_binary64_reconstruction_to_nearest_even(params):
    source = np.sort(np.random.default_rng(6).uniform(0, 1800, 500))
    blob = quantized.encode(source, F64, params)
    wide = quantized.decode(blob, F64, len(source), params)
    narrow = quantized.decode(blob, F32, len(source), params)
    assert narrow.dtype == np.float32
    np.testing.assert_array_equal(narrow.view(np.uint32), wide.astype(np.float32).view(np.uint32))


def test_float32_reconstruction_that_overflows_is_rejected():
    params = {"scale": 1, "width": 1, "log": True}
    assert quantized.decode(bytes([100]), F64, 1, params)[0] > np.finfo(np.float32).max
    with pytest.raises(ValueError, match="finite"):
        quantized.decode(bytes([100]), F32, 1, params)


def test_explicit_float32_grid_accounts_for_the_final_rounding():
    # A fine log grid leaves some values within half a float32 ulp of the grid
    # bound. The writer check must allow that final rounding, not reject it.
    source = np.random.default_rng(8).uniform(1, 2000, 20000).astype(np.float32)
    params = quantized.parameters(source, 100000, log=True)
    blob, _ = encode_pipeline(source, F32, [3, 1, params])
    decoded = decode_pipeline(blob, F32, len(source), [3, 1, params], 1).astype(np.float64)
    x = source.astype(np.float64)
    grid = (x + 1) * np.expm1(0.5 / 100000)
    assert np.any(np.abs(decoded - x) > grid)
    assert np.all(np.abs(decoded - x) <= grid + np.maximum(decoded * 2.0**-24, 2.0**-150))


def test_float32_ppm_candidate_fails_its_bound_and_exact_wins():
    # The token-parity input of the same name. Under zlib the float64-declared
    # grid would be smaller than the exact words, but its float32 values miss
    # 0.1 ppm, so the check fails and the exact encoding is kept.
    mz = np.sort(np.random.default_rng(7).uniform(150, 1800, 24)).astype(np.float32)
    grid = quantized.ppm_parameters(mz, 0.1, F64)
    with pytest.raises(ValueError, match="ppm bound"):
        quantized.ppm_parameters(mz, 0.1, F32)
    wide = encode_pipeline(mz, F64, [3, 1, grid])[0]
    exact = encode_pipeline(mz, F32, [2, 1])[0]
    assert len(zlib.compress(wide, 6)) < len(zlib.compress(exact, 6))
    spec = InlineSpectrum(len(mz), mz=mz)
    assert encoding_plan(spec, compression="zlib")[0]["encoding"] == [2, 1]
    np.testing.assert_array_equal(decode_token(encode_spectrum(spec)).mz, mz)


def test_float32_ppm_candidate_when_it_passes_decodes_within_bound():
    # Whether the float32 rounding stays within 0.1 ppm depends on the values.
    mz = np.array([100.5, 200.25, 300.125], dtype=np.float32)
    params = quantized.ppm_parameters(mz, 0.1, F32)
    blob, _ = encode_pipeline(mz, F32, [3, 1, params])
    decoded = decode_pipeline(blob, F32, len(mz), [3, 1, params], 1)
    assert decoded.dtype == np.float32
    assert np.all(np.abs(decoded.astype(np.float64) - mz) <= mz.astype(np.float64) * 1e-7)


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_log_intensity_candidate_checks_its_relative_bound_in_the_declared_type(dtype):
    source = np.random.default_rng(9).lognormal(3, 4, 5000).astype(dtype)
    params = quantized.intensity_parameters(source, 3600, TAILS[dtype])
    blob, _ = encode_pipeline(source, TAILS[dtype], [3, 1, params])
    decoded = decode_pipeline(blob, TAILS[dtype], len(source), [3, 1, params], 1)
    assert decoded.dtype == dtype
    x = source.astype(np.float64)
    assert np.all(np.abs(decoded.astype(np.float64) - x) <= x * 2 * np.expm1(0.5 / 3600))


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
@pytest.mark.parametrize("compression", ["raw", "zlib"])
def test_default_lossy_profile_preserves_dtypes(dtype, compression):
    spec = InlineSpectrum(
        64, mz=_mz(dtype), intensity=_counts(dtype), charge=np.random.default_rng(1).integers(1, 4, 64).astype(np.int32)
    )
    decoded = decode_token(encode_spectrum(spec, compression=compression))
    assert (decoded.mz.dtype, decoded.intensity.dtype, decoded.charge.dtype) == (dtype, dtype, np.int32)
