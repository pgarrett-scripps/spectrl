//! The token writer (sections 1, 2 and 6): profiles, canonical order and
//! outer compression.

use crate::cbor::{self, MAX_SAFE, Value};
use crate::codecs::{self, Array, DType, Encoding, Quantized, Rounded, width_for};
use crate::error::{Error, ErrorKind, Result};
use crate::fdlibm;
use crate::framing::{self, MAX_PAYLOAD_BYTES, Mode};
use crate::header::{self, MAX_ELEMENTS, Operation};
use crate::model::*;

/// Outer payload compression requested by a caller.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[non_exhaustive]
pub enum Compression {
    Raw,
    #[default]
    Zlib,
    Brotli,
    /// The smallest complete token among available modes, ties `z`, `r`, `b`.
    Auto,
}

impl Compression {
    pub fn from_name(name: &str) -> Option<Compression> {
        match name {
            "raw" | "r" => Some(Compression::Raw),
            "zlib" | "z" => Some(Compression::Zlib),
            "brotli" | "b" => Some(Compression::Brotli),
            "auto" => Some(Compression::Auto),
            _ => None,
        }
    }
}

/// Writer options.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct EncodeOptions {
    /// Exact encodings only (the lossless profile). The default is the
    /// size-chosen default profile.
    pub lossless: bool,
    pub compression: Compression,
}

fn fail<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::encode(message))
}

/// Write `spectrum` as a token.
pub fn encode(spectrum: &Spectrum, options: EncodeOptions) -> Result<String> {
    let sorted = prepare(spectrum)?;
    let metadata = header::write_metadata(&sorted).map_err(as_encode)?;
    let token_for = |mode: Mode| -> Result<String> {
        let document = document(&sorted, &metadata, options.lossless, mode)?;
        let payload = match mode {
            Mode::Raw => document,
            Mode::Zlib => framing::deflate(&document),
            Mode::Brotli => framing::brotli_compress(&document)?,
        };
        if payload.len() > MAX_PAYLOAD_BYTES {
            return fail("the encoded payload exceeds the 16 MiB limit");
        }
        Ok(framing::frame(mode, &payload))
    };
    match options.compression {
        Compression::Raw => token_for(Mode::Raw),
        Compression::Zlib => token_for(Mode::Zlib),
        Compression::Brotli => token_for(Mode::Brotli),
        Compression::Auto => {
            let mut modes = vec![Mode::Zlib, Mode::Raw];
            if framing::brotli_available() {
                modes.push(Mode::Brotli);
            }
            let mut best: Option<String> = None;
            let mut last_error = None;
            for mode in modes {
                match token_for(mode) {
                    Ok(t) => {
                        if best.as_ref().is_none_or(|b| t.len() < b.len()) {
                            best = Some(t);
                        }
                    }
                    Err(e) => last_error = Some(e),
                }
            }
            best.ok_or_else(|| {
                last_error.unwrap_or_else(|| Error::encode("no payload mode available"))
            })
        }
    }
}

fn as_encode(e: Error) -> Error {
    if e.kind() == ErrorKind::Unsupported {
        e
    } else {
        e.with_kind(ErrorKind::Encode)
    }
}

