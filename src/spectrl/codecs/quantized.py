"""Linear or log1p quantization followed by shuffled unsigned integer words.

Reconstruction goes through _deterministic.expm1 rather than the platform's,
so the same token decodes to the same bits in every implementation. See that
module for why the platform routine is not enough.
"""

import math

import numpy as np

from .._format import DEFAULT_INTENSITY_SCALE, DEFAULT_MZ_PPM
from ._deterministic import expm1 as deterministic_expm1
from ._deterministic import log1p as deterministic_log1p
from .shuffle import shuffle


def validate(params):
    if set(params) - {"scale", "width", "log", "delta"} or not {"scale", "width"} <= set(params):
        raise ValueError("quantized encoding requires scale and width")
    scale = params["scale"]
    if type(scale) not in (int, float) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("quantization scale must be finite and positive")
    if type(params["width"]) is not int or params["width"] not in (1, 2, 4, 8):
        raise ValueError("quantized word width must be 1, 2, 4, or 8")
    if any(type(params[k]) is not bool for k in ("log", "delta") if k in params):
        raise ValueError("quantized log and delta parameters must be booleans")


def indices(data, params):
    a = np.asarray(data, dtype=np.float64)
    if not np.isfinite(a).all() or np.any(a < 0):
        raise ValueError("quantization requires finite nonnegative values")
    with np.errstate(over="ignore", invalid="ignore"):
        scaled = (deterministic_log1p(a) if params.get("log", False) else a) * params["scale"]
        floor = np.floor(scaled)
        q = floor + (scaled - floor >= 0.5)
    if not np.isfinite(q).all() or np.any(q > 2**53 - 1):
        raise ValueError("quantized index exceeds the safe integer range")
    return q.astype("<u8")


def parameters(data, scale, *, log=False, delta=False):
    params = {"scale": scale}
    if log:
        params["log"] = True
    if delta:
        params["delta"] = True
    q = indices(data, params)
    maximum = int(q.max(initial=0))
    params["width"] = next(w for w in (1, 2, 4, 8) if maximum < 2 ** (8 * w))
    return params


def intensity_parameters(data, scale=DEFAULT_INTENSITY_SCALE):
    """Choose the default log1p intensity grid, refined for values below 1.

    log1p is nearly linear below 1, so a fixed scale gives an absolute floor
    there and zeroes small peaks of normalized spectra. When the smallest
    positive value m is below 1, the scale grows to scale * (m + 1) / (2 * m),
    which bounds every positive value by the relative error the fixed scale
    already allows at 1.
    """
    source = np.asarray(data, dtype=np.float64)
    positive = source[source > 0]
    minimum = float(positive.min()) if len(positive) else 1.0
    if minimum < 1:
        refined = scale / 2 * (minimum + 1) / minimum
        if not math.isfinite(refined) or refined > 2**53 - 1:
            raise ValueError("intensity scale is outside the supported range")
        scale = max(scale, math.ceil(refined))
    return parameters(source, scale, log=True)


def ppm_parameters(data, ppm=DEFAULT_MZ_PPM):
    """Choose a log1p grid with a checked pointwise relative error bound."""
    if type(ppm) not in (int, float) or not math.isfinite(ppm) or ppm <= 0:
        raise ValueError("ppm must be finite and positive")
    source = np.asarray(data, dtype=np.float64)
    if not np.isfinite(source).all() or np.any(source < 0):
        raise ValueError("ppm quantization requires finite nonnegative values")
    positive = source[source > 0]
    minimum = float(positive.min()) if len(positive) else 1.0
    relative = ppm * 1e-6
    # Calibrate the log1p bound at the smallest positive value. Reserve a
    # numerical margin and verify the actual reconstruction before accepting.
    log_step = float(deterministic_log1p(relative * (1 - 1e-7) * (minimum / (minimum + 1))))
    if log_step <= 0 or not math.isfinite(log_step):
        raise ValueError("ppm scale is outside the supported range")
    scale = 0.5 / log_step
    if not math.isfinite(scale) or scale > 2**53 - 1:
        raise ValueError("ppm scale is outside the supported range")
    params = parameters(source, math.ceil(scale), log=True, delta=True)
    recovered = deterministic_expm1(indices(source, params).astype(np.float64) / params["scale"])
    if np.any(np.abs(source - recovered) > source * relative):
        raise ValueError("quantized reconstruction exceeds the ppm bound")
    return params


def encode(data, _type, params):
    q = indices(data, params)
    width = params["width"]
    if np.any(q > min(2**53 - 1, 2 ** (8 * width) - 1)):
        raise ValueError("quantized index exceeds its word width")
    words = q.astype(f"<u{width}")
    if params.get("delta", False):
        words[1:] = words[1:] - words[:-1]
    blob = shuffle(words.tobytes(), width)
    recovered = decode(blob, _type, len(q), params)
    source = np.asarray(data, dtype=np.float64)
    half_step = 0.5 / params["scale"]
    with np.errstate(over="ignore"):
        bound = (source + 1) * deterministic_expm1(half_step) if params.get("log", False) else half_step
    if np.any(np.abs(source - recovered) > bound):
        raise ValueError("quantized reconstruction exceeds the rounding bound")
    return blob


def decode(blob, _type, count, params):
    width = params["width"]
    if len(blob) != count * width:
        raise ValueError("quantized byte count mismatch")
    words = np.frombuffer(shuffle(blob, width, inverse=True), dtype=f"<u{width}")
    if params.get("delta", False):
        words = np.cumsum(words, dtype=words.dtype)
    if np.any(words > 2**53 - 1):
        raise ValueError("quantized index exceeds the safe integer range")
    with np.errstate(over="ignore", invalid="ignore"):
        result = words.astype(np.float64) / params["scale"]
        if params.get("log", False):
            result = deterministic_expm1(result)
    if not np.isfinite(result).all():
        raise ValueError("quantized reconstruction is not finite")
    return result
