//! Seeded property tests: lossless round trips are bit-exact, default-profile
//! values stay within their stated bounds, and arbitrary corruption of a
//! valid token yields an error value, never a panic.

use spectrl::{
    Array, Compression, EncodeOptions, Spectrum, decode_token, encode_spectrum, inspect_token,
};

struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn below(&mut self, n: u64) -> u64 {
        self.next() % n
    }
}

fn spectrum(rng: &mut Rng) -> Spectrum {
    let n = rng.below(300) as usize;
    let mut s = Spectrum::new(n);
    let mz: Vec<f64> = (0..n).map(|_| 50.0 + rng.unit() * 1950.0).collect();
    let intensity: Vec<f64> = (0..n)
        .map(|_| match rng.below(4) {
            0 => rng.below(100_000) as f64,
            1 => rng.unit() * 1e-3,
            2 => 0.0,
            _ => (rng.unit() * 20.0).exp(),
        })
        .collect();
    if rng.below(2) == 0 {
        s.mz = Some(Array::F32(mz.iter().map(|&v| v as f32).collect()));
        s.intensity = Some(Array::F32(intensity.iter().map(|&v| v as f32).collect()));
    } else {
        s.mz = Some(Array::F64(mz));
        s.intensity = Some(Array::F64(intensity));
    }
    if rng.below(2) == 0 {
        s.charge = Some(Array::I32((0..n).map(|_| rng.below(5) as i32).collect()));
    }
    s
}

fn sorted_by_mz(s: &Spectrum) -> (Vec<f64>, Vec<f64>, Option<Array>) {
    let mz = s.mz.as_ref().unwrap().to_f64();
    let it = s.intensity.as_ref().unwrap().to_f64();
    let mut idx: Vec<usize> = (0..mz.len()).collect();
    idx.sort_by(|&a, &b| mz[a].partial_cmp(&mz[b]).unwrap());
    let charge = s.charge.as_ref().map(|c| c.permute(&idx));
    (
        idx.iter().map(|&i| mz[i]).collect(),
        idx.iter().map(|&i| it[i]).collect(),
        charge,
    )
}

#[test]
fn round_trips_within_profile_bounds() {
    let mut rng = Rng(0x5eed_1234_abcd_ef01);
    let modes = [
        Compression::Raw,
        Compression::Zlib,
        #[cfg(feature = "brotli")]
        Compression::Brotli,
        Compression::Auto,
    ];
    for case in 0..300 {
        let s = spectrum(&mut rng);
        let (mz, it, charge) = sorted_by_mz(&s);
        for lossless in [true, false] {
            let compression = modes[case % modes.len()];
            let token = encode_spectrum(
                &s,
                EncodeOptions {
                    lossless,
                    compression,
                },
            )
            .unwrap();
            let d = decode_token(&token).unwrap().spectrum;
            let (gm, gi) = (
                d.mz.as_ref().unwrap().to_f64(),
                d.intensity.as_ref().unwrap().to_f64(),
            );
            if lossless {
                assert_eq!(
                    d.mz.as_ref().unwrap().dtype(),
                    s.mz.as_ref().unwrap().dtype()
                );
                assert_eq!(
                    gm.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
                    mz.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
                );
                assert_eq!(
                    gi.iter().map(|v| v.to_bits()).collect::<Vec<_>>(),
                    it.iter().map(|v| v.to_bits()).collect::<Vec<_>>()
                );
            } else {
                for (g, x) in gm.iter().zip(&mz) {
                    assert!((g - x).abs() <= 0.1e-6 * x, "case {case}: m/z {x} -> {g}");
                }
                for (g, x) in gi.iter().zip(&it) {
                    // The loosest intensity candidate: log scale 3600.
                    assert!(
                        (g - x).abs() <= 2.0 * (0.5f64 / 3600.0).exp_m1() * x.max(1.0),
                        "case {case}: {x} -> {g}"
                    );
                }
            }
            assert_eq!(d.charge, charge);
        }
    }
}

#[test]
fn corruption_is_an_error_not_a_panic() {
    let mut rng = Rng(0xdead_beef_0bad_f00d);
    let mut rejected = 0;
    for _ in 0..3000 {
        let s = spectrum(&mut rng);
        let token = encode_spectrum(
            &s,
            EncodeOptions {
                lossless: rng.below(2) == 0,
                compression: Compression::Raw,
            },
        )
        .unwrap();
        let mut bytes = token.into_bytes();
        let edits = 1 + rng.below(4);
        for _ in 0..edits {
            let i = rng.below(bytes.len() as u64) as usize;
            const ALPHABET: &[u8] =
                b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.";
            bytes[i] = ALPHABET[rng.below(ALPHABET.len() as u64) as usize];
        }
        let mut text = String::from_utf8(bytes).unwrap();
        // Repair the checksum half the time so the payload itself is exercised.
        if rng.below(2) == 0 {
            if let Some(dot) = text.rfind('.') {
                let sum = spectrl::framing::checksum(&text[..dot]);
                text.truncate(dot + 1);
                text.push_str(&sum);
            }
        }
        let a = std::panic::catch_unwind(|| decode_token(&text).is_err()).expect("decode panicked");
        let b =
            std::panic::catch_unwind(|| inspect_token(&text).is_err()).expect("inspect panicked");
        rejected += (a || b) as usize;
    }
    assert!(rejected > 0);
}
