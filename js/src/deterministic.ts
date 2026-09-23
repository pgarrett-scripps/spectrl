/** expm1 and log1p that give the same bits in every implementation.
 *
 * The lossy codecs reconstruct values with expm1, and a token is meant to
 * decode to the same spectrum wherever it is opened. IEEE 754 fixes the result
 * of every arithmetic operation but says nothing about transcendental
 * functions, so each platform's libm is free to differ by up to an ulp. V8 and
 * numpy (glibc) do: expm1 disagrees on about one decode-path input in two
 * thousand, often enough that most real spectra contain at least one such peak.
 *
 * These are the fdlibm algorithms, built only from +, -, * and / on doubles
 * and from powers of two that are exactly representable, so every step is
 * specified exactly by IEEE 754 and both languages produce identical bits by
 * construction. Accuracy is fdlibm's, under one ulp, measured equal to glibc's.
 *
 * The Python port lives in src/spectrl/codecs/_deterministic.py and the two are
 * compared bit for bit by the parity check. */

// fdlibm's branch boundaries. The C code compares the high word of |x|, so each
// threshold is the double whose high word is one greater, with a zero low word.
const BIG = 38.816253662109375 // 56 * ln2; below -this, expm1 saturates at -1
const OVERFLOW = 7.09782712893383973096e+02 // above this, exp overflows
const HALF_LN2 = 0.3465735912322998
const THREE_HALF_LN2 = 1.0397214889526367
const TINY = 5.551120417081703e-17 // 2**-54, below which expm1(x) is x

// ln2 split so that k * LN2_HI is exact for every k fdlibm produces.
const LN2_HI = 6.93147180369123816490e-01
const LN2_LO = 1.90821492927058770002e-10
const INV_LN2 = 1.44269504088896338700e+00

// Minimax coefficients for R1(z), fdlibm s_expm1.c.
const Q1 = -3.33333333333331316428e-02
const Q2 = 1.58730158725481460165e-03
const Q3 = -7.93650757867487942473e-05
const Q4 = 4.00821782732936239552e-06
const Q5 = -2.01099218183624371326e-07

/** exp(x) - 1, computed identically on every platform. */
export function expm1(x: number): number {
  if (Number.isNaN(x) || x === Infinity) return x
  const negative = x < 0 || Object.is(x, -0)
  const absolute = Math.abs(x)

  // fdlibm does not short-circuit large |x| to exp(x)-1: it filters overflow
  // and saturation, then falls through to the ordinary path, whose k > 56
  // branch handles the rest. Calling exp() here would reintroduce the platform
  // routine this module exists to avoid.
  if (x === -Infinity || x <= -BIG) return -1
  if (x > OVERFLOW) return Infinity
  if (absolute < TINY) return x

  // Argument reduction: x = k*ln2 + r, with c the error in r.
  let k = 0, reduced = x, c = 0
  if (absolute >= HALF_LN2) {
    let hi: number, lo: number
    if (absolute < THREE_HALF_LN2) {
      // k is +-1 without a multiply, which keeps hi exact.
      if (negative) { hi = x + LN2_HI; lo = -LN2_LO; k = -1 }
      else { hi = x - LN2_HI; lo = LN2_LO; k = 1 }
    } else {
      // trunc, not floor: fdlibm's int cast rounds toward zero.
      k = Math.trunc(INV_LN2 * x + (negative ? -0.5 : 0.5))
      hi = x - k * LN2_HI // exact
      lo = k * LN2_LO
    }
    reduced = hi - lo
    c = (hi - reduced) - lo
  }

  // The rational approximation on the reduced range.
  const half = 0.5 * reduced
  const hxs = reduced * half
  const r1 = 1 + hxs * (Q1 + hxs * (Q2 + hxs * (Q3 + hxs * (Q4 + hxs * Q5))))
  const t = 3 - r1 * half
  let e = hxs * ((r1 - t) / (6 - reduced * t))

  if (k === 0) return reduced - (reduced * e - hxs)

  e = reduced * (e - c) - c - hxs
  if (k === -1) return 0.5 * (reduced - e) - 0.5
  if (k === 1) {
    return reduced < -0.25 ? -2 * (e - (reduced + 0.5)) : 1 + 2 * (reduced - e)
  }
  // Powers of two are exact, so the scaling introduces no rounding of its own.
  const twoK = pow2(k)
  if (k <= -2 || k > 56) return (1 - (e - reduced)) * twoK - 1
  if (k < 20) return (1 - pow2(-k) - (e - reduced)) * twoK
  return (reduced - (e + pow2(-k)) + 1) * twoK
}

