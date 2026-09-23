"""Encoding 4: rounded floating-point words, checked against plain integer arithmetic."""

import numpy as np
import pytest

from spectrl.codecs import rounded
from spectrl.pipeline import decode_pipeline, encode_pipeline

F32, F64 = 1000521, 1000523
FORMATS = {F32: (np.float32, 23, 4), F64: (np.float64, 52, 8)}


def _reference_word(value, tail, bits):
    """(u + 2**(d-1)) >> d on an unbounded Python int."""
    dtype, mantissa, size = FORMATS[tail]
    u = int(np.array([value], dtype=dtype).view(f"<u{size}")[0])
    d = mantissa - bits
    return u if d == 0 else (u + (1 << (d - 1))) >> d


def _values(tail, n=400, seed=4):
    dtype = FORMATS[tail][0]
    rng = np.random.default_rng(seed)
    finfo = np.finfo(dtype)
    a = (rng.lognormal(0, 12, n) * rng.choice([-1, 1], n)).astype(dtype)
    a = a[np.isfinite(a)]
    edge = [0.0, -0.0, finfo.tiny, -finfo.tiny, finfo.smallest_subnormal, finfo.tiny / 3, 1.0, 1.5, -2.75]
    return np.concatenate([a, np.array(edge, dtype=dtype)])


@pytest.mark.parametrize("tail", [F32, F64])
@pytest.mark.parametrize("bits", [0, 1, 7, 12, 20, 23, 40, 52])
def test_words_match_integer_reference_and_bound(tail, bits):
    dtype, mantissa, size = FORMATS[tail]
    if bits > mantissa:
        pytest.skip("bits exceed the type")
    source = _values(tail)
    source = source[np.isfinite(source)]
    words = rounded.words(source, tail, bits)
    expected = [_reference_word(v, tail, bits) for v in source]
    assert [int(w) for w in words] == expected
    d = mantissa - bits
    params = rounded.parameters(source[:50], tail, bits)
    blob = rounded.encode(source[:50], tail, params)
    out = rounded.decode(blob, tail, 50, params)
    assert out.dtype == dtype
    x = source[:50].astype(np.float64)
    y = out.astype(np.float64)
    normal = np.abs(x) >= np.finfo(dtype).tiny
    assert np.all(np.abs(y - x)[normal] <= np.abs(x[normal]) * 2.0 ** -(bits + 1))
    subnormal_bound = 2.0 ** (d - 1) * float(np.finfo(dtype).smallest_subnormal) if d else 0.0
    assert np.all(np.abs(y - x)[~normal] <= subnormal_bound)
    assert np.array_equal(np.signbit(y), np.signbit(x))


@pytest.mark.parametrize("tail", [F32, F64])
def test_all_mantissa_bits_is_bit_exact(tail):
    dtype, mantissa, _ = FORMATS[tail]
    source = _values(tail)
    params = rounded.parameters(source, tail, mantissa)
    out = rounded.decode(rounded.encode(source, tail, params), tail, len(source), params)
    assert out.tobytes() == source.tobytes()


def test_carry_ties_away_from_zero_and_signed_zero():
    below_two = np.nextafter(2.0, 0.0)
    out = rounded.decode(
        rounded.encode(np.array([below_two, -below_two]), F64, {"bits": 12, "width": 4}),
        F64,
        2,
        {"bits": 12, "width": 4},
    )
    assert out.tolist() == [2.0, -2.0]
    # 1 + 2**-13 sits exactly halfway between 1 and 1 + 2**-12; the magnitude rounds up.
    tie = np.array([1 + 2.0**-13, -(1 + 2.0**-13)])
    params = {"bits": 12, "width": 4}
    assert rounded.decode(rounded.encode(tie, F64, params), F64, 2, params).tolist() == [1 + 2.0**-12, -(1 + 2.0**-12)]
    zeros = np.array([0.0, -0.0], dtype=np.float32)
    out = rounded.decode(rounded.encode(zeros, F32, {"bits": 0, "width": 2}), F32, 2, {"bits": 0, "width": 2})
    assert out.tobytes() == zeros.tobytes()


