//! An independent Rust implementation of the `spectrl.v3` single-spectrum
//! token format.
//!
//! A token is `spectrl.v3.<mode>.<base64url(payload)>.<crc32>`: one mass
//! spectrum's arrays and modeled mzML metadata in a URL-safe string that
//! decodes with no lookup service. This crate was written from
//! `SPECIFICATION.md`, `schema/registry.json` and the shared test vectors, not
//! from the Python or TypeScript sources, and produces byte-identical tokens.
//!
//! ```
//! use spectrl::{Array, EncodeOptions, Spectrum, decode_token, encode_spectrum};
//!
//! let mut s = Spectrum::new(3);
//! s.mz = Some(Array::F64(vec![100.0, 200.5, 300.25]));
//! s.intensity = Some(Array::F32(vec![10.0, 20.0, 5.0]));
//! let token = encode_spectrum(&s, EncodeOptions { lossless: true, ..Default::default() }).unwrap();
//! let back = decode_token(&token).unwrap();
//! assert_eq!(back.spectrum.mz, s.mz);
//! ```

#![forbid(unsafe_code)]

pub mod base64url;
// Wire-level building blocks shared with the CLI and the conformance tests.
// They are public for those callers, not part of the stable API.
#[doc(hidden)]
pub mod cbor;
pub mod codecs;
pub mod error;
pub mod fdlibm;
#[doc(hidden)]
pub mod framing;
#[doc(hidden)]
pub mod header;
#[doc(hidden)]
pub mod json;
pub mod model;
pub mod writer;

pub use codecs::{Array, DType, Encoding, Quantized, Rounded};
pub use error::{Error, ErrorKind, Result};
pub use framing::Mode;
pub use header::Operation;
pub use model::*;
pub use writer::{Compression, EncodeOptions, encode as encode_spectrum};

use header::{Descriptor, Header, OpId};

/// Reader resource budgets (section 8). The defaults match the reference
/// implementations; [`Budgets::ceilings`] raises them to the hard limits for
/// trusted producers.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Budgets {
    pub max_token_chars: usize,
    pub max_peaks: usize,
    pub max_arrays: usize,
    pub max_array_bytes: usize,
}

impl Default for Budgets {
    fn default() -> Self {
        Budgets {
            max_token_chars: 4 * 1024 * 1024,
            max_peaks: 1_000_000,
            max_arrays: 64,
            max_array_bytes: 64 * 1024 * 1024,
        }
    }
}

impl Budgets {
    /// The hard ceilings only.
    pub fn ceilings() -> Self {
        Budgets {
            max_token_chars: usize::MAX,
            max_peaks: header::MAX_ELEMENTS,
            max_arrays: usize::MAX,
            max_array_bytes: usize::MAX,
        }
    }
}

/// A decoded token.
#[derive(Debug, Clone, PartialEq)]
#[non_exhaustive]
pub struct Decoded {
    pub spectrum: Spectrum,
    /// The eight-character checksum as received.
    pub checksum: String,
    pub mode: framing::Mode,
}

/// One array as seen by [`inspect_token`], without decoding its values.
#[derive(Debug, Clone, PartialEq)]
#[non_exhaustive]
pub struct ArrayInfo {
    /// `mz`, `intensity`, `charge`, `MS:xxxxxxx` or the nonstandard name.
    pub key: String,
    pub array_type: String,
    pub name: Option<String>,
    pub dtype: DType,
    pub operation: header::Operation,
    pub fidelity: i64,
    /// Whether this reader implements the encoding.
    pub available: bool,
    pub byte_count: usize,
    pub unit: Option<String>,
}

fn header_of<'a>(token: &'a str, budgets: &Budgets) -> Result<(Header, framing::Frame<'a>)> {
    if token.len() > budgets.max_token_chars {
        return Err(Error::decode(format!(
            "token length {} exceeds the budget of {} characters",
            token.len(),
            budgets.max_token_chars
        )));
    }
    let frame = framing::split(token)?;
    let bytes = framing::expand(&frame)?;
    let root = cbor::decode(&bytes)?;
    let header = header::read_header(&root)?;
    check_budgets(&header, budgets)?;
    Ok((header, frame))
}

