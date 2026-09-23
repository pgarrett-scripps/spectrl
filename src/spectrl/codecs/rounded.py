"""Rounded floating-point words for v3 encoding 4.

Each value keeps its sign, exponent and leading ``bits`` mantissa bits. The
rounding is done on the unsigned integer view of the IEEE 754 bits, so it uses
integer operations only and every conforming writer produces the same words.
"""

from __future__ import annotations

import numpy as np

from ..cv import TYPE_FLOAT32, TYPE_FLOAT64
from .shuffle import shuffle

# Declared type -> (mantissa bits M, type size W in bytes).
_FORMATS = {TYPE_FLOAT32: (23, 4), TYPE_FLOAT64: (52, 8)}


def validate(params):
    if set(params) != {"bits", "width"}:
        raise ValueError("rounded encoding requires exactly bits and width")
    bits = params["bits"]
    if type(bits) is not int or not 0 <= bits <= 52:
        raise ValueError("rounded mantissa bits must be an integer from 0 to 52")
    if type(params["width"]) is not int or params["width"] not in (1, 2, 4, 8):
        raise ValueError("rounded word width must be 1, 2, 4, or 8")


def _format(tail, params):
    try:
        mantissa, size = _FORMATS[tail]
    except KeyError:
        raise ValueError("rounded encoding requires float32 or float64") from None
    if params["bits"] > mantissa:
        raise ValueError("rounded mantissa bits exceed the declared type")
    if params["width"] > size:
        raise ValueError("rounded word width exceeds the declared type")
    return mantissa - params["bits"], size


def words(data, tail, bits):
    """Rounded unsigned words (as uint64) for ``data`` in the declared float type."""
    shift, size = _format(tail, {"bits": bits, "width": 1})
    a = np.asarray(data, dtype=f"<f{size}")
    if not np.isfinite(a).all():
        raise ValueError("rounded encoding requires finite values")
    u = a.view(f"<u{size}").astype(np.uint64)
    if shift == 0:
        return u
    # (u + 2**(shift-1)) >> shift without overflow: add the first dropped bit.
    return (u >> np.uint64(shift)) + ((u >> np.uint64(shift - 1)) & np.uint64(1))


def parameters(data, tail, bits):
    """Choose the smallest word width that holds every rounded word."""
    _, size = _format(tail, {"bits": bits, "width": 1})
    maximum = int(words(data, tail, bits).max(initial=0))
    return {"bits": bits, "width": next(w for w in (1, 2, 4, 8) if w <= size and maximum < 2 ** (8 * w))}


def _reconstruct(w, tail, shift, size):
    # With shift 0 every word of at most W bytes is in range.
    if shift and np.any(w >= np.uint64(2 ** (8 * size - shift))):
        raise ValueError("rounded word exceeds the declared type")
    bits = (w << np.uint64(shift)).astype(f"<u{size}")
    result = bits.view(f"<f{size}")
    if not np.isfinite(result).all():
        raise ValueError("rounded reconstruction is not finite")
    return result


def encode(data, tail, params):
    shift, size = _format(tail, params)
    w = words(data, tail, params["bits"])
    width = params["width"]
    if np.any(w > np.uint64(2 ** (8 * width) - 1)):
        raise ValueError("rounded word exceeds its word width")
    _reconstruct(w, tail, shift, size)
    return shuffle(w.astype(f"<u{width}").tobytes(), width)


def decode(blob, tail, count, params):
    shift, size = _format(tail, params)
    width = params["width"]
    if len(blob) != count * width:
        raise ValueError("rounded byte count mismatch")
    w = np.frombuffer(shuffle(blob, width, inverse=True), dtype=f"<u{width}").astype(np.uint64)
    return _reconstruct(w, tail, shift, size).copy()
