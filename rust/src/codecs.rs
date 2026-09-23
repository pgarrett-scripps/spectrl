//! Numeric encodings 0..4, revision 1 (section 5).

use crate::cbor::MAX_SAFE;
use crate::error::{Error, Result, bail};
use crate::fdlibm;

/// A reconstructed numeric type.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DType {
    F32,
    F64,
    I32,
}

impl DType {
    pub fn tail(self) -> i64 {
        match self {
            DType::F32 => 1000521,
            DType::F64 => 1000523,
            DType::I32 => 1000519,
        }
    }

    pub fn from_tail(tail: i64) -> Option<DType> {
        match tail {
            1000521 => Some(DType::F32),
            1000523 => Some(DType::F64),
            1000519 => Some(DType::I32),
            _ => None,
        }
    }

    pub fn size(self) -> usize {
        match self {
            DType::F32 | DType::I32 => 4,
            DType::F64 => 8,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            DType::F32 => "float32",
            DType::F64 => "float64",
            DType::I32 => "int32",
        }
    }

    pub fn from_name(name: &str) -> Option<DType> {
        match name {
            "float32" => Some(DType::F32),
            "float64" => Some(DType::F64),
            "int32" => Some(DType::I32),
            _ => None,
        }
    }

    pub fn is_float(self) -> bool {
        matches!(self, DType::F32 | DType::F64)
    }
}

/// One numeric array in its native type.
#[derive(Debug, Clone, PartialEq)]
pub enum Array {
    F32(Vec<f32>),
    F64(Vec<f64>),
    I32(Vec<i32>),
}

impl Array {
    pub fn dtype(&self) -> DType {
        match self {
            Array::F32(_) => DType::F32,
            Array::F64(_) => DType::F64,
            Array::I32(_) => DType::I32,
        }
    }

    pub fn len(&self) -> usize {
        match self {
            Array::F32(v) => v.len(),
            Array::F64(v) => v.len(),
            Array::I32(v) => v.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Value `i` widened to binary64 (exact for all three types).
    pub fn get(&self, i: usize) -> f64 {
        match self {
            Array::F32(v) => v[i] as f64,
            Array::F64(v) => v[i],
            Array::I32(v) => v[i] as f64,
        }
    }

    pub fn to_f64(&self) -> Vec<f64> {
        (0..self.len()).map(|i| self.get(i)).collect()
    }

    /// Native little-endian words.
    pub fn to_le_bytes(&self) -> Vec<u8> {
        match self {
            Array::F32(v) => v.iter().flat_map(|x| x.to_le_bytes()).collect(),
            Array::F64(v) => v.iter().flat_map(|x| x.to_le_bytes()).collect(),
            Array::I32(v) => v.iter().flat_map(|x| x.to_le_bytes()).collect(),
        }
    }

    pub fn from_le_bytes(dtype: DType, bytes: &[u8]) -> Array {
        match dtype {
            DType::F32 => Array::F32(
                bytes
                    .chunks_exact(4)
                    .map(|c| f32::from_le_bytes(c.try_into().unwrap()))
                    .collect(),
            ),
            DType::F64 => Array::F64(
                bytes
                    .chunks_exact(8)
                    .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
                    .collect(),
            ),
            DType::I32 => Array::I32(
                bytes
                    .chunks_exact(4)
                    .map(|c| i32::from_le_bytes(c.try_into().unwrap()))
                    .collect(),
            ),
        }
    }

    pub fn all_finite(&self) -> bool {
        match self {
            Array::F32(v) => v.iter().all(|x| x.is_finite()),
            Array::F64(v) => v.iter().all(|x| x.is_finite()),
            Array::I32(_) => true,
        }
    }

    /// Reorder by `perm` (new position i takes old element perm[i]).
    pub fn permute(&self, perm: &[usize]) -> Array {
        match self {
            Array::F32(v) => Array::F32(perm.iter().map(|&i| v[i]).collect()),
            Array::F64(v) => Array::F64(perm.iter().map(|&i| v[i]).collect()),
            Array::I32(v) => Array::I32(perm.iter().map(|&i| v[i]).collect()),
        }
    }
}

/// Encoding 3 parameters.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Quantized {
    pub scale: f64,
    pub width: usize,
    pub log: bool,
    pub delta: bool,
}

/// Encoding 4 parameters.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Rounded {
    pub bits: u32,
    pub width: usize,
}

