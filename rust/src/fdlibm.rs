//! fdlibm 5.3 `log1p` and `expm1`, ported line for line.
//!
//! Section 5 pins encoding 3's logarithm to these algorithms in binary64 so
//! that every implementation computes the same indices and reconstructed
//! bits. Only IEEE 754 basic operations and bit manipulation are used; the
//! platform math library is never called. `tests/fdlibm.rs` checks both
//! against reference outputs from Java `StrictMath` (fdlibm 5.3).

#![allow(clippy::excessive_precision, clippy::many_single_char_names)]

fn hi(x: f64) -> i32 {
    (x.to_bits() >> 32) as u32 as i32
}

fn lo(x: f64) -> u32 {
    x.to_bits() as u32
}

fn with_hi(x: f64, high: i32) -> f64 {
    f64::from_bits(((high as u32 as u64) << 32) | (x.to_bits() & 0xffff_ffff))
}

const LN2_HI: f64 = 6.93147180369123816490e-01; // 0x3fe62e42 fee00000
const LN2_LO: f64 = 1.90821492927058770002e-10; // 0x3dea39ef 35793c76

/// ln(1 + x), fdlibm 5.3 `s_log1p.c`.
pub fn log1p(x: f64) -> f64 {
    const TWO54: f64 = 1.80143985094819840000e+16;
    const LP1: f64 = 6.666666666666735130e-01;
    const LP2: f64 = 3.999999999940941908e-01;
    const LP3: f64 = 2.857142874366239149e-01;
    const LP4: f64 = 2.222219843214978396e-01;
    const LP5: f64 = 1.818357216161805012e-01;
    const LP6: f64 = 1.531383769920937332e-01;
    const LP7: f64 = 1.479819860511658591e-01;
    let zero = 0.0f64;

    let hx = hi(x);
    let ax = hx & 0x7fff_ffff;
    let mut k: i32 = 1;
    let mut f = 0.0f64;
    let mut hu: i32 = 0;
    let mut c = 0.0f64;

    if hx < 0x3FDA827A {
        // x < 0.41422
        if ax >= 0x3ff00000 {
            // x <= -1.0
            if x == -1.0 {
                return -TWO54 / zero; // log1p(-1) = -inf
            }
            return (x - x) / (x - x); // log1p(x < -1) = NaN
        }
        if ax < 0x3e200000 {
            // |x| < 2**-29
            if TWO54 + x > zero && ax < 0x3c900000 {
                // |x| < 2**-54
                return x;
            }
            return x - x * x * 0.5;
        }
        if hx > 0 || hx <= 0xbfd2bec3u32 as i32 {
            // -0.2929 < x < 0.41422
            k = 0;
            f = x;
            hu = 1;
        }
    }
    if hx >= 0x7ff00000 {
        return x + x;
    }
    if k != 0 {
        let mut u;
        if hx < 0x43400000 {
            u = 1.0 + x;
            hu = hi(u);
            k = (hu >> 20) - 1023;
            c = if k > 0 { 1.0 - (u - x) } else { x - (u - 1.0) }; // correction term
            c /= u;
        } else {
            u = x;
            hu = hi(u);
            k = (hu >> 20) - 1023;
            c = 0.0;
        }
        hu &= 0x000fffff;
        if hu < 0x6a09e {
            u = with_hi(u, hu | 0x3ff00000); // normalize u
        } else {
            k += 1;
            u = with_hi(u, hu | 0x3fe00000); // normalize u/2
            hu = (0x00100000 - hu) >> 2;
        }
        f = u - 1.0;
    }
    let hfsq = 0.5 * f * f;
    if hu == 0 {
        // |f| < 2**-20
        if f == zero {
            if k == 0 {
                return zero;
            }
            c += k as f64 * LN2_LO;
            return k as f64 * LN2_HI + c;
        }
        let r = hfsq * (1.0 - 0.66666666666666666 * f);
        if k == 0 {
            return f - r;
        }
        return k as f64 * LN2_HI - ((r - (k as f64 * LN2_LO + c)) - f);
    }
    let s = f / (2.0 + f);
    let z = s * s;
    let r = z * (LP1 + z * (LP2 + z * (LP3 + z * (LP4 + z * (LP5 + z * (LP6 + z * LP7))))));
    if k == 0 {
        return f - (hfsq - s * (hfsq + r));
    }
    k as f64 * LN2_HI - ((hfsq - (s * (hfsq + r) + (k as f64 * LN2_LO + c))) - f)
}

