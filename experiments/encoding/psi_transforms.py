"""Experimental reproductions of PSI transforms missing from spectrl's registry.

Dictionary layout follows mzdata-bindata encodings.rs and the mzd writeup.
Floating predictors follow biospi/pwiz mzMLb IO.cpp, with explicit rounding.
These are benchmark helpers, not new public spectrl codecs.
"""

import struct

import numpy as np


def shuffle(raw, width, inverse=False):
    if width not in (1, 2, 4, 8) or len(raw) % width:
        raise ValueError("invalid word width or byte length")
    data = np.frombuffer(raw, dtype=np.uint8)
    shape = (width, -1) if inverse else (-1, width)
    return data.reshape(shape).T.copy().tobytes()


def index_width(count):
    # Maintained mzdata encoder and decoder use <= 2**bits, allowing index zero.
    for width in (1, 2, 4, 8):
        if count <= 1 << (8 * width):
            return width
    raise ValueError("dictionary too large")


def dictionary_encode(raw, width):
    if width not in (4, 8) or len(raw) % width:
        raise ValueError("invalid numeric representation")
    if not raw:
        return b""
    words = np.frombuffer(raw, dtype=f"<u{width}")
    values, indices = np.unique(words, return_inverse=True)
    count = len(values)
    iw = index_width(count)
    header = struct.pack("<QQ", 16 + count * width, count)
    return (
        header
        + shuffle(values.astype(f"<u{width}").tobytes(), width)
        + shuffle(indices.astype(f"<u{iw}").tobytes(), iw)
    )


def dictionary_decode(blob, width):
    if width not in (4, 8):
        raise ValueError("invalid word width")
    if not blob:
        return b""
    if len(blob) < 16:
        raise ValueError("truncated dictionary header")
    offset, count = struct.unpack("<QQ", blob[:16])
    if not count or offset != 16 + count * width or offset > len(blob):
        raise ValueError("invalid dictionary dimensions")
    values = np.frombuffer(shuffle(blob[16:offset], width, inverse=True), dtype=f"<u{width}")
    iw = index_width(count)
    indices = np.frombuffer(shuffle(blob[offset:], iw, inverse=True), dtype=f"<u{iw}")
    if len(indices) and int(indices.max()) >= count:
        raise ValueError("dictionary index out of range")
    return values[indices].astype(f"<u{width}").tobytes()


def mzmlb_encode(values, predictor, truncate_bits):
    result = values.copy()
    width = result.dtype.itemsize
    mantissa = 23 if width == 4 else 52
    if not 0 <= truncate_bits <= mantissa:
        raise ValueError("invalid mantissa truncation")
    words = result.view(f"<u{width}")
    words &= ((1 << (width * 8)) - 1) ^ ((1 << truncate_bits) - 1)
    if predictor == "none":
        return result
    if predictor == "delta" and len(result):
        previous = result[0]
        for i in range(1, len(result)):
            result[i] = result[0] + result[i] - previous
            previous = result[i] + previous - result[0]
    elif predictor == "linear" and len(result) > 1:
        previous2, previous1 = result[0], result[1]
        two = result.dtype.type(2)
        for i in range(2, len(result)):
            result[i] = result[1] + result[i] - two * previous1 + previous2
            old_previous1 = previous1
            previous1 = result[i] + two * previous1 - previous2 - result[1]
            previous2 = old_previous1
    elif predictor not in ("delta", "linear"):
        raise ValueError("unknown predictor")
    return result


def mzmlb_decode(values, predictor):
    result = values.copy()
    two = result.dtype.type(2)
    for i in range(2, len(result)):
        if predictor == "delta":
            result[i] = result[i] + result[i - 1] - result[0]
        elif predictor == "linear":
            result[i] = result[i] + two * result[i - 1] - result[i - 2] - result[1]
    return result


def self_check():
    """Check dictionary bytes against a separate scalar implementation."""
    rng = np.random.default_rng(20260917)
    for width in (4, 8):
        for count in (0, 1, 2, 254, 255, 256, 257, 65535, 65536, 65537):
            words = np.arange(count, dtype=f"<u{width}")
            rng.shuffle(words)
            raw = words.tobytes()
            encoded = dictionary_encode(raw, width)
            assert dictionary_decode(encoded, width) == raw
            if count:
                sorted_words = sorted({int(word) for word in words})
                mapping = {word: i for i, word in enumerate(sorted_words)}
                iw = index_width(count)
                value_bytes = [word.to_bytes(width, "little") for word in sorted_words]
                index_bytes = [mapping[int(word)].to_bytes(iw, "little") for word in words]
                scalar = struct.pack("<QQ", 16 + width * count, count)
                scalar += bytes(word[b] for b in range(width) for word in value_bytes)
                scalar += bytes(word[b] for b in range(iw) for word in index_bytes)
                assert encoded == scalar
        # Arbitrary bit patterns include values that are not valid numeric inputs.
        raw = rng.bytes(width * 1024)
        assert dictionary_decode(dictionary_encode(raw, width), width) == raw
    for dtype in (np.float32, np.float64):
        values = np.asarray([100.0, 100.1, 100.2], dtype=dtype)
        assert mzmlb_decode(mzmlb_encode(values, "none", 0), "none").tobytes() == values.tobytes()
        assert mzmlb_decode(mzmlb_encode(values, "delta", 0), "delta").tobytes() != values.tobytes()
    for width, words in (
        (4, [0, 2**31, 0x7F800000, 0xFF800000, 0x7FC01234, 0x7FC01235, 1]),
        (8, [0, 2**63, 0x7FF0000000000000, 0xFFF0000000000000, 0x7FF8000000001234, 0x7FF8000000001235, 1]),
    ):
        raw = np.asarray(words + words, dtype=f"<u{width}").tobytes()
        assert dictionary_decode(dictionary_encode(raw, width), width) == raw
    for malformed in (b"x", bytes(16), struct.pack("<QQ", 999, 1)):
        try:
            dictionary_decode(malformed, 8)
        except ValueError:
            pass
        else:
            raise AssertionError("malformed dictionary accepted")