/// A core numeric encoding, revision 1.
#[derive(Debug, Clone, Copy, PartialEq)]
#[non_exhaustive]
pub enum Encoding {
    Raw,
    Shuffle,
    DeltaShuffle,
    Quantized(Quantized),
    Rounded(Rounded),
}

impl Encoding {
    pub fn id(&self) -> i64 {
        match self {
            Encoding::Raw => 0,
            Encoding::Shuffle => 1,
            Encoding::DeltaShuffle => 2,
            Encoding::Quantized(_) => 3,
            Encoding::Rounded(_) => 4,
        }
    }

    /// Fidelity flag the descriptor must carry: 0 exact, 1 potentially lossy.
    pub fn fidelity(&self) -> i64 {
        match self {
            Encoding::Raw | Encoding::Shuffle | Encoding::DeltaShuffle => 0,
            Encoding::Quantized(_) | Encoding::Rounded(_) => 1,
        }
    }

    /// The reconstructed type for an input of type `input`, if supported.
    pub fn output_dtype(&self, input: DType) -> Option<DType> {
        match self {
            Encoding::Raw | Encoding::Shuffle | Encoding::DeltaShuffle => Some(input),
            // An int32 input is declared float64 (section 5).
            Encoding::Quantized(_) => Some(if input.is_float() { input } else { DType::F64 }),
            Encoding::Rounded(_) => input.is_float().then_some(input),
        }
    }
}

pub fn valid_width(width: i64) -> bool {
    matches!(width, 1 | 2 | 4 | 8)
}

// ---------------------------------------------------------------------------
// Transforms

pub fn shuffle(bytes: &[u8], width: usize) -> Vec<u8> {
    let n = bytes.len() / width;
    let mut out = vec![0u8; bytes.len()];
    for i in 0..n {
        for lane in 0..width {
            out[lane * n + i] = bytes[i * width + lane];
        }
    }
    out
}

pub fn unshuffle(bytes: &[u8], width: usize) -> Vec<u8> {
    let n = bytes.len() / width;
    let mut out = vec![0u8; bytes.len()];
    for i in 0..n {
        for lane in 0..width {
            out[i * width + lane] = bytes[lane * n + i];
        }
    }
    out
}

fn mask(width: usize) -> u64 {
    if width == 8 {
        u64::MAX
    } else {
        (1u64 << (8 * width)) - 1
    }
}

fn read_words(bytes: &[u8], width: usize) -> Vec<u64> {
    bytes
        .chunks_exact(width)
        .map(|c| {
            let mut w = [0u8; 8];
            w[..width].copy_from_slice(c);
            u64::from_le_bytes(w)
        })
        .collect()
}

fn write_words(words: &[u64], width: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(words.len() * width);
    for w in words {
        out.extend_from_slice(&w.to_le_bytes()[..width]);
    }
    out
}

fn delta(words: &mut [u64], width: usize) {
    let m = mask(width);
    let mut prev = 0u64;
    for w in words.iter_mut() {
        let cur = *w;
        *w = cur.wrapping_sub(prev) & m;
        prev = cur;
    }
}

fn undelta(words: &mut [u64], width: usize) {
    let m = mask(width);
    let mut acc = 0u64;
    for w in words.iter_mut() {
        acc = acc.wrapping_add(*w) & m;
        *w = acc;
    }
}

/// Modular delta then byte shuffle over raw W-byte words (encoding 2).
pub fn delta_shuffle(raw: &[u8], width: usize) -> Vec<u8> {
    let mut words = read_words(raw, width);
    delta(&mut words, width);
    shuffle(&write_words(&words, width), width)
}