/** 2**k without a pow() call, so the result is the exact power of two. */
function pow2(k: number): number {
  if (k >= -1022 && k <= 1023) {
    // A normal power of two is exactly representable; build it from its bits.
    const bits = new DataView(new ArrayBuffer(8))
    bits.setUint32(0, (k + 1023) << 20, false)
    bits.setUint32(4, 0, false)
    return bits.getFloat64(0, false)
  }
  return Math.pow(2, k)
}

// fdlibm s_log1p.c. Lp1..Lp7 approximate log((2+s)/(2-s))/s on the reduced range.
const LP1 = 6.666666666666735130e-01
const LP2 = 3.999999999940941908e-01
const LP3 = 2.857142874366239149e-01
const LP4 = 2.222219843214978396e-01
const LP5 = 1.818357216161805012e-01
const LP6 = 1.531383769920937332e-01
const LP7 = 1.479819860511658591e-01

// fdlibm compares high words, so each threshold is the exact double that
// comparison corresponds to.
const SQRT2_LOWER = 0.4142136573791504 // hx < 0x3FDA827A: 1 + x is below sqrt(2)
// hx <= 0xbfd2bec3 on a SIGNED high word, which for a negative x means |x| is
// at most this, not at least.
const NO_REDUCTION = -0.2928931713104248
const SMALL = 1.862645149230957e-09 // 2**-29
const VERY_SMALL = 5.551115123125783e-17 // 2**-54
const TWO53 = 9007199254740992.0 // above this, 1 + x is just x
const MANTISSA_SQRT2 = 1.4142131805419922 // the 0x6a09e mantissa boundary

const scratch = new DataView(new ArrayBuffer(8))

/** x = mantissa * 2**exponent with mantissa in [0.5, 1), exactly. */
function frexp(x: number): { mantissa: number, exponent: number } {
  scratch.setFloat64(0, x, false)
  let high = scratch.getUint32(0, false)
  let biased = (high >>> 20) & 0x7ff
  let offset = 0
  if (biased === 0) {
    // Subnormal: scale into the normal range first, exactly.
    scratch.setFloat64(0, x * 18446744073709551616, false) // 2**64
    high = scratch.getUint32(0, false)
    biased = (high >>> 20) & 0x7ff
    offset = -64
  }
  scratch.setUint32(0, (high & 0x800fffff) | 0x3fe00000, false)
  return { mantissa: scratch.getFloat64(0, false), exponent: biased - 1022 + offset }
}

/** log(1 + x), computed identically on every platform.
 *
 * The encoder quantizes log1p values and derives the stored scale from one, so
 * a platform disagreement here could move a rounded integer or the scale itself
 * and produce a different token. */
export function log1p(x: number): number {
  if (Number.isNaN(x) || x === Infinity) return x
  if (x === -Infinity || x < -1) return NaN
  if (x === -1) return -Infinity
  if (x === 0) return x // preserves -0
  const absolute = Math.abs(x)
  if (absolute < VERY_SMALL) return x
  if (absolute < SMALL) return x - x * x * 0.5

  // Reduce 1 + x to u in [sqrt(2)/2, sqrt(2)), recording k.
  const nearOne = x < SQRT2_LOWER && (x > 0 || x >= NO_REDUCTION)
  let k = 0, f = x, c = 0
  if (!nearOne) {
    const huge = x >= TWO53
    const uRaw = huge ? x : 1 + x
    const { mantissa, exponent } = frexp(uRaw)
    let u = 2 * mantissa
    k = exponent - 1
    // The correction term recovers what 1 + x rounded away. fdlibm computes it
    // from the exponent of 1 + x, before the sqrt(2) adjustment below moves it.
    c = huge ? 0 : (k > 0 ? 1 - (uRaw - x) : x - (uRaw - 1)) / uRaw
    if (u >= MANTISSA_SQRT2) { u = 0.5 * u; k += 1 }
    f = u - 1
  }

  const hfsq = 0.5 * f * f
  const s = f / (2 + f)
  const z = s * s
  const r = z * (LP1 + z * (LP2 + z * (LP3 + z * (LP4 + z * (LP5 + z * (LP6 + z * LP7))))))
  if (k === 0) return f - (hfsq - s * (hfsq + r))
  return k * LN2_HI - ((hfsq - (s * (hfsq + r) + (k * LN2_LO + c))) - f)
}
