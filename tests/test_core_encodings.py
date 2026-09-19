"""The four numeric encodings and the removed development interfaces."""

import numpy as np
import pytest

from spectrl import ArrayEncoding, InlineSpectrum, decode_token, encode_spectrum, encoding_plan
from spectrl.pipeline import ENCODINGS, decode_pipeline, encode_pipeline


@pytest.mark.parametrize("dtype,tail", [("float32", 1000521), ("float64", 1000523), ("int32", 1000519)])
@pytest.mark.parametrize("encoding", [0, 1, 2])
@pytest.mark.parametrize("n", [0, 1, 2, 31, 256])
def test_each_exact_encoding_preserves_native_bits(dtype, tail, encoding, n):
    rng = np.random.default_rng(901)
    a = rng.integers(-(2**31), 2**31, n, dtype=np.int32) if dtype == "int32" else rng.normal(size=n).astype(dtype)
    if dtype != "int32" and n >= 2:
        a[:2] = [-0.0, 0.0]
    blob, fidelity = encode_pipeline(a, tail, [encoding, 1])
    assert decode_pipeline(blob, tail, n, [encoding, 1], fidelity).tobytes() == a.tobytes()
    with pytest.raises(ValueError):
        decode_pipeline(blob + b"x", tail, n, [encoding, 1], fidelity)


def test_registry_and_fixed_default():
    assert {key for key in ENCODINGS if isinstance(key[0], int)} == {(i, 1) for i in range(4)}
    s = InlineSpectrum(2, mz=[100, 200], intensity=[1, 2], extra_arrays={"custom": [3.0, 4.0]})
    assert [p["encoding"] for p in encoding_plan(s, lossless=True)] == [[2, 1], [1, 1], [0, 1]]
    assert encoding_plan(s, lossless=True, array_encodings={"mz": ArrayEncoding("raw")})[0]["encoding"] == [0, 1]


@pytest.mark.parametrize(
    "option",
    [
        "numlin-zlib",
        "numpic-zstd",
        "numslof-zlib",
        "dictionary-zstd",
        "zlib",
        "MS:1002746",
        1002746,
        {"compression": "zlib"},
        {"encoding": 0, "compression": 0},
        {"codec": "raw"},
        {"fixed_point": 1000},
    ],
)
def test_removed_development_options_fail(option):
    with pytest.raises((ValueError, TypeError)):
        encode_spectrum(InlineSpectrum(1, mz=[1]), array_encodings={"mz": option})


def test_parameterized_quantization_and_custom_array_permission():
    s = InlineSpectrum(3, mz=[1.01, 2.04, 3.07], extra_arrays={"score": [1.01, 2.04, 3.07]})
    option = [3, 1, {"scale": 10, "width": 1}]
    d = decode_token(encode_spectrum(s, array_encodings={"mz": option}))
    assert np.max(np.abs(d.mz - s.mz)) <= 0.05
    with pytest.raises(ValueError, match="lossy"):
        encode_spectrum(s, lossless=True, array_encodings={"mz": option})
    with pytest.raises(ValueError, match="permission"):
        encode_spectrum(s, array_encodings={"score": option})
    d = decode_token(encode_spectrum(s, array_encodings={"score": option}, allow_unsafe_lossy_custom=True))
    assert np.max(np.abs(d.extra_arrays["score"] - s.extra_arrays["score"])) <= 0.05