/// Inverse of [`delta_shuffle`].
pub fn undelta_unshuffle(blob: &[u8], width: usize) -> Vec<u8> {
    let mut words = read_words(&unshuffle(blob, width), width);
    undelta(&mut words, width);
    write_words(&words, width)
}

/// Round to the nearest integer, ties upward, exactly.
pub fn round_half_up(y: f64) -> f64 {
    let f = y.floor();
    if y - f >= 0.5 { f + 1.0 } else { f }
}

/// Smallest core width holding `max`.
pub fn width_for(max: u64) -> usize {
    match max {
        0..=0xff => 1,
        0x100..=0xffff => 2,
        0x1_0000..=0xffff_ffff => 4,
        _ => 8,
    }
}

// ---------------------------------------------------------------------------
// Encoding 3

/// Quantization indices for `values` (before delta), or an error naming the
/// violated domain.
pub fn quantize_indices(values: &[f64], scale: f64, log: bool) -> Result<Vec<u64>> {
    if !(scale.is_finite() && scale > 0.0) {
        return Err(Error::encode("quantized scale must be finite and positive"));
    }
    let mut out = Vec::with_capacity(values.len());
    for &x in values {
        if !x.is_finite() || x < 0.0 {
            return Err(Error::encode(
                "quantized encoding needs finite nonnegative values",
            ));
        }
        let y = if log { fdlibm::log1p(x) } else { x } * scale;
        let idx = round_half_up(y);
        if idx.is_nan() || idx > MAX_SAFE as f64 {
            return Err(Error::encode("quantized index exceeds 2^53 - 1"));
        }
        out.push(idx as u64);
    }
    Ok(out)
}

/// A binary64 reconstruction as a value of the declared type, widened back.
pub fn in_declared(value: f64, dtype: DType) -> f64 {
    match dtype {
        DType::F32 => value as f32 as f64,
        _ => value,
    }
}

pub fn dequantize(index: u64, scale: f64, log: bool) -> f64 {
    let q = index as f64 / scale;
    if log { fdlibm::expm1(q) } else { q }
}

fn encode_quantized(values: &[f64], p: &Quantized) -> Result<Vec<u8>> {
    let mut words = quantize_indices(values, p.scale, p.log)?;
    let m = mask(p.width);
    if words.iter().any(|&w| w > m) {
        return Err(Error::encode(format!(
            "quantized index does not fit width {}",
            p.width
        )));
    }
    if p.delta {
        delta(&mut words, p.width);
    }
    Ok(shuffle(&write_words(&words, p.width), p.width))
}

