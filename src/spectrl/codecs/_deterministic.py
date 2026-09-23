"""expm1 and log1p that give the same bits in every implementation.

The lossy codecs reconstruct values with expm1, and a token is meant to decode
to the same spectrum wherever it is opened. IEEE 754 fixes the result of every
arithmetic operation but says nothing about transcendental functions, so each
platform's libm is free to differ by up to an ulp. numpy (glibc) and V8 do:
expm1 disagrees on about one decode-path input in two thousand, which is often
enough that most real spectra contain at least one such peak.

These are the fdlibm algorithms, built only from +, - , * and / on doubles and
from powers of two that are exactly representable. Every step is therefore
specified exactly by IEEE 754, so Python and JavaScript produce identical bits
by construction rather than by luck. Accuracy is fdlibm's, under one ulp, which
is what the platform routines were already delivering.

The JavaScript port lives in js/src/deterministic.ts and the two are compared
bit for bit by the parity check.
"""

from __future__ import annotations

import numpy as np

# fdlibm's branch boundaries. The C code compares the high word of |x|, so each
# threshold is the double whose high word is one greater, with a zero low word.
_BIG = 38.816253662109375  # 56 * ln2; below -this, expm1 saturates at -1
_OVERFLOW = 7.09782712893383973096e02  # above this, exp overflows
_HALF_LN2 = 0.3465735912322998
_THREE_HALF_LN2 = 1.0397214889526367
_TINY = 5.551120417081703e-17  # 2**-54, below which expm1(x) is x

# ln2 split so that k * _LN2_HI is exact for every k fdlibm produces.
_LN2_HI = 6.93147180369123816490e-01
_LN2_LO = 1.90821492927058770002e-10
_INV_LN2 = 1.44269504088896338700e00

# Minimax coefficients for R1(z), fdlibm s_expm1.c.
_Q1 = -3.33333333333331316428e-02
_Q2 = 1.58730158725481460165e-03
_Q3 = -7.93650757867487942473e-05
_Q4 = 4.00821782732936239552e-06
_Q5 = -2.01099218183624371326e-07


def expm1(x):
    """exp(x) - 1, computed identically on every platform.

    Vectorized over a numpy array. Every branch fdlibm selects between is
    evaluated and then chosen with a mask, which costs a few flops per element
    and keeps the whole array on one code path.
    """
    x = np.asarray(x, dtype=np.float64)
    special = ~np.isfinite(x)
    # Non-finite inputs are replaced at the end, but they would otherwise raise
    # their way through the reduction, so they travel as zero.
    work = np.where(special, 0.0, x)
    out = np.empty(work.shape, dtype=np.float64)
    absolute = np.abs(work)
    negative = np.signbit(work)

    # --- argument reduction: x = k*ln2 + r, with c the error in r ---------
    # |x| in [0.5 ln2, 1.5 ln2) takes k = +-1 without a multiply, which keeps
    # hi exact.
    near = absolute >= _HALF_LN2
    inner = near & (absolute < _THREE_HALF_LN2)
    outer = near & ~inner

    k = np.zeros(x.shape, dtype=np.float64)
    hi = np.array(work, dtype=np.float64, copy=True)
    lo = np.zeros(x.shape, dtype=np.float64)

    k = np.where(inner, np.where(negative, -1.0, 1.0), k)
    hi = np.where(inner, np.where(negative, work + _LN2_HI, work - _LN2_HI), hi)
    lo = np.where(inner, np.where(negative, -_LN2_LO, _LN2_LO), lo)

    # trunc, not floor: fdlibm's int cast rounds toward zero after the +-0.5.
    k_outer = np.trunc(_INV_LN2 * work + np.where(negative, -0.5, 0.5))
    k = np.where(outer, k_outer, k)
    hi = np.where(outer, work - k_outer * _LN2_HI, hi)  # exact
    lo = np.where(outer, k_outer * _LN2_LO, lo)

    reduced = np.where(near, hi - lo, work)
    c = np.where(near, (hi - reduced) - lo, 0.0)

    # --- the rational approximation on the reduced range -----------------
    half = 0.5 * reduced
    hxs = reduced * half
    r1 = 1.0 + hxs * (_Q1 + hxs * (_Q2 + hxs * (_Q3 + hxs * (_Q4 + hxs * _Q5))))
    t = 3.0 - r1 * half
    with np.errstate(divide="ignore", invalid="ignore"):
        e = hxs * ((r1 - t) / (6.0 - reduced * t))

    # --- reassembly, one case per fdlibm branch --------------------------
    # k == 0: c is zero and no scaling is needed.
    out = reduced - (reduced * e - hxs)

    integer_k = k.astype(np.int64)
    scaled_e = reduced * (e - c) - c - hxs

    minus_one = integer_k == -1
    out = np.where(minus_one, 0.5 * (reduced - scaled_e) - 0.5, out)

    plus_one = integer_k == 1
    out = np.where(
        plus_one,
        np.where(reduced < -0.25, -2.0 * (scaled_e - (reduced + 0.5)), 1.0 + 2.0 * (reduced - scaled_e)),
        out,
    )

    # Powers of two are exact, so ldexp introduces no rounding of its own.
    with np.errstate(over="ignore"):
        two_k = np.ldexp(np.ones(work.shape), np.clip(integer_k, -1100, 1100))

    far = (integer_k <= -2) | (integer_k > 56)
    with np.errstate(over="ignore", invalid="ignore"):
        out = np.where(far, (1.0 - (scaled_e - reduced)) * two_k - 1.0, out)

        # 2 <= k <= 56, split at 20 the way fdlibm does to keep t exact.
        small = (integer_k >= 2) & (integer_k < 20)
        t_small = 1.0 - np.ldexp(np.ones(work.shape), -np.clip(integer_k, 0, 1023))
        out = np.where(small, (t_small - (scaled_e - reduced)) * two_k, out)

        large = (integer_k >= 20) & (integer_k <= 56)
        t_large = np.ldexp(np.ones(work.shape), -np.clip(integer_k, 0, 1023))
        out = np.where(large, (reduced - (scaled_e + t_large) + 1.0) * two_k, out)

    # --- ends of the range ------------------------------------------------
    out = np.where(absolute < _TINY, work, out)
    out = np.where(work <= -_BIG, -1.0, out)
    out = np.where(work > _OVERFLOW, np.inf, out)
    out = np.where(np.isneginf(x), -1.0, out)
    out = np.where(np.isposinf(x) | np.isnan(x), x, out)
    return out