/// Validate the arrays and apply the stable m/z sort.
fn prepare(spectrum: &Spectrum) -> Result<Spectrum> {
    let n = spectrum.default_array_length;
    if n > MAX_ELEMENTS {
        return fail(format!(
            "array length {n} exceeds the hard ceiling of {MAX_ELEMENTS}"
        ));
    }
    for (key, array) in spectrum.arrays() {
        if array.len() != n {
            return fail(format!(
                "array {key:?} has {} elements, but the array length is {n}",
                array.len()
            ));
        }
        if !array.all_finite() {
            return fail(format!("array {key:?} contains non-finite values"));
        }
    }
    let present: Vec<String> = spectrum
        .arrays()
        .iter()
        .map(|(k, _)| k.to_string())
        .collect();
    for (what, keys) in [
        (
            "array_names",
            spectrum.array_names.keys().collect::<Vec<_>>(),
        ),
        ("array_units", spectrum.array_units.keys().collect()),
        ("array_params", spectrum.array_params.keys().collect()),
        (
            "array_user_params",
            spectrum.array_user_params.keys().collect(),
        ),
        (
            "array_processing",
            spectrum.array_processing.keys().collect(),
        ),
        (
            "array_extensions",
            spectrum.array_extensions.keys().collect(),
        ),
    ] {
        if let Some(k) = keys.iter().find(|k| !present.contains(k)) {
            return fail(format!("{what} names absent array {k:?}"));
        }
    }
    let mut out = spectrum.clone();
    if let Some(mz) = &spectrum.mz {
        let values = mz.to_f64();
        if values.iter().any(|&v| v < 0.0) {
            return fail("m/z array contains negative values");
        }
        let mut perm: Vec<usize> = (0..n).collect();
        perm.sort_by(|&a, &b| values[a].partial_cmp(&values[b]).expect("finite"));
        if perm.iter().enumerate().any(|(i, &p)| i != p) {
            for key in ["mz", "intensity", "charge"] {
                if let Some(slot) = out.core_mut(key) {
                    if let Some(a) = slot.as_ref() {
                        *slot = Some(a.permute(&perm));
                    }
                }
            }
            for a in out.extra_arrays.values_mut() {
                *a = a.permute(&perm);
            }
        }
    }
    Ok(out)
}

/// The complete CBOR document for one payload mode.
fn document(
    spectrum: &Spectrum,
    metadata: &[(Value, Value)],
    lossless: bool,
    mode: Mode,
) -> Result<Vec<u8>> {
    let mut descriptors = Vec::new();
    for (key, array) in spectrum.arrays() {
        let (encoding, blob, dtype) = choose(key, array, lossless, mode)?;
        let operation = Operation::from_encoding(&encoding);
        descriptors.push(
            header::write_descriptor(spectrum, key, dtype, &operation, encoding.fidelity(), blob)
                .map_err(as_encode)?,
        );
    }
    let mut root = metadata.to_vec();
    root.push((Value::Int(6), Value::Array(descriptors)));
    let bytes = cbor::encode(&Value::Map(root)).map_err(as_encode)?;
    if bytes.len() > MAX_PAYLOAD_BYTES {
        return fail("the CBOR document exceeds the 16 MiB limit");
    }
    // Everything written must be readable: run the reader's own validation.
    let parsed = cbor::decode(&bytes).map_err(as_encode)?;
    header::read_header(&parsed).map_err(as_encode)?;
    Ok(bytes)
}

fn exact(key: &str) -> Encoding {
    match key {
        "mz" => Encoding::DeltaShuffle,
        "intensity" => Encoding::Shuffle,
        _ => Encoding::Raw,
    }
}

/// Pick the encoding for one array and return it with its blob and the
/// declared reconstructed type.
fn choose(
    key: &str,
    array: &Array,
    lossless: bool,
    mode: Mode,
) -> Result<(Encoding, Vec<u8>, DType)> {
    let fallback = exact(key);
    let floating = array.dtype().is_float();
    let candidates: Vec<Encoding> = if lossless || !floating {
        vec![]
    } else {
        let values = array.to_f64();
        match key {
            "mz" => mz_candidate(&values, array.dtype()).into_iter().collect(),
            "intensity" if values.iter().all(|&v| v >= 0.0) => intensity_candidates(array, &values),
            _ => vec![],
        }
    };
    let (blob, dtype) = codecs::encode(array, &fallback)?;
    let mut best = (fallback, measure(&blob, mode), blob, dtype);
    for candidate in candidates {
        let Ok((blob, dtype)) = codecs::encode(array, &candidate) else {
            continue;
        };
        let size = measure(&blob, mode);
        if size < best.1 {
            best = (candidate, size, blob, dtype);
        }
    }
    Ok((best.0, best.2, best.3))
}

fn measure(blob: &[u8], mode: Mode) -> usize {
    match mode {
        Mode::Raw => blob.len(),
        _ => framing::deflate(blob).len(),
    }
}

