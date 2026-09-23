//! The decoded spectrum model (sections 2, 3, 7 and 8).
//!
//! Field names follow the reference JSON interchange (`spectrum_to_dict`), so
//! [`crate::json`] maps them one to one.

use std::collections::BTreeMap;

use crate::cbor::Value;
use crate::codecs::Array;

/// A CV or user parameter value: null (a flag), a finite number, or text.
#[derive(Debug, Clone, PartialEq)]
pub enum Scalar {
    Null,
    Number(f64),
    Text(String),
}

/// One `[accession, value]` pair with an optional unit.
#[derive(Debug, Clone, PartialEq)]
pub struct CvParam {
    pub accession: String,
    pub value: Scalar,
    pub unit_accession: Option<String>,
}

impl CvParam {
    pub fn new(accession: impl Into<String>, value: Scalar) -> Self {
        CvParam {
            accession: accession.into(),
            value,
            unit_accession: None,
        }
    }
}

/// `{"n": name, "v": value?, "u": unit?}`.
#[derive(Debug, Clone, PartialEq)]
pub struct UserParam {
    pub name: String,
    pub value: Scalar,
    pub unit_accession: Option<String>,
}

/// A parameter group: scan windows, isolation windows, selected ions, activation.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Group {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Scan {
    pub params: Vec<CvParam>,
    pub windows: Vec<Group>,
    pub user_params: Vec<UserParam>,
    pub source: Option<Source>,
    pub acquisition: Option<Acquisition>,
    pub processing: Vec<Processing>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Precursor {
    pub isolation_window: Option<Group>,
    pub selected_ions: Vec<Group>,
    pub activation: Option<Group>,
    pub source: Option<Source>,
    pub acquisition: Option<Acquisition>,
    pub processing: Vec<Processing>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Product {
    pub isolation_window: Option<Group>,
}

/// Record key 0..7 (source allows 0, 1, 2, 3, 5, 6, 7).
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Source {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub id: Option<String>,
    pub name: Option<String>,
    pub location: Option<String>,
    pub external_ids: Vec<String>,
    pub spectrum_ref: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Acquisition {
    pub instrument: Option<Instrument>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Instrument {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub id: Option<String>,
    pub name: Option<String>,
    pub components: Vec<Component>,
    pub software: Option<Software>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Component {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub kind: Option<String>,
    pub order: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Software {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub id: Option<String>,
    pub name: Option<String>,
    pub version: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Default)]
pub struct Processing {
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub software: Option<Software>,
    pub operation: Option<String>,
    pub revision: Option<i64>,
    /// String-keyed map; `None` when absent.
    pub parameters: Option<Vec<(String, Value)>>,
    pub source_params: Vec<CvParam>,
}

/// `{"revision", "required", "data"}`.
#[derive(Debug, Clone, PartialEq)]
pub struct Extension {
    pub revision: i64,
    pub required: bool,
    pub data: Value,
}

pub type Extensions = Vec<(String, Extension)>;

/// One spectrum with its arrays and metadata.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Spectrum {
    pub default_array_length: usize,
    pub id: Option<String>,
    pub mz: Option<Array>,
    pub intensity: Option<Array>,
    pub charge: Option<Array>,
    /// Keyed by `MS:xxxxxxx` for standard arrays or the name for nonstandard ones.
    pub extra_arrays: BTreeMap<String, Array>,
    pub params: Vec<CvParam>,
    pub scans: Vec<Scan>,
    pub scan_combination: Option<String>,
    pub precursors: Vec<Precursor>,
    pub products: Vec<Product>,
    pub user_params: Vec<UserParam>,
    pub source: Option<Source>,
    pub acquisition: Option<Acquisition>,
    pub processing: Vec<Processing>,
    pub extensions: Extensions,
    pub cv_versions: Vec<(String, String)>,
    /// Per-array metadata keyed by `mz`, `intensity`, `charge` or the extra key.
    pub array_names: BTreeMap<String, String>,
    pub array_units: BTreeMap<String, String>,
    pub array_params: BTreeMap<String, Vec<CvParam>>,
    pub array_user_params: BTreeMap<String, Vec<UserParam>>,
    pub array_processing: BTreeMap<String, Vec<Processing>>,
    pub array_extensions: BTreeMap<String, Extensions>,
}

pub const CORE_ARRAYS: [(&str, i64); 3] =
    [("mz", 1000514), ("intensity", 1000515), ("charge", 1000516)];
pub const NONSTANDARD_ARRAY: i64 = 1000786;

impl Spectrum {
    pub fn new(default_array_length: usize) -> Self {
        Spectrum {
            default_array_length,
            ..Default::default()
        }
    }

    pub fn core(&self, key: &str) -> Option<&Array> {
        match key {
            "mz" => self.mz.as_ref(),
            "intensity" => self.intensity.as_ref(),
            "charge" => self.charge.as_ref(),
            _ => None,
        }
    }

    pub fn core_mut(&mut self, key: &str) -> Option<&mut Option<Array>> {
        match key {
            "mz" => Some(&mut self.mz),
            "intensity" => Some(&mut self.intensity),
            "charge" => Some(&mut self.charge),
            _ => None,
        }
    }

    /// Present arrays in canonical writer order: m/z, intensity, charge,
    /// then extra arrays by key in Unicode scalar-value order.
    pub fn arrays(&self) -> Vec<(&str, &Array)> {
        let mut out = Vec::new();
        for (key, _) in CORE_ARRAYS {
            if let Some(a) = self.core(key) {
                out.push((key, a));
            }
        }
        for (key, a) in &self.extra_arrays {
            out.push((key.as_str(), a));
        }
        out
    }
}

/// Seven-digit accession text for an ontology prefix and tail.
pub fn accession(prefix: &str, tail: i64) -> String {
    format!("{prefix}:{tail:07}")
}

/// `[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+`
pub fn is_accession(text: &str) -> bool {
    let Some((prefix, local)) = text.split_once(':') else {
        return false;
    };
    is_prefix(prefix) && !local.is_empty() && local.bytes().all(|b| b.is_ascii_alphanumeric())
}

/// `[A-Za-z][A-Za-z0-9]*`
pub fn is_prefix(text: &str) -> bool {
    let mut bytes = text.bytes();
    matches!(bytes.next(), Some(b) if b.is_ascii_alphabetic())
        && bytes.all(|b| b.is_ascii_alphanumeric())
}

/// `[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+`
pub fn is_namespaced(text: &str) -> bool {
    let Some((ns, local)) = text.split_once(':') else {
        return false;
    };
    let mut first = ns.bytes();
    matches!(first.next(), Some(b) if b.is_ascii_alphabetic())
        && first.all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'_' || b == b'-')
        && !local.is_empty()
        && local
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'/' | b'-'))
}

/// `PREFIX:ddddddd` with exactly seven digits, split.
pub fn seven_digit(text: &str) -> Option<(&str, i64)> {
    let (prefix, local) = text.split_once(':')?;
    if is_prefix(prefix) && local.len() == 7 && local.bytes().all(|b| b.is_ascii_digit()) {
        Some((prefix, local.parse().ok()?))
    } else {
        None
    }
}