# fdlibm s_log1p.c. Lp1..Lp7 approximate log((2+s)/(2-s))/s on the reduced range.
_LP1 = 6.666666666666735130e-01
_LP2 = 3.999999999940941908e-01
_LP3 = 2.857142874366239149e-01
_LP4 = 2.222219843214978396e-01
_LP5 = 1.818357216161805012e-01
_LP6 = 1.531383769920937332e-01
_LP7 = 1.479819860511658591e-01

# fdlibm compares high words, so each threshold below is the exact double that
# comparison corresponds to.
_SQRT2_LOWER = 0.4142136573791504  # hx < 0x3FDA827A: 1 + x is below sqrt(2)
_NO_REDUCTION = -0.2928931713104248  # hx <= 0xbfd2bec3 on a SIGNED high word,
# which for a negative x means |x| is at most this, not at least.
_SMALL = 1.862645149230957e-09  # 2**-29
_VERY_SMALL = 5.551115123125783e-17  # 2**-54
_TWO53 = 9007199254740992.0  # above this, 1 + x is just x
_MANTISSA_SQRT2 = 1.4142131805419922  # the 0x6a09e mantissa boundary


def log1p(x):
    """log(1 + x), computed identically on every platform.

    The encoder quantizes log1p values and derives the stored scale from one,
    so a platform disagreement here could move a rounded integer or the scale
    itself and produce a different token. It has never been observed, but a
    format that promises the same token everywhere should not rest on that.
    """
    x = np.asarray(x, dtype=np.float64)
    finite = np.isfinite(x)
    work = np.where(finite, x, 0.0)
    absolute = np.abs(work)

    # --- reduce 1 + x to u in [sqrt(2)/2, sqrt(2)), recording k ------------
    # frexp gives u = m * 2**e with m in [0.5, 1), so 2m lies in [1, 2) and
    # the exponent fdlibm reads from the high word is e - 1.
    near_one = (work < _SQRT2_LOWER) & ((work > 0) | (work >= _NO_REDUCTION))
    with np.errstate(invalid="ignore"):
        # Past 2**53 the addition is a no-op, and fdlibm skips it rather than
        # computing a correction that would be zero anyway.
        huge = work >= _TWO53
        u_raw = np.where(near_one, 1.0, np.where(huge, work, 1.0 + work))
        mantissa, exponent = np.frexp(np.where(u_raw > 0, u_raw, 1.0))
    u = 2.0 * mantissa
    k = exponent - 1
    # The correction term recovers what 1.0 + x rounded away. fdlibm computes
    # it from the exponent of 1 + x, which is this k, *before* the sqrt(2)
    # adjustment below moves it; using the adjusted k picks the wrong branch
    # for every x just above sqrt(2) - 1 and costs an ulp of accuracy.
    with np.errstate(invalid="ignore"):
        c = np.where(k > 0, 1.0 - (u_raw - work), work - (u_raw - 1.0))
        c = np.where(huge, 0.0, c / u_raw)
    # A mantissa at or above sqrt(2) is halved instead, keeping |f| smallest.
    high = u >= _MANTISSA_SQRT2
    u = np.where(high, 0.5 * u, u)
    k = np.where(high, k + 1, k)

    f = np.where(near_one, work, u - 1.0)
    k = np.where(near_one, 0, k)
    c = np.where(near_one, 0.0, c)

    # --- the rational approximation ---------------------------------------
    hfsq = 0.5 * f * f
    with np.errstate(invalid="ignore", divide="ignore"):
        s = f / (2.0 + f)
        z = s * s
        r = z * (_LP1 + z * (_LP2 + z * (_LP3 + z * (_LP4 + z * (_LP5 + z * (_LP6 + z * _LP7))))))
        k_float = k.astype(np.float64)
        out = np.where(
            k == 0,
            f - (hfsq - s * (hfsq + r)),
            k_float * _LN2_HI - ((hfsq - (s * (hfsq + r) + (k_float * _LN2_LO + c))) - f),
        )

    # --- ends of the range -------------------------------------------------
    # |x| < 2**-29 keeps only the first two terms; below 2**-54, log1p(x) is x.
    with np.errstate(over="ignore"):
        out = np.where(absolute < _SMALL, work - work * work * 0.5, out)
    out = np.where(absolute < _VERY_SMALL, work, out)
    out = np.where(work == 0.0, work, out)  # preserves -0.0
    out = np.where(work == -1.0, -np.inf, out)
    out = np.where(work < -1.0, np.nan, out)
    out = np.where(np.isnan(x) | np.isposinf(x), x, out)
    out = np.where(np.isneginf(x), np.nan, out)
    return out