fn decode_quantized(blob: &[u8], p: &Quantized) -> Result<Vec<f64>> {
    let mut words = read_words(&unshuffle(blob, p.width), p.width);
    if p.delta {
        undelta(&mut words, p.width);
    }
    let mut out = Vec::with_capacity(words.len());
    for w in words {
        if w > MAX_SAFE as u64 {
            bail!("quantized index exceeds 2^53 - 1");
        }
        let v = dequantize(w, p.scale, p.log);
        if !v.is_finite() {
            bail!("quantized value reconstructs to a non-finite number");
        }
        out.push(v);
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Encoding 4

fn mantissa_bits(dtype: DType) -> Option<u32> {
    match dtype {
        DType::F32 => Some(23),
        DType::F64 => Some(52),
        DType::I32 => None,
    }
}

/// Stored words for encoding 4, before shuffling.
pub fn round_words(array: &Array, bits: u32) -> Result<Vec<u64>> {
    let (m, raw): (u32, Vec<u64>) = match array {
        Array::F32(v) => (23, v.iter().map(|x| x.to_bits() as u64).collect()),
        Array::F64(v) => (52, v.iter().map(|x| x.to_bits()).collect()),
        Array::I32(_) => {
            return Err(Error::encode(
                "rounded floating-point words need float32 or float64",
            ));
        }
    };
    if bits > m {
        return Err(Error::encode(format!("rounded bits must be at most {m}")));
    }
    let d = m - bits;
    let mut out = Vec::with_capacity(raw.len());
    for u in raw {
        let word = if d == 0 {
            u
        } else {
            ((u as u128 + (1u128 << (d - 1))) >> d) as u64
        };
        let back = word << d;
        let finite = if m == 23 {
            f32::from_bits(back as u32).is_finite() && back >> 32 == 0
        } else {
            f64::from_bits(back).is_finite()
        };
        if !finite {
            return Err(Error::encode("rounded value is not finite"));
        }
        out.push(word);
    }
    Ok(out)
}

fn encode_rounded(array: &Array, p: &Rounded) -> Result<Vec<u8>> {
    let words = round_words(array, p.bits)?;
    let m = mask(p.width);
    if words.iter().any(|&w| w > m) {
        return Err(Error::encode(format!(
            "rounded word does not fit width {}",
            p.width
        )));
    }
    Ok(shuffle(&write_words(&words, p.width), p.width))
}

fn decode_rounded(blob: &[u8], dtype: DType, p: &Rounded) -> Result<Array> {
    let m = mantissa_bits(dtype).expect("checked by decode");
    let d = m - p.bits;
    let total = 8 * dtype.size() as u32;
    let words = read_words(&unshuffle(blob, p.width), p.width);
    let limit_bits = total - d; // words must be below 2^limit_bits
    let mut out = Vec::with_capacity(words.len() * dtype.size());
    for w in words {
        if limit_bits < 64 && w >> limit_bits != 0 {
            bail!("rounded word exceeds the declared type");
        }
        let bits = w << d;
        match dtype {
            DType::F32 => {
                let v = f32::from_bits(bits as u32);
                if !v.is_finite() {
                    bail!("rounded reconstruction is not finite");
                }
                out.extend_from_slice(&v.to_le_bytes());
            }
            _ => {
                let v = f64::from_bits(bits);
                if !v.is_finite() {
                    bail!("rounded reconstruction is not finite");
                }
                out.extend_from_slice(&v.to_le_bytes());
            }
        }
    }
    Ok(Array::from_le_bytes(dtype, &out))
}

// ---------------------------------------------------------------------------
// Dispatch

/// Encode `array` with `encoding`. Returns the blob and the reconstructed type.
pub fn encode(array: &Array, encoding: &Encoding) -> Result<(Vec<u8>, DType)> {
    let dtype = array.dtype();
    let w = dtype.size();
    Ok(match encoding {
        Encoding::Raw => (array.to_le_bytes(), dtype),
        Encoding::Shuffle => (shuffle(&array.to_le_bytes(), w), dtype),
        Encoding::DeltaShuffle => (delta_shuffle(&array.to_le_bytes(), w), dtype),
        Encoding::Quantized(p) => {
            if !valid_width(p.width as i64) {
                return Err(Error::encode("quantized width must be 1, 2, 4 or 8"));
            }
            let declared = if dtype.is_float() { dtype } else { DType::F64 };
            (encode_quantized(&array.to_f64(), p)?, declared)
        }
        Encoding::Rounded(p) => {
            if !valid_width(p.width as i64) || p.width > w {
                return Err(Error::encode(
                    "rounded width must be 1, 2, 4 or 8 and at most the type size",
                ));
            }
            (encode_rounded(array, p)?, dtype)
        }
    })
}

/// Decode a blob of `n` elements of declared type `dtype`. Parameters that are
/// out of range for `dtype` are a decode error, never a panic.
pub fn decode(blob: &[u8], n: usize, dtype: DType, encoding: &Encoding) -> Result<Array> {
    match encoding {
        Encoding::Quantized(p) if !valid_width(p.width as i64) => {
            bail!("quantized width must be 1, 2, 4 or 8");
        }
        Encoding::Rounded(p) => {
            let Some(m) = mantissa_bits(dtype) else {
                bail!("rounded encoding needs a float32 or float64 array");
            };
            if !valid_width(p.width as i64) || p.width > dtype.size() {
                bail!("rounded width must be 1, 2, 4 or 8 and at most the type size");
            }
            if p.bits > m {
                bail!("rounded mantissa bits exceed 0..{m} for {}", dtype.name());
            }
        }
        _ => {}
    }
    let word = match encoding {
        Encoding::Quantized(p) => p.width,
        Encoding::Rounded(p) => p.width,
        _ => dtype.size(),
    };
    if blob.len() as u64 != n as u64 * word as u64 {
        if matches!(encoding, Encoding::Rounded(_)) {
            bail!(
                "rounded byte count {} does not match {} words of {} bytes",
                blob.len(),
                n,
                word
            );
        }
        bail!(
            "array byte count {} does not match {} elements of {} bytes",
            blob.len(),
            n,
            word
        );
    }
    let w = dtype.size();
    let array = match encoding {
        Encoding::Raw => Array::from_le_bytes(dtype, blob),
        Encoding::Shuffle => Array::from_le_bytes(dtype, &unshuffle(blob, w)),
        Encoding::DeltaShuffle => Array::from_le_bytes(dtype, &undelta_unshuffle(blob, w)),
        Encoding::Quantized(p) => {
            let wide = decode_quantized(blob, p)?;
            match dtype {
                // Round the binary64 reconstruction to nearest binary32, ties to even.
                DType::F32 => {
                    let narrow: Vec<f32> = wide.iter().map(|&v| v as f32).collect();
                    if !narrow.iter().all(|v| v.is_finite()) {
                        bail!("quantized value reconstructs to a non-finite float32");
                    }
                    Array::F32(narrow)
                }
                _ => Array::F64(wide),
            }
        }
        Encoding::Rounded(p) => decode_rounded(blob, dtype, p)?,
    };
    if !array.all_finite() {
        bail!("array values must be finite");
    }
    Ok(array)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rounding_ties_upward() {
        assert_eq!(round_half_up(0.5), 1.0);
        assert_eq!(round_half_up(1.5), 2.0);
        assert_eq!(round_half_up(2.4999999999999996), 2.0);
        assert_eq!(round_half_up(0.49999999999999994), 0.0);
        assert_eq!(round_half_up(4503599627370497.0), 4503599627370497.0);
    }

    #[test]
    fn out_of_range_parameters_are_errors_not_panics() {
        let rounded = |bits, width| Encoding::Rounded(Rounded { bits, width });
        let quantized = |width| {
            Encoding::Quantized(Quantized {
                scale: 1.0,
                width,
                log: false,
                delta: false,
            })
        };
        for (dtype, encoding) in [
            (DType::I32, rounded(0, 4)),
            (DType::F64, rounded(60, 8)),
            (DType::F32, rounded(24, 4)),
            (DType::F32, rounded(0, 8)),
            (DType::F64, rounded(0, 0)),
            (DType::F64, quantized(0)),
            (DType::F64, quantized(3)),
        ] {
            let e = decode(&[], 0, dtype, &encoding).unwrap_err();
            assert_eq!(e.kind(), crate::ErrorKind::Decode, "{dtype:?} {encoding:?}");
        }
    }

    #[test]
    fn rounded_words_carry_into_exponent() {
        let a = Array::F64(vec![1.9999999999999998, 1.0, -0.0, 3.0]);
        let words = round_words(&a, 0).unwrap();
        assert_eq!(words[0] << 52, 2.0f64.to_bits());
        assert_eq!(words[1] << 52, 1.0f64.to_bits());
        assert_eq!(words[2] << 52, (-0.0f64).to_bits());
        // 3.0 = 1.5 * 2: the half rounds away from zero to 4.0
        assert_eq!(words[3] << 52, 4.0f64.to_bits());
    }
}