fn check_budgets(h: &Header, b: &Budgets) -> Result<()> {
    let n = h.spectrum.default_array_length;
    if n > b.max_peaks {
        return Err(Error::decode(format!(
            "array length {n} exceeds the peak budget of {}",
            b.max_peaks
        )));
    }
    if h.descriptors.len() > b.max_arrays {
        return Err(Error::decode(format!(
            "{} arrays exceed the array budget of {}",
            h.descriptors.len(),
            b.max_arrays
        )));
    }
    let total: u128 = h
        .descriptors
        .iter()
        .map(|d| n as u128 * d.dtype.size() as u128)
        .sum();
    if total > b.max_array_bytes as u128 {
        return Err(Error::decode(format!(
            "reconstructed arrays ({total} bytes) exceed the budget of {} bytes",
            b.max_array_bytes
        )));
    }
    Ok(())
}

/// Decode a token with the default budgets.
pub fn decode_token(token: &str) -> Result<Decoded> {
    decode_token_with(token, &Budgets::default())
}

/// Decode a token with explicit budgets.
pub fn decode_token_with(token: &str, budgets: &Budgets) -> Result<Decoded> {
    let (header, frame) = header_of(token, budgets)?;
    let checksum = frame.checksum.to_string();
    let mode = frame.mode;
    let Header {
        mut spectrum,
        descriptors,
    } = header;
    if let Some((name, _)) = spectrum.extensions.iter().find(|(_, e)| e.required) {
        return Err(Error::unsupported(format!(
            "required extension {name:?} is not supported by this reader"
        )));
    }
    let n = spectrum.default_array_length;
    for d in descriptors {
        place(&mut spectrum, d, n)?;
    }
    Ok(Decoded {
        spectrum,
        checksum,
        mode,
    })
}

fn place(spectrum: &mut Spectrum, d: Descriptor, n: usize) -> Result<()> {
    if let Some((name, _)) = d.extensions.iter().find(|(_, e)| e.required) {
        return Err(Error::unsupported(format!(
            "array {:?} requires extension {name:?}, which this reader does not support",
            d.key
        )));
    }
    let Some(encoding) = &d.encoding else {
        let id = match &d.operation.id {
            OpId::Builtin(i) => i.to_string(),
            OpId::Named(s) => s.clone(),
        };
        return Err(Error::unsupported(format!(
            "array {:?} uses encoding {id} revision {}, which this reader does not implement",
            d.key, d.operation.revision
        )));
    };
    let array = codecs::decode(&d.blob, n, d.dtype, encoding)?;
    if !array.all_finite() {
        return Err(Error::decode(format!(
            "array {:?} contains non-finite values",
            d.key
        )));
    }
    if d.key == "mz" && array.to_f64().iter().any(|&v| v < 0.0) {
        return Err(Error::decode("m/z array contains negative values"));
    }
    let key = d.key.clone();
    if let Some(name) = d.name {
        spectrum.array_names.insert(key.clone(), name);
    }
    if let Some(unit) = d.unit {
        spectrum.array_units.insert(key.clone(), unit);
    }
    if !d.params.is_empty() {
        spectrum.array_params.insert(key.clone(), d.params);
    }
    if !d.user_params.is_empty() {
        spectrum
            .array_user_params
            .insert(key.clone(), d.user_params);
    }
    let mut processing = d.processing;
    if d.fidelity == 1 {
        let mut records = processing.unwrap_or_else(|| spectrum.processing.clone());
        records.push(header::lossy_record(&d.operation));
        processing = Some(records);
    }
    if let Some(p) = processing {
        spectrum.array_processing.insert(key.clone(), p);
    }
    if !d.extensions.is_empty() {
        spectrum.array_extensions.insert(key.clone(), d.extensions);
    }
    match spectrum.core_mut(&key) {
        Some(slot) => *slot = Some(array),
        None => {
            spectrum.extra_arrays.insert(key, array);
        }
    }
    Ok(())
}

/// Validate a token and list its arrays without decoding values. Unknown
/// encodings and required extensions are reported, not rejected.
pub fn inspect_token(token: &str) -> Result<Vec<ArrayInfo>> {
    inspect_token_with(token, &Budgets::default())
}

pub fn inspect_token_with(token: &str, budgets: &Budgets) -> Result<Vec<ArrayInfo>> {
    let (header, _) = header_of(token, budgets)?;
    Ok(header
        .descriptors
        .into_iter()
        .map(|d| ArrayInfo {
            array_type: accession("MS", d.array_tail),
            available: d.encoding.is_some() && !d.extensions.iter().any(|(_, e)| e.required),
            byte_count: d.blob.len(),
            key: d.key,
            name: d.name,
            dtype: d.dtype,
            operation: d.operation,
            fidelity: d.fidelity,
            unit: d.unit,
        })
        .collect())
}