fn smallest_positive(values: &[f64]) -> Option<f64> {
    values.iter().copied().filter(|&v| v > 0.0).reduce(f64::min)
}

/// Quantized parameters with the smallest width, or `None` when an index is
/// out of domain.
fn quantized(values: &[f64], scale: f64, log: bool, delta: bool) -> Option<Quantized> {
    if !(scale.is_finite() && scale > 0.0 && scale <= MAX_SAFE as f64) {
        return None;
    }
    let indices = codecs::quantize_indices(values, scale, log).ok()?;
    let width = width_for(indices.iter().copied().max().unwrap_or(0));
    Some(Quantized {
        scale,
        width,
        log,
        delta,
    })
}

/// A quantized index's reconstruction in the declared type (section 5).
fn reconstructed(index: f64, scale: f64, log: bool, dtype: DType) -> f64 {
    codecs::in_declared(codecs::dequantize(index as u64, scale, log), dtype)
}

/// Whether `y`, the declared-type reconstruction of `x` on a log grid, is within
/// the grid's rounding bound, grown for the final float32 rounding (section 5).
fn within_grid(x: f64, y: f64, scale: f64, dtype: DType) -> bool {
    let slack = if dtype == DType::F32 {
        (y * 2f64.powi(-24)).max(2f64.powi(-150))
    } else {
        0.0
    };
    (y - x).abs() <= (x + 1.0) * fdlibm::expm1(0.5 / scale) + slack
}

/// The 0.1 ppm logarithmic m/z candidate, if every value in the declared type
/// passes both the grid bound (section 5) and the 0.1 ppm bound (section 6).
fn mz_candidate(values: &[f64], dtype: DType) -> Option<Encoding> {
    let m = smallest_positive(values).unwrap_or(1.0);
    let r = 0.1e-6 * (1.0 - 1e-7);
    // Grouped as the reference implementations evaluate it; (r * m) / (m + 1)
    // rounds differently for about one m in 10^9 and moves the scale by one.
    let scale = (0.5 / fdlibm::log1p(r * (m / (m + 1.0)))).ceil();
    let q = quantized(values, scale, true, true)?;
    let ok = values.iter().all(|&x| {
        let back = reconstructed(
            codecs::round_half_up(fdlibm::log1p(x) * scale),
            scale,
            true,
            dtype,
        );
        within_grid(x, back, scale, dtype) && (back - x).abs() <= 0.1e-6 * x
    });
    ok.then_some(Encoding::Quantized(q))
}

/// Default-profile intensity candidates after exact byte shuffle, in tie order.
fn intensity_candidates(array: &Array, values: &[f64]) -> Vec<Encoding> {
    let mut out = Vec::new();
    if values
        .iter()
        .all(|&v| v.fract() == 0.0 && v <= MAX_SAFE as f64)
    {
        if let Some(q) = quantized(values, 1.0, false, false) {
            out.push(Encoding::Quantized(q));
        }
    }
    if let Ok(words) = codecs::round_words(array, 12) {
        let width = width_for(words.iter().copied().max().unwrap_or(0));
        if width <= array.dtype().size() {
            out.push(Encoding::Rounded(Rounded { bits: 12, width }));
        }
    }
    let scale = match smallest_positive(values) {
        Some(m) if m < 1.0 => 3600f64.max((3600.0 / 2.0 * (m + 1.0) / m).ceil()),
        _ => 3600.0,
    };
    if let Some(q) = quantized(values, scale, true, false) {
        let dtype = array.dtype();
        let relative = 2.0 * fdlibm::expm1(0.5 / 3600.0);
        let bound_ok = values.iter().all(|&x| {
            let y = reconstructed(
                codecs::round_half_up(fdlibm::log1p(x) * scale),
                scale,
                true,
                dtype,
            );
            // The grid bound (section 5) and the profile's relative bound
            // (section 6), both in the declared type.
            within_grid(x, y, scale, dtype) && (y - x).abs() <= x * relative
        });
        if bound_ok {
            out.push(Encoding::Quantized(q));
        }
    }
    out
}