@pytest.mark.parametrize(
    "tail,bits,values,width",
    [
        (F32, 0, [0.0, 1.0], 1),  # 0x3F800000 rounded at 23 bits is 127
        (F32, 0, [-1.0], 2),  # sign bit makes 383
        (F32, 12, [1.0], 4),
        (F64, 0, [1.0], 2),  # 1023
        (F64, 20, [1.0], 4),
        (F64, 12, [1.0], 4),  # 1023 << 12 < 2**32
        (F64, 30, [1.0], 8),
    ],
)
def test_minimal_width(tail, bits, values, width):
    assert rounded.parameters(np.array(values), tail, bits) == {"bits": bits, "width": width}
    ref = max(_reference_word(v, tail, bits) for v in values)
    assert ref < 2 ** (8 * width) and (width == 1 or ref >= 2 ** (4 * width))


def test_each_width_round_trips():
    for tail, bits, width, values in [
        (F32, 0, 1, [0.0, 2.0**-60]),
        (F32, 0, 2, [1.0, -1.0, 1e38]),
        (F32, 12, 4, [1.5, -7.25e-3]),
        (F64, 0, 2, [1.0, -1e300]),
        (F64, 12, 4, [123.456, -0.0]),
        (F64, 52, 8, [np.pi, -np.e]),
    ]:
        source = np.array(values, dtype=FORMATS[tail][0])
        params = {"bits": bits, "width": width}
        blob, fidelity = encode_pipeline(source, tail, [4, 1, params])
        assert fidelity == 1 and len(blob) == width * len(values)
        out = decode_pipeline(blob, tail, len(values), [4, 1, params], 1)
        assert out.dtype == source.dtype


def test_writer_rejects_nonfinite_rounding_and_overwide_words():
    top = np.array([np.finfo(np.float32).max], dtype=np.float32)
    with pytest.raises(ValueError, match="not finite"):
        rounded.encode(top, F32, {"bits": 0, "width": 2})
    with pytest.raises(ValueError, match="word width"):
        rounded.encode(np.array([1.0]), F64, {"bits": 12, "width": 2})
    with pytest.raises(ValueError, match="finite values"):
        rounded.encode(np.array([np.inf]), F64, {"bits": 12, "width": 4})


@pytest.mark.parametrize(
    "params,tail,blob,count,message",
    [
        ({"bits": 12, "width": 4}, F64, (1 << 24).to_bytes(4, "little"), 1, "declared type"),
        ({"bits": 0, "width": 2}, F32, (1 << 9).to_bytes(2, "little"), 1, "declared type"),
        ({"bits": 12, "width": 8}, F32, bytes(8), 1, "width exceeds"),
        ({"bits": 24, "width": 4}, F32, bytes(4), 1, "bits exceed"),
        ({"bits": 12, "width": 4}, F64, bytes(5), 1, "byte count"),
        ({"bits": 0, "width": 2}, F32, (0xFF).to_bytes(2, "little"), 1, "not finite"),
        ({"bits": 12, "width": 4}, 1000519, bytes(4), 1, "float32 or float64"),
    ],
)
def test_decoder_rejections(params, tail, blob, count, message):
    with pytest.raises(ValueError, match=message):
        rounded.decode(blob, tail, count, params)


@pytest.mark.parametrize(
    "params",
    [
        {"bits": 12},
        {"width": 4},
        {"bits": 12, "width": 4, "log": True},
        {"bits": -1, "width": 4},
        {"bits": 53, "width": 8},
        {"bits": 1.0, "width": 4},
        {"bits": True, "width": 4},
        {"bits": 12, "width": 3},
    ],
)
def test_invalid_parameters(params):
    with pytest.raises(ValueError):
        rounded.validate(params)


def test_pipeline_rejects_int32_declared_type():
    with pytest.raises(ValueError):
        encode_pipeline(np.array([1], dtype=np.int32), 1000519, [4, 1, {"bits": 12, "width": 4}])
    with pytest.raises(ValueError):
        decode_pipeline(bytes(4), 1000519, 1, [4, 1, {"bits": 12, "width": 4}], 1)
