"""Shared quantized words, independent byte examples, and numeric bounds."""

import numpy as np
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, encoding_plan
from spectrl.cbor_format import read_token_payload
from spectrl.codecs import quantized


@pytest.mark.parametrize("width", [1, 2, 4, 8])
@pytest.mark.parametrize("delta", [False, True])
@pytest.mark.parametrize("log", [False, True])
def test_quantized_words_reconstruct_within_declared_bound(width, delta, log):
    params = {"scale": 10, "width": width, "delta": delta, "log": log}
    values = np.array([0, 0.001, 1.234, 2.567, 1.2])
    blob = quantized.encode(values, 1000523, params)
    result = quantized.decode(blob, 1000523, len(values), params)
    bound = (values + 1) * np.expm1(0.05) if log else 0.05
    assert np.all(np.abs(result - values) <= bound)
    assert len(blob) == width * len(values)


def test_hand_calculated_words():
    p = {"scale": 2, "width": 1, "delta": True}
    assert quantized.encode(np.array([1, 2, 2.5]), 1000523, p) == bytes.fromhex("020201")
    p = {"scale": 1, "width": 2}
    assert quantized.encode(np.array([256, 513]), 1000523, p) == bytes.fromhex("00010102")


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"scale": 0, "width": 1},
        {"scale": True, "width": 1},
        {"scale": 1, "width": True},
        {"scale": 1, "width": 3},
        {"scale": 1, "width": 1, "delta": 1},
        {"scale": float("inf"), "width": 1},
    ],
)
def test_invalid_parameters(params):
    with pytest.raises(ValueError):
        quantized.validate(params)


def test_domains_counts_and_large_integer_words():
    p = {"scale": 1, "width": 8, "delta": True}
    source = np.array([2**32 + 1, 2**53 - 1, 0], dtype=float)
    assert np.array_equal(quantized.decode(quantized.encode(source, 1000523, p), 1000523, 3, p), source)
    for source in ([2**53], [-1], [float("inf")]):
        with pytest.raises(ValueError):
            quantized.encode(np.array(source), 1000523, p)
    with pytest.raises(ValueError, match="byte count"):
        quantized.decode(b"", 1000523, 1, p)
    with pytest.raises(ValueError, match="safe integer"):
        quantized.decode(b"\xff" * 8, 1000523, 1, p)


def test_default_uses_only_core_encodings_and_omits_inner_compression():
    import cbor2

    spec = InlineSpectrum(
        3, mz=[100.123456, 200.1, 300.1], intensity=[1e-6, 1000, 1e12], charge=np.array([1, 2, 3], dtype=np.int32)
    )
    token = encode_spectrum(spec)
    doc = cbor2.loads(read_token_payload(token))
    # Twelve rounded mantissa bits beat the refined log grid on this span.
    assert [d[2][0] for d in doc[6]] == [3, 4, 0]
    assert all(3 not in d for d in doc[6])
    assert doc[6][1][2][2] == {"bits": 12, "width": 4}
    # The smallest intensity is below 1, so the log candidate's grid is refined to keep it.
    assert quantized.intensity_parameters(spec.intensity)["scale"] > 3600
    decoded = decode_token(token)
    assert doc[6][0][2][2]["log"] is True
    assert np.all(np.abs(decoded.mz - spec.mz) <= spec.mz * 1e-7)
    assert np.all(np.abs(decoded.intensity - spec.intensity) <= spec.intensity * 2.0**-13)
    assert decoded.charge.dtype == np.int32


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_default_mz_checks_pointwise_ppm_across_masses(dtype):
    source = np.concatenate(([0, 0, 0.001234567], np.geomspace(1, 1e6, 1000))).astype(dtype)
    spec = InlineSpectrum(len(source), mz=source)
    decoded = decode_token(encode_spectrum(spec, max_len=None))
    assert np.all(np.abs(decoded.mz - source.astype(np.float64)) <= source.astype(np.float64) * 1e-7)
    assert np.array_equal(decoded.mz[:2], [0, 0])
    assert np.all(np.diff(decoded.mz) >= 0)
    if dtype is np.float32:
        # Exact float32 words are smaller than the float64 ppm grid, so the default keeps them.
        assert encoding_plan(spec)[0]["encoding"] == [2, 1]
        np.testing.assert_array_equal(decoded.mz, source)
    else:
        # High masses can use their relative allowance instead of the old absolute cap.
        assert encoding_plan(spec)[0]["encoding"][0] == 3
        assert np.max(np.abs(decoded.mz - source)) > 5e-6


@pytest.mark.parametrize("source", [[], [0, 0], [0, 1e-300, 100], [0, np.nextafter(0.0, 1.0), 100]])
def test_default_mz_preserves_zero_and_unsupported_domains(source):
    spec = InlineSpectrum(len(source), mz=np.array(source, dtype=np.float64))
    decoded = decode_token(encode_spectrum(spec))
    np.testing.assert_array_equal(decoded.mz, spec.mz)


def test_explicit_linear_mz_grid_remains_available():
    source = np.array([100.123456, 500.234567, 1000.345678])
    spec = InlineSpectrum(len(source), mz=source)
    decoded = decode_token(
        encode_spectrum(
            spec,
            array_encodings={
                "mz": {"encoding": [3, 1, {"scale": 100000, "width": 4, "delta": True}]},
            },
        )
    )
    assert np.all(np.abs(decoded.mz - source) <= 5e-6)


@pytest.mark.parametrize("ppm", [0, -1, True, float("nan"), float("inf")])
def test_ppm_parameters_reject_invalid_error_bounds(ppm):
    with pytest.raises(ValueError, match="ppm"):
        quantized.ppm_parameters(np.array([100.0]), ppm)


def test_default_intensity_scale_refines_below_one():
    assert quantized.intensity_parameters(np.array([1.0, 3.0, 1.0e5]))["scale"] == 3600
    assert quantized.intensity_parameters(np.zeros(3))["scale"] == 3600
    assert quantized.intensity_parameters(np.array([0.5, 2.0]))["scale"] == 5400
    normalized = np.array([0.0, 1.0e-6, 5.0e-5, 0.25, 1.0])
    params = quantized.intensity_parameters(normalized)
    recovered = quantized.decode(quantized.encode(normalized, 1000521, params), 1000521, 5, params)
    assert recovered[0] == 0
    assert np.all(np.abs(recovered - normalized) <= normalized * 2 * np.expm1(0.5 / 3600))


def test_default_intensity_drops_the_log_candidate_when_its_scale_is_unbounded():
    with pytest.raises(ValueError, match="outside the supported range"):
        quantized.intensity_parameters(np.array([1.0e-300, 1.0]))
    spec = InlineSpectrum(2, mz=[100.0, 200.0], intensity=[1.0e-300, 1.0])
    # The rounded candidate keeps a strict relative bound at any normal magnitude.
    assert encoding_plan(spec)[1]["encoding"][0] in (1, 4)
    decoded = decode_token(encode_spectrum(spec)).intensity
    assert np.all(np.abs(decoded - spec.intensity) <= spec.intensity * 2.0**-13)


def test_default_lossy_token_keeps_small_normalized_peaks():
    intensity = np.array([1.0e-5, 0.3, 1.0])
    spec = InlineSpectrum(3, mz=[100.0, 200.0, 300.0], intensity=intensity)
    decoded = decode_token(encode_spectrum(spec)).intensity
    assert np.all(np.abs(decoded - intensity) <= intensity * 2 * np.expm1(0.5 / 3600))
