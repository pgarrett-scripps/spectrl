//! fdlibm `log1p` and `expm1` against Java `StrictMath` (the fdlibm 5.3
//! reference) bit for bit, and against the `libm` crate's fdlibm port.

use spectrl::fdlibm::{expm1, log1p};

#[test]
fn strictmath_table() {
    let text = include_str!("data/fdlibm-strictmath.txt");
    let mut n = 0;
    for line in text.lines().filter(|l| !l.trim().is_empty()) {
        let w: Vec<u64> = line
            .split_whitespace()
            .map(|h| u64::from_str_radix(h, 16).unwrap())
            .collect();
        let x = f64::from_bits(w[0]);
        // A NaN result's sign and payload follow the CPU's default NaN
        // (negative on x86-64, positive on aarch64), so NaNs match as NaNs.
        let same = |got: f64, want: u64| {
            got.to_bits() == want || (got.is_nan() && f64::from_bits(want).is_nan())
        };
        assert!(same(log1p(x), w[1]), "log1p({x:e}) [{line}]");
        assert!(same(expm1(x), w[2]), "expm1({x:e}) [{line}]");
        n += 1;
    }
    assert!(n > 20_000);
}

#[test]
fn matches_libm_port() {
    let mut s: u64 = 0x9e3779b97f4a7c15;
    for _ in 0..200_000 {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;
        let x = f64::from_bits(s);
        if !x.is_finite() {
            continue;
        }
        let (a, b) = (log1p(x), libm::log1p(x));
        assert!(
            a.to_bits() == b.to_bits() || (a.is_nan() && b.is_nan()),
            "log1p({x:e})"
        );
        let (a, b) = (expm1(x), libm::expm1(x));
        assert!(
            a.to_bits() == b.to_bits() || (a.is_nan() && b.is_nan()),
            "expm1({x:e})"
        );
    }
}