/// exp(x) - 1, fdlibm 5.3 `s_expm1.c`, including its behavior for k = 1024
/// (arguments just below the overflow threshold), where the exponent
/// adjustment below reaches the infinity/NaN exponent.
pub fn expm1(x: f64) -> f64 {
    const ONE: f64 = 1.0;
    const HUGE: f64 = 1.0e+300;
    const TINY: f64 = 1.0e-300;
    const O_THRESHOLD: f64 = 7.09782712893383973096e+02;
    const INVLN2: f64 = 1.44269504088896338700e+00;
    const Q1: f64 = -3.33333333333331316428e-02;
    const Q2: f64 = 1.58730158725481460165e-03;
    const Q3: f64 = -7.93650757867487942473e-05;
    const Q4: f64 = 4.00821782732936239552e-06;
    const Q5: f64 = -2.01099218183624371326e-07;

    let mut x = x;
    let mut hx = hi(x) as u32;
    let xsb = hx & 0x8000_0000; // sign bit of x
    hx &= 0x7fff_ffff; // high word of |x|

    // filter out huge and non-finite argument
    if hx >= 0x4043687A {
        // |x| >= 56*ln2
        if hx >= 0x40862E42 {
            // |x| >= 709.78...
            if hx >= 0x7ff00000 {
                if ((hx & 0xfffff) | lo(x)) != 0 {
                    return x + x; // NaN
                }
                return if xsb == 0 { x } else { -1.0 };
            }
            if x > O_THRESHOLD {
                return HUGE * HUGE; // overflow
            }
        }
        if xsb != 0 && x + TINY < 0.0 {
            // x < -56*ln2
            return TINY - ONE; // -1
        }
    }

    let k: i32;
    let mut c = 0.0f64;
    // argument reduction
    if hx > 0x3fd62e42 {
        // |x| > 0.5 ln2
        let (h, l);
        if hx < 0x3FF0A2B2 {
            // and |x| < 1.5 ln2
            if xsb == 0 {
                h = x - LN2_HI;
                l = LN2_LO;
                k = 1;
            } else {
                h = x + LN2_HI;
                l = -LN2_LO;
                k = -1;
            }
        } else {
            k = (INVLN2 * x + if xsb == 0 { 0.5 } else { -0.5 }) as i32;
            let t = k as f64;
            h = x - t * LN2_HI; // t*ln2_hi is exact here
            l = t * LN2_LO;
        }
        x = h - l;
        c = (h - x) - l;
    } else if hx < 0x3c900000 {
        // |x| < 2**-54, return x
        let t = HUGE + x;
        return x - (t - (HUGE + x));
    } else {
        k = 0;
    }

    // x is now in primary range
    let hfx = 0.5 * x;
    let hxs = x * hfx;
    let r1 = ONE + hxs * (Q1 + hxs * (Q2 + hxs * (Q3 + hxs * (Q4 + hxs * Q5))));
    let t = 3.0 - r1 * hfx;
    let mut e = hxs * ((r1 - t) / (6.0 - x * t));
    if k == 0 {
        return x - (x * e - hxs); // c is 0
    }
    e = x * (e - c) - c;
    e -= hxs;
    if k == -1 {
        return 0.5 * (x - e) - 0.5;
    }
    if k == 1 {
        if x < -0.25 {
            return -2.0 * (e - (x + 0.5));
        }
        return ONE + 2.0 * (x - e);
    }
    let add_exponent = |y: f64| with_hi(y, hi(y).wrapping_add(k.wrapping_shl(20)));
    if k <= -2 || k > 56 {
        // suffice to return exp(x)-1
        let y = add_exponent(ONE - (e - x));
        return y - ONE;
    }
    let y = if k < 20 {
        let t = with_hi(ONE, 0x3ff00000 - (0x200000 >> k)); // t = 1 - 2^-k
        add_exponent(t - (e - x))
    } else {
        let t = with_hi(ONE, (0x3ff - k) << 20); // 2^-k
        add_exponent(x - (e + t) + ONE)
    };
    y
}
