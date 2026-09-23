//! The CBOR header (sections 2, 3, 4, 7, 8): wire form to model and back.

use crate::cbor::{MAX_SAFE, Value};
use crate::codecs::{DType, Encoding, Quantized, Rounded, valid_width};
use crate::error::{Error, Result};
use crate::model::*;

/// Hard ceiling on key 0 (section 8).
pub const MAX_ELEMENTS: usize = 4_000_000;
/// Hard ceiling on one array's intermediate bytes (section 8).
pub const MAX_BLOB_BYTES: usize = 64 * 1024 * 1024;
const MAX_TAIL: i64 = 9_999_999;

fn err<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::decode(message))
}

/// An operation identifier: a built-in integer or a namespaced string.
#[derive(Debug, Clone, PartialEq)]
pub enum OpId {
    Builtin(i64),
    Named(String),
}

/// `[identifier, revision, parameters?]` as it appears on the wire.
#[derive(Debug, Clone, PartialEq)]
pub struct Operation {
    pub id: OpId,
    pub revision: i64,
    pub parameters: Option<Vec<(String, Value)>>,
}

impl Operation {
    pub fn to_value(&self) -> Value {
        let mut out = vec![
            match &self.id {
                OpId::Builtin(i) => Value::Int(*i),
                OpId::Named(s) => Value::text(s.clone()),
            },
            Value::Int(self.revision),
        ];
        if let Some(p) = &self.parameters {
            out.push(Value::Map(
                p.iter()
                    .map(|(k, v)| (Value::text(k.clone()), v.clone()))
                    .collect(),
            ));
        }
        Value::Array(out)
    }

    /// The operation for a core encoding, revision 1.
    pub fn from_encoding(encoding: &Encoding) -> Operation {
        let parameters = match encoding {
            Encoding::Quantized(q) => {
                let mut p = vec![
                    ("scale".to_string(), Value::Float(q.scale)),
                    ("width".to_string(), Value::Int(q.width as i64)),
                ];
                if q.log {
                    p.push(("log".to_string(), Value::Bool(true)));
                }
                if q.delta {
                    p.push(("delta".to_string(), Value::Bool(true)));
                }
                Some(p)
            }
            Encoding::Rounded(r) => Some(vec![
                ("bits".to_string(), Value::Int(r.bits as i64)),
                ("width".to_string(), Value::Int(r.width as i64)),
            ]),
            _ => None,
        };
        Operation {
            id: OpId::Builtin(encoding.id()),
            revision: 1,
            parameters,
        }
    }
}

/// One array descriptor, validated but not decoded.
#[derive(Debug, Clone)]
pub struct Descriptor {
    /// `mz`, `intensity`, `charge`, `MS:xxxxxxx` or the nonstandard name.
    pub key: String,
    pub dtype: DType,
    pub array_tail: i64,
    pub operation: Operation,
    /// `None` for an unknown encoding or revision.
    pub encoding: Option<Encoding>,
    pub fidelity: i64,
    pub name: Option<String>,
    pub blob: Vec<u8>,
    pub unit: Option<String>,
    pub params: Vec<CvParam>,
    pub user_params: Vec<UserParam>,
    pub processing: Option<Vec<Processing>>,
    pub extensions: Extensions,
}

/// A parsed header: metadata in a [`Spectrum`] with no arrays, plus descriptors.
#[derive(Debug, Clone)]
pub struct Header {
    pub spectrum: Spectrum,
    pub descriptors: Vec<Descriptor>,
}

// ---------------------------------------------------------------------------
// Reading

fn int_fields<'a>(value: &'a Value, what: &str, allowed: &[i64]) -> Result<Vec<(i64, &'a Value)>> {
    let Some(entries) = value.as_map() else {
        return err(format!("{what} must be a map, not {}", value.type_name()));
    };
    let mut out = Vec::with_capacity(entries.len());
    for (k, v) in entries {
        match k {
            Value::Int(i) if allowed.contains(i) => out.push((*i, v)),
            _ => return err(format!("unknown {what} key {}", show_key(k))),
        }
    }
    Ok(out)
}

fn text_fields<'a>(
    value: &'a Value,
    what: &str,
    allowed: &[&str],
) -> Result<Vec<(&'a str, &'a Value)>> {
    let Some(entries) = value.as_map() else {
        return err(format!("{what} must be a map, not {}", value.type_name()));
    };
    let mut out = Vec::with_capacity(entries.len());
    for (k, v) in entries {
        match k {
            Value::Text(s) if allowed.contains(&s.as_str()) => out.push((s.as_str(), v)),
            _ => return err(format!("unknown {what} key {}", show_key(k))),
        }
    }
    Ok(out)
}

fn show_key(k: &Value) -> String {
    match k {
        Value::Int(i) => i.to_string(),
        Value::Text(s) => format!("{s:?}"),
        other => other.type_name().to_string(),
    }
}

fn list<'a>(value: &'a Value, what: &str) -> Result<&'a [Value]> {
    value
        .as_array()
        .ok_or_else(|| Error::decode(format!("{what} must be a list, not {}", value.type_name())))
}

fn text(value: &Value, what: &str) -> Result<String> {
    match value {
        Value::Text(s) => Ok(s.clone()),
        other => err(format!("{what} must be text, not {}", other.type_name())),
    }
}

fn nonempty_text(value: &Value, what: &str) -> Result<String> {
    let s = text(value, what)?;
    if s.is_empty() {
        return err(format!("{what} must be nonempty text"));
    }
    Ok(s)
}

fn tail(value: &Value, what: &str) -> Result<i64> {
    match value {
        Value::Int(i) if (0..=MAX_TAIL).contains(i) => Ok(*i),
        _ => err(format!("{what} must be an accession tail in 0..9999999")),
    }
}

fn positive(value: &Value, what: &str) -> Result<i64> {
    match value {
        Value::Int(i) if *i >= 1 => Ok(*i),
        _ => err(format!("{what} must be a positive integer")),
    }
}

/// Parameter accession: an MS tail or accession-shaped text.
fn read_accession(value: &Value) -> Result<String> {
    match value {
        Value::Int(_) => Ok(accession("MS", tail(value, "CV parameter accession")?)),
        Value::Text(s) if is_accession(s) => Ok(s.clone()),
        Value::Text(s) => err(format!("invalid CV parameter accession {s:?}")),
        other => err(format!(
            "CV parameter accession must be a tail or text, not {}",
            other.type_name()
        )),
    }
}

/// Section 3 unit wire forms.
pub fn read_unit(value: &Value) -> Result<String> {
    match value {
        Value::Int(_) => Ok(accession("UO", tail(value, "unit accession")?)),
        Value::Array(pair) => match pair.as_slice() {
            [Value::Text(prefix), t @ Value::Int(_)] if is_prefix(prefix) => {
                Ok(accession(prefix, tail(t, "unit accession")?))
            }
            _ => err("invalid unit: an ontology pair must be [prefix, tail]"),
        },
        Value::Text(s) if is_accession(s) => Ok(s.clone()),
        Value::Text(s) => err(format!("invalid unit accession {s:?}")),
        other => err(format!(
            "invalid unit: {} is not a unit wire form",
            other.type_name()
        )),
    }
}

fn read_scalar(value: &Value) -> Result<Scalar> {
    match value {
        Value::Null => Ok(Scalar::Null),
        Value::Int(i) => Ok(Scalar::Number(*i as f64)),
        Value::Float(f) => Ok(Scalar::Number(*f)),
        Value::Text(s) => Ok(Scalar::Text(s.clone())),
        Value::Bool(_) => {
            err("parameter value must be null, a number or text, not a boolean (use 0 or 1)")
        }
        other => err(format!(
            "parameter value must be null, a number or text, not {}",
            other.type_name()
        )),
    }
}

pub fn read_params(value: &Value) -> Result<Vec<CvParam>> {
    let mut out = Vec::new();
    for pair in list(value, "CV parameters")? {
        let Some([acc, v]) = pair
            .as_array()
            .and_then(|p| <&[Value; 2]>::try_from(p).ok())
        else {
            return err("a CV parameter must be an [accession, value] pair");
        };
        let accession = read_accession(acc)?;
        let (value, unit_accession) = match v {
            Value::Array(inner) => match inner.as_slice() {
                [val, unit] => (read_scalar(val)?, Some(read_unit(unit)?)),
                _ => return err("a CV value with a unit must be a [value, unit] pair"),
            },
            other => (read_scalar(other)?, None),
        };
        out.push(CvParam {
            accession,
            value,
            unit_accession,
        });
    }
    Ok(out)
}

pub fn read_user_params(value: &Value) -> Result<Vec<UserParam>> {
    let mut out = Vec::new();
    for item in list(value, "user parameters")? {
        let mut name = None;
        let mut val = Scalar::Null;
        let mut unit = None;
        for (k, v) in text_fields(item, "user parameter", &["n", "v", "u"])? {
            match k {
                "n" => name = Some(nonempty_text(v, "user parameter name")?),
                "v" => val = read_scalar(v)?,
                _ => unit = Some(read_unit(v)?),
            }
        }
        let Some(name) = name else {
            return err("a user parameter needs a nonempty name");
        };
        out.push(UserParam {
            name,
            value: val,
            unit_accession: unit,
        });
    }
    Ok(out)
}

fn read_group(value: &Value) -> Result<Group> {
    let mut g = Group::default();
    for (k, v) in int_fields(value, "parameter group", &[0, 1])? {
        match k {
            0 => g.params = read_params(v)?,
            _ => g.user_params = read_user_params(v)?,
        }
    }
    Ok(g)
}

fn read_groups(value: &Value) -> Result<Vec<Group>> {
    list(value, "parameter groups")?
        .iter()
        .map(read_group)
        .collect()
}

fn read_source(value: &Value) -> Result<Source> {
    let mut s = Source::default();
    for (k, v) in int_fields(value, "source record", &[0, 1, 2, 3, 5, 6, 7])? {
        if matches!(v, Value::Null) && matches!(k, 2 | 3 | 5 | 6 | 7) {
            continue; // a null leaf field reads as absent
        }
        match k {
            0 => s.params = read_params(v)?,
            1 => s.user_params = read_user_params(v)?,
            2 => s.id = Some(text(v, "source id")?),
            3 => s.name = Some(text(v, "source name")?),
            5 => s.location = Some(text(v, "source location")?),
            6 => {
                s.external_ids = list(v, "external IDs")?
                    .iter()
                    .map(|x| nonempty_text(x, "external ID"))
                    .collect::<Result<_>>()?
            }
            _ => s.spectrum_ref = Some(text(v, "spectrum reference")?),
        }
    }
    Ok(s)
}

fn read_software(value: &Value) -> Result<Software> {
    let mut s = Software::default();
    for (k, v) in int_fields(value, "software record", &[0, 1, 2, 3, 4])? {
        if matches!(v, Value::Null) && matches!(k, 2..=4) {
            continue; // a null leaf field reads as absent
        }
        match k {
            0 => s.params = read_params(v)?,
            1 => s.user_params = read_user_params(v)?,
            2 => s.id = Some(text(v, "software id")?),
            3 => s.name = Some(text(v, "software name")?),
            _ => s.version = Some(text(v, "software version")?),
        }
    }
    Ok(s)
}

fn read_component(value: &Value) -> Result<Component> {
    let mut c = Component::default();
    for (k, v) in int_fields(value, "component record", &[0, 1, 10, 11])? {
        if matches!(v, Value::Null) && matches!(k, 10 | 11) {
            continue; // a null leaf field reads as absent
        }
        match k {
            0 => c.params = read_params(v)?,
            1 => c.user_params = read_user_params(v)?,
            10 => {
                let kind = text(v, "component kind")?;
                if !matches!(kind.as_str(), "source" | "analyzer" | "detector") {
                    return err(format!(
                        "component kind must be source, analyzer or detector, not {kind:?}"
                    ));
                }
                c.kind = Some(kind);
            }
            _ => match v {
                Value::Int(i) if *i >= 0 => c.order = Some(*i),
                _ => return err("component order must be a nonnegative integer"),
            },
        }
    }
    Ok(c)
}

fn read_instrument(value: &Value) -> Result<Instrument> {
    let mut s = Instrument::default();
    for (k, v) in int_fields(value, "instrument record", &[0, 1, 2, 3, 9, 12])? {
        if matches!(v, Value::Null) && matches!(k, 2 | 3) {
            continue; // a null leaf field reads as absent
        }
        match k {
            0 => s.params = read_params(v)?,
            1 => s.user_params = read_user_params(v)?,
            2 => s.id = Some(text(v, "instrument id")?),
            3 => s.name = Some(text(v, "instrument name")?),
            9 => {
                s.components = list(v, "components")?
                    .iter()
                    .map(read_component)
                    .collect::<Result<_>>()?
            }
            _ => s.software = Some(read_software(v)?),
        }
    }
    Ok(s)
}

fn read_acquisition(value: &Value) -> Result<Acquisition> {
    let mut a = Acquisition::default();
    for (_, v) in int_fields(value, "acquisition record", &[8])? {
        a.instrument = Some(read_instrument(v)?);
    }
    Ok(a)
}

fn read_string_map(value: &Value, what: &str) -> Result<Vec<(String, Value)>> {
    let Some(entries) = value.as_map() else {
        return err(format!(
            "{what} must be a string-keyed map, not {}",
            value.type_name()
        ));
    };
    entries
        .iter()
        .map(|(k, v)| match k {
            Value::Text(s) => Ok((s.clone(), v.clone())),
            _ => err(format!("{what} must be a string-keyed map")),
        })
        .collect()
}

fn read_processing_record(value: &Value) -> Result<Processing> {
    let mut p = Processing::default();
    for (k, v) in int_fields(value, "processing record", &[0, 1, 12, 13, 14, 15, 16])? {
        if matches!(v, Value::Null) && matches!(k, 13..=15) {
            continue; // a null leaf field reads as absent
        }
        match k {
            0 => p.params = read_params(v)?,
            1 => p.user_params = read_user_params(v)?,
            12 => p.software = Some(read_software(v)?),
            13 => p.operation = Some(text(v, "processing operation")?),
            14 => p.revision = Some(positive(v, "processing revision")?),
            15 => p.parameters = Some(read_string_map(v, "processing parameters")?),
            _ => p.source_params = read_params(v)?,
        }
    }
    Ok(p)
}

pub fn read_processing(value: &Value) -> Result<Vec<Processing>> {
    list(value, "processing records")?
        .iter()
        .map(read_processing_record)
        .collect()
}

pub fn read_extensions(value: &Value) -> Result<Extensions> {
    let Some(entries) = value.as_map() else {
        return err(format!(
            "extensions must be a map, not {}",
            value.type_name()
        ));
    };
    let mut out = Vec::with_capacity(entries.len());
    for (k, v) in entries {
        let Value::Text(name) = k else {
            return err("extension identifiers must be namespaced text");
        };
        if !is_namespaced(name) {
            return err(format!("extension identifier {name:?} must be namespaced"));
        }
        let (mut revision, mut required, mut data) = (None, None, None);
        for (field, fv) in text_fields(v, "extension record", &["revision", "required", "data"])? {
            match field {
                "revision" => revision = Some(positive(fv, "extension revision")?),
                "required" => match fv {
                    Value::Bool(b) => required = Some(*b),
                    _ => return err("extension required must be a boolean"),
                },
                _ => data = Some(fv.clone()),
            }
        }
        let (Some(revision), Some(required), Some(data)) = (revision, required, data) else {
            return err("an extension record needs revision, required and data");
        };
        out.push((
            name.clone(),
            Extension {
                revision,
                required,
                data,
            },
        ));
    }
    Ok(out)
}

fn read_scan(value: &Value) -> Result<Scan> {
    let mut s = Scan::default();
    for (k, v) in int_fields(value, "scan", &[0, 1, 2, 3, 4, 5])? {
        match k {
            0 => s.params = read_params(v)?,
            1 => s.windows = read_groups(v)?,
            2 => s.user_params = read_user_params(v)?,
            3 => s.source = Some(read_source(v)?),
            4 => s.acquisition = Some(read_acquisition(v)?),
            _ => s.processing = read_processing(v)?,
        }
    }
    Ok(s)
}

fn read_precursor(value: &Value) -> Result<Precursor> {
    let mut p = Precursor::default();
    for (k, v) in int_fields(value, "precursor", &[0, 1, 2, 3, 4, 5])? {
        match k {
            0 => p.isolation_window = Some(read_group(v)?),
            1 => p.selected_ions = read_groups(v)?,
            2 => p.activation = Some(read_group(v)?),
            3 => p.source = Some(read_source(v)?),
            4 => p.acquisition = Some(read_acquisition(v)?),
            _ => p.processing = read_processing(v)?,
        }
    }
    Ok(p)
}

fn read_product(value: &Value) -> Result<Product> {
    let mut p = Product::default();
    for (_, v) in int_fields(value, "product", &[0])? {
        p.isolation_window = Some(read_group(v)?);
    }
    Ok(p)
}

fn read_scan_list(value: &Value, spectrum: &mut Spectrum) -> Result<()> {
    for (k, v) in text_fields(value, "scan list", &["c", "s"])? {
        match k {
            "c" => spectrum.scan_combination = Some(accession("MS", tail(v, "scan combination")?)),
            _ => {
                spectrum.scans = list(v, "scans")?
                    .iter()
                    .map(read_scan)
                    .collect::<Result<_>>()?
            }
        }
    }
    Ok(())
}

fn read_cv_versions(value: &Value) -> Result<Vec<(String, String)>> {
    let Some(entries) = value.as_map() else {
        return err("ontology versions must be a map");
    };
    let mut out = Vec::new();
    for (k, v) in entries {
        let Value::Text(prefix) = k else {
            return err("ontology version keys must be accession prefixes");
        };
        if !is_prefix(prefix) {
            return err(format!("invalid ontology prefix {prefix:?}"));
        }
        out.push((prefix.clone(), nonempty_text(v, "ontology version")?));
    }
    Ok(out)
}

// Terms a descriptor's scientific parameters must not repeat: numeric types
// and binary compression declarations (see SPEC-NOTES.md, section 4).
const REPRESENTATION_TERMS: &[i64] = &[
    1000519, 1000521, 1000522, 1000523, // numeric types
    1000574, 1000576, // zlib, no compression
    1002312, 1002313, 1002314, // numpress
    1002746, 1002747, 1002748, // numpress + zlib
    1003780, 1003781, 1003782, 1003783, 1003784, 1003785, // truncation / zstd variants
];

fn read_operation(value: &Value) -> Result<Operation> {
    let Some(items) = value.as_array() else {
        return err(
            "an encoding operation must be [identifier, revision] or [identifier, revision, parameters]",
        );
    };
    if !(2..=3).contains(&items.len()) {
        return err(
            "an encoding operation must be [identifier, revision] or [identifier, revision, parameters]",
        );
    }
    let id = match &items[0] {
        Value::Int(i) if *i >= 0 => OpId::Builtin(*i),
        Value::Text(s) if is_namespaced(s) => OpId::Named(s.clone()),
        _ => {
            return err(
                "an operation identifier must be a nonnegative integer or a namespaced string",
            );
        }
    };
    let revision = match &items[1] {
        Value::Int(r) if *r >= 1 => *r,
        _ => return err("an operation revision must be a positive integer"),
    };
    let parameters = match items.get(2) {
        None => None,
        Some(p) => {
            let map = read_string_map(p, "operation parameters")?;
            if map.is_empty() {
                return err("an empty operation parameter map must be omitted");
            }
            Some(map)
        }
    };
    Ok(Operation {
        id,
        revision,
        parameters,
    })
}

/// Resolve a core encoding and validate its parameters. `Ok(None)` means the
/// encoding or revision is unknown to this reader.
fn resolve(op: &Operation, dtype: DType, fidelity: i64) -> Result<Option<Encoding>> {
    let OpId::Builtin(id) = op.id else {
        return Ok(None);
    };
    if op.revision != 1 || id > 4 {
        return Ok(None);
    }
    let encoding = match id {
        0..=2 => {
            if op.parameters.is_some() {
                return err("this encoding does not accept parameters");
            }
            [Encoding::Raw, Encoding::Shuffle, Encoding::DeltaShuffle][id as usize]
        }
        3 => {
            let params = op.parameters.as_deref().unwrap_or(&[]);
            let (mut scale, mut width, mut log, mut delta) = (None, None, false, false);
            for (k, v) in params {
                match (k.as_str(), v) {
                    ("scale", Value::Int(i)) => scale = Some(*i as f64),
                    ("scale", Value::Float(f)) => scale = Some(*f),
                    ("width", Value::Int(w)) => width = Some(*w),
                    ("log", Value::Bool(b)) => log = *b,
                    ("delta", Value::Bool(b)) => delta = *b,
                    ("scale" | "width", _) => {
                        return err(format!("quantized parameter {k} has the wrong type"));
                    }
                    ("log" | "delta", _) => {
                        return err(format!("quantized parameter {k} must be a boolean"));
                    }
                    _ => return err(format!("unknown quantized parameter {k:?}")),
                }
            }
            let (Some(scale), Some(width)) = (scale, width) else {
                return err("quantized encoding needs scale and width parameters");
            };
            if !(scale.is_finite() && scale > 0.0) {
                return err("quantized scale must be finite and positive");
            }
            if !valid_width(width) {
                return err("quantized width must be 1, 2, 4 or 8");
            }
            if !dtype.is_float() {
                return err("quantized encoding supports float32 and float64 only");
            }
            Encoding::Quantized(Quantized {
                scale,
                width: width as usize,
                log,
                delta,
            })
        }
        _ => {
            let params = op.parameters.as_deref().unwrap_or(&[]);
            let (mut bits, mut width) = (None, None);
            for (k, v) in params {
                match (k.as_str(), v) {
                    ("bits", Value::Int(b)) => bits = Some(*b),
                    ("width", Value::Int(w)) => width = Some(*w),
                    ("bits" | "width", _) => {
                        return err(format!("rounded parameter {k} must be an integer"));
                    }
                    _ => return err(format!("unknown rounded parameter {k:?}")),
                }
            }
            let (Some(bits), Some(width)) = (bits, width) else {
                return err("rounded encoding needs bits and width parameters");
            };
            let m = match dtype {
                DType::F32 => 23,
                DType::F64 => 52,
                DType::I32 => return err("rounded encoding needs dtype float32 or float64"),
            };
            if !(0..=m).contains(&bits) {
                return err(format!(
                    "rounded mantissa bits exceed 0..{m} for {}",
                    dtype.name()
                ));
            }
            if !valid_width(width) {
                return err("rounded width must be 1, 2, 4 or 8");
            }
            if width as usize > dtype.size() {
                return err("rounded word width exceeds the declared type size");
            }
            Encoding::Rounded(Rounded {
                bits: bits as u32,
                width: width as usize,
            })
        }
    };
    if encoding.fidelity() != fidelity {
        return err("encoding fidelity declaration mismatch");
    }
    Ok(Some(encoding))
}

fn read_descriptor(value: &Value, n: usize) -> Result<Descriptor> {
    let fields = int_fields(
        value,
        "array descriptor",
        &[0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11],
    )?;
    let get = |k: i64| fields.iter().find(|(key, _)| *key == k).map(|(_, v)| *v);
    let (Some(dt), Some(at), Some(op), Some(data), Some(fid)) =
        (get(0), get(1), get(2), get(5), get(7))
    else {
        return err("an array descriptor needs keys 0, 1, 2, 5 and 7");
    };
    let dtype = match dt {
        Value::Int(t) => DType::from_tail(*t),
        _ => None,
    }
    .ok_or_else(|| Error::decode("array numeric type must be float32, float64 or int32"))?;
    let array_tail = tail(at, "array type")?;
    let operation = read_operation(op)?;
    let fidelity = match fid {
        Value::Int(f @ (0 | 1)) => *f,
        _ => return err("array fidelity must be 0 or 1"),
    };
    let Value::Bytes(blob) = data else {
        return err("array data must be a byte string");
    };
    if blob.len() > MAX_BLOB_BYTES || blob.len() as u64 > 64 + 16 * n as u64 {
        return err("array bytes exceed the intermediate size limit");
    }
    let name = get(4).map(|v| nonempty_text(v, "array name")).transpose()?;
    let unit = get(6).map(read_unit).transpose()?;
    let params = get(8).map(read_params).transpose()?.unwrap_or_default();
    let user_params = get(9)
        .map(read_user_params)
        .transpose()?
        .unwrap_or_default();
    let processing = get(10).map(read_processing).transpose()?;
    let extensions = get(11)
        .map(read_extensions)
        .transpose()?
        .unwrap_or_default();

    let key = match array_tail {
        NONSTANDARD_ARRAY => {
            let Some(name) = &name else {
                return err("a nonstandard array (MS:1000786) needs a name");
            };
            if matches!(name.as_str(), "mz" | "intensity" | "charge") {
                return err(format!("nonstandard array name {name:?} is reserved"));
            }
            if is_accession(name) {
                return err("nonstandard array name must not be a CV accession");
            }
            name.clone()
        }
        _ => CORE_ARRAYS
            .iter()
            .find(|(_, t)| *t == array_tail)
            .map(|(k, _)| k.to_string())
            .unwrap_or_else(|| accession("MS", array_tail)),
    };
    for p in &params {
        if let Some(("MS", t)) = seven_digit(&p.accession) {
            if t == array_tail || REPRESENTATION_TERMS.contains(&t) {
                return err(
                    "array scientific parameters conflict with representation declarations",
                );
            }
        }
    }
    let encoding = resolve(&operation, dtype, fidelity)?;
    Ok(Descriptor {
        key,
        dtype,
        array_tail,
        operation,
        encoding,
        fidelity,
        name,
        blob: blob.clone(),
        unit,
        params,
        user_params,
        processing,
        extensions,
    })
}

/// Validate the whole header and split it into metadata and descriptors.
pub fn read_header(root: &Value) -> Result<Header> {
    let Some(entries) = root.as_map() else {
        return err(format!(
            "the CBOR root must be an integer-keyed map, not {}",
            root.type_name()
        ));
    };
    let mut keys: Vec<(i64, &Value)> = Vec::with_capacity(entries.len());
    for (k, v) in entries {
        match k {
            Value::Int(i) if (0..=12).contains(i) => keys.push((*i, v)),
            other => {
                return err(format!(
                    "unsupported spectrl header key {}",
                    show_key(other)
                ));
            }
        }
    }
    let Some(&(_, n_value)) = keys.iter().find(|(k, _)| *k == 0) else {
        return err("header key 0 (array length) is required");
    };
    let n = match n_value {
        Value::Int(i) if *i >= 0 => *i as u64,
        _ => return err("header key 0: array length must be a nonnegative integer"),
    };
    if n > MAX_ELEMENTS as u64 {
        return err(format!(
            "header key 0: array length {n} exceeds the hard ceiling of {MAX_ELEMENTS}"
        ));
    }
    let n = n as usize;
    let mut spectrum = Spectrum::new(n);
    let mut descriptors = Vec::new();
    keys.sort_by_key(|(k, _)| *k);
    for (k, v) in keys {
        let result: Result<()> = (|| {
            match k {
                0 => {}
                1 => spectrum.id = Some(text(v, "spectrum id")?),
                2 => spectrum.params = read_params(v)?,
                3 => read_scan_list(v, &mut spectrum)?,
                4 => {
                    spectrum.precursors = list(v, "precursors")?
                        .iter()
                        .map(read_precursor)
                        .collect::<Result<_>>()?
                }
                5 => {
                    spectrum.products = list(v, "products")?
                        .iter()
                        .map(read_product)
                        .collect::<Result<_>>()?
                }
                6 => {
                    for d in list(v, "arrays")? {
                        descriptors.push(read_descriptor(d, n)?);
                    }
                }
                7 => spectrum.user_params = read_user_params(v)?,
                8 => spectrum.source = Some(read_source(v)?),
                9 => spectrum.acquisition = Some(read_acquisition(v)?),
                10 => spectrum.processing = read_processing(v)?,
                11 => spectrum.extensions = read_extensions(v)?,
                _ => spectrum.cv_versions = read_cv_versions(v)?,
            }
            Ok(())
        })();
        result.map_err(|e| {
            Error::new(
                e.kind(),
                format!("malformed spectrl header key {k}: {}", e.message()),
            )
        })?;
    }
    // Identity: a standard array by accession, a nonstandard one by name.
    for (i, d) in descriptors.iter().enumerate() {
        if descriptors[..i].iter().any(|o| o.key == d.key) {
            return err(format!("duplicate array identity {:?}", d.key));
        }
    }
    Ok(Header {
        spectrum,
        descriptors,
    })
}

/// Key of the reconstructed m/z parameter in an encoding descriptor record.
pub fn lossy_record(op: &Operation) -> Processing {
    Processing {
        operation: Some("spectrl:lossy-encoding".to_string()),
        revision: Some(1),
        parameters: Some(vec![("encoding".to_string(), op.to_value())]),
        ..Default::default()
    }
}

// ---------------------------------------------------------------------------
// Writing

fn enc_err<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::encode(message))
}

fn int(k: i64) -> Value {
    Value::Int(k)
}

fn scalar_value(s: &Scalar) -> Result<Value> {
    Ok(match s {
        Scalar::Null => Value::Null,
        Scalar::Number(f) => {
            if !f.is_finite() {
                return enc_err("parameter values must be finite");
            }
            Value::Float(*f)
        }
        Scalar::Text(t) => Value::text(t.clone()),
    })
}

pub fn write_accession(acc: &str) -> Result<Value> {
    match seven_digit(acc) {
        Some(("MS", t)) => Ok(int(t)),
        _ if is_accession(acc) => Ok(Value::text(acc)),
        _ => enc_err(format!("invalid CV accession {acc:?}")),
    }
}

pub fn write_unit(unit: &str) -> Result<Value> {
    match seven_digit(unit) {
        Some(("UO", t)) => Ok(int(t)),
        Some((prefix, t)) => Ok(Value::Array(vec![Value::text(prefix), int(t)])),
        None if is_accession(unit) => Ok(Value::text(unit)),
        None => enc_err(format!("invalid unit accession {unit:?}")),
    }
}

pub fn write_params(params: &[CvParam]) -> Result<Value> {
    let mut out = Vec::with_capacity(params.len());
    for p in params {
        let value = scalar_value(&p.value)?;
        let value = match &p.unit_accession {
            Some(u) => Value::Array(vec![value, write_unit(u)?]),
            None => value,
        };
        out.push(Value::Array(vec![write_accession(&p.accession)?, value]));
    }
    Ok(Value::Array(out))
}

pub fn write_user_params(params: &[UserParam]) -> Result<Value> {
    let mut out = Vec::with_capacity(params.len());
    for p in params {
        if p.name.is_empty() {
            return enc_err("user parameter names must be nonempty");
        }
        let mut m = vec![(Value::text("n"), Value::text(p.name.clone()))];
        if p.value != Scalar::Null {
            m.push((Value::text("v"), scalar_value(&p.value)?));
        }
        if let Some(u) = &p.unit_accession {
            m.push((Value::text("u"), write_unit(u)?));
        }
        out.push(Value::Map(m));
    }
    Ok(Value::Array(out))
}

fn write_group(g: &Group) -> Result<Value> {
    let mut m = vec![(int(0), write_params(&g.params)?)];
    if !g.user_params.is_empty() {
        m.push((int(1), write_user_params(&g.user_params)?));
    }
    Ok(Value::Map(m))
}

fn push_params(m: &mut Vec<(Value, Value)>, key: i64, params: &[CvParam]) -> Result<()> {
    if !params.is_empty() {
        m.push((int(key), write_params(params)?));
    }
    Ok(())
}

fn push_user(m: &mut Vec<(Value, Value)>, key: i64, params: &[UserParam]) -> Result<()> {
    if !params.is_empty() {
        m.push((int(key), write_user_params(params)?));
    }
    Ok(())
}

fn push_text(m: &mut Vec<(Value, Value)>, key: i64, text: &Option<String>) {
    if let Some(t) = text {
        m.push((int(key), Value::text(t.clone())));
    }
}

fn write_source(s: &Source) -> Result<Value> {
    let mut m = Vec::new();
    push_params(&mut m, 0, &s.params)?;
    push_user(&mut m, 1, &s.user_params)?;
    push_text(&mut m, 2, &s.id);
    push_text(&mut m, 3, &s.name);
    push_text(&mut m, 5, &s.location);
    if !s.external_ids.is_empty() {
        m.push((
            int(6),
            Value::Array(
                s.external_ids
                    .iter()
                    .map(|x| Value::text(x.clone()))
                    .collect(),
            ),
        ));
    }
    push_text(&mut m, 7, &s.spectrum_ref);
    Ok(Value::Map(m))
}

fn write_software(s: &Software) -> Result<Value> {
    let mut m = Vec::new();
    push_params(&mut m, 0, &s.params)?;
    push_user(&mut m, 1, &s.user_params)?;
    push_text(&mut m, 2, &s.id);
    push_text(&mut m, 3, &s.name);
    push_text(&mut m, 4, &s.version);
    Ok(Value::Map(m))
}

fn write_acquisition(a: &Acquisition) -> Result<Value> {
    let mut m = Vec::new();
    if let Some(i) = &a.instrument {
        let mut im = Vec::new();
        push_params(&mut im, 0, &i.params)?;
        push_user(&mut im, 1, &i.user_params)?;
        push_text(&mut im, 2, &i.id);
        push_text(&mut im, 3, &i.name);
        if !i.components.is_empty() {
            let mut comps = Vec::new();
            for c in &i.components {
                let mut cm = Vec::new();
                push_params(&mut cm, 0, &c.params)?;
                push_user(&mut cm, 1, &c.user_params)?;
                push_text(&mut cm, 10, &c.kind);
                if let Some(o) = c.order {
                    cm.push((int(11), int(o)));
                }
                comps.push(Value::Map(cm));
            }
            im.push((int(9), Value::Array(comps)));
        }
        if let Some(s) = &i.software {
            im.push((int(12), write_software(s)?));
        }
        m.push((int(8), Value::Map(im)));
    }
    Ok(Value::Map(m))
}

pub fn write_processing(records: &[Processing]) -> Result<Value> {
    let mut out = Vec::with_capacity(records.len());
    for p in records {
        let mut m = Vec::new();
        push_params(&mut m, 0, &p.params)?;
        push_user(&mut m, 1, &p.user_params)?;
        if let Some(s) = &p.software {
            m.push((int(12), write_software(s)?));
        }
        push_text(&mut m, 13, &p.operation);
        if let Some(r) = p.revision {
            m.push((int(14), int(r)));
        }
        if let Some(params) = &p.parameters {
            if !params.is_empty() {
                m.push((
                    int(15),
                    Value::Map(
                        params
                            .iter()
                            .map(|(k, v)| (Value::text(k.clone()), v.clone()))
                            .collect(),
                    ),
                ));
            }
        }
        push_params(&mut m, 16, &p.source_params)?;
        out.push(Value::Map(m));
    }
    Ok(Value::Array(out))
}

pub fn write_extensions(ext: &Extensions) -> Value {
    Value::Map(
        ext.iter()
            .map(|(k, e)| {
                (
                    Value::text(k.clone()),
                    Value::Map(vec![
                        (Value::text("data"), e.data.clone()),
                        (Value::text("required"), Value::Bool(e.required)),
                        (Value::text("revision"), int(e.revision)),
                    ]),
                )
            })
            .collect(),
    )
}

fn write_context(
    m: &mut Vec<(Value, Value)>,
    source: &Option<Source>,
    acq: &Option<Acquisition>,
    proc: &[Processing],
) -> Result<()> {
    if let Some(s) = source {
        m.push((int(3), write_source(s)?));
    }
    if let Some(a) = acq {
        m.push((int(4), write_acquisition(a)?));
    }
    if !proc.is_empty() {
        m.push((int(5), write_processing(proc)?));
    }
    Ok(())
}

/// Header entries for everything except key 6 (arrays).
pub fn write_metadata(s: &Spectrum) -> Result<Vec<(Value, Value)>> {
    let mut m = vec![(int(0), int(s.default_array_length as i64))];
    if let Some(id) = &s.id {
        m.push((int(1), Value::text(id.clone())));
    }
    push_params(&mut m, 2, &s.params)?;
    if !s.scans.is_empty() || s.scan_combination.is_some() {
        let mut sl = Vec::new();
        if let Some(c) = &s.scan_combination {
            let Some(("MS", t)) = seven_digit(c) else {
                return enc_err(format!("scan combination {c:?} must be a PSI-MS accession"));
            };
            sl.push((Value::text("c"), int(t)));
        }
        if !s.scans.is_empty() {
            let mut scans = Vec::new();
            for scan in &s.scans {
                let mut sm = vec![(int(0), write_params(&scan.params)?)];
                if !scan.windows.is_empty() {
                    sm.push((
                        int(1),
                        Value::Array(
                            scan.windows
                                .iter()
                                .map(write_group)
                                .collect::<Result<_>>()?,
                        ),
                    ));
                }
                push_user(&mut sm, 2, &scan.user_params)?;
                write_context(&mut sm, &scan.source, &scan.acquisition, &scan.processing)?;
                scans.push(Value::Map(sm));
            }
            sl.push((Value::text("s"), Value::Array(scans)));
        }
        m.push((int(3), Value::Map(sl)));
    }
    if !s.precursors.is_empty() {
        let mut out = Vec::new();
        for p in &s.precursors {
            let mut pm = Vec::new();
            if let Some(g) = &p.isolation_window {
                pm.push((int(0), write_group(g)?));
            }
            if !p.selected_ions.is_empty() {
                pm.push((
                    int(1),
                    Value::Array(
                        p.selected_ions
                            .iter()
                            .map(write_group)
                            .collect::<Result<_>>()?,
                    ),
                ));
            }
            if let Some(g) = &p.activation {
                pm.push((int(2), write_group(g)?));
            }
            write_context(&mut pm, &p.source, &p.acquisition, &p.processing)?;
            out.push(Value::Map(pm));
        }
        m.push((int(4), Value::Array(out)));
    }
    if !s.products.is_empty() {
        let mut out = Vec::new();
        for p in &s.products {
            let mut pm = Vec::new();
            if let Some(g) = &p.isolation_window {
                pm.push((int(0), write_group(g)?));
            }
            out.push(Value::Map(pm));
        }
        m.push((int(5), Value::Array(out)));
    }
    push_user(&mut m, 7, &s.user_params)?;
    if let Some(src) = &s.source {
        m.push((int(8), write_source(src)?));
    }
    if let Some(a) = &s.acquisition {
        m.push((int(9), write_acquisition(a)?));
    }
    if !s.processing.is_empty() {
        m.push((int(10), write_processing(&s.processing)?));
    }
    if !s.extensions.is_empty() {
        m.push((int(11), write_extensions(&s.extensions)));
    }
    if !s.cv_versions.is_empty() {
        m.push((
            int(12),
            Value::Map(
                s.cv_versions
                    .iter()
                    .map(|(k, v)| (Value::text(k.clone()), Value::text(v.clone())))
                    .collect(),
            ),
        ));
    }
    Ok(m)
}

/// A descriptor map for an encoded array.
#[allow(clippy::too_many_arguments)]
pub fn write_descriptor(
    spectrum: &Spectrum,
    key: &str,
    dtype: DType,
    operation: &Operation,
    fidelity: i64,
    blob: Vec<u8>,
) -> Result<Value> {
    let (tail, name) = match CORE_ARRAYS.iter().find(|(k, _)| *k == key) {
        Some((_, t)) => (*t, spectrum.array_names.get(key).cloned()),
        None => match seven_digit(key) {
            Some(("MS", t)) => {
                if CORE_ARRAYS.iter().any(|(_, c)| *c == t) || t == NONSTANDARD_ARRAY {
                    return enc_err(format!(
                        "extra array key {key:?} names a core or nonstandard array type"
                    ));
                }
                (t, spectrum.array_names.get(key).cloned())
            }
            _ if is_accession(key) => {
                return enc_err(format!(
                    "extra array key {key:?} is not a PSI-MS array accession"
                ));
            }
            _ => (NONSTANDARD_ARRAY, Some(key.to_string())),
        },
    };
    let mut m = vec![
        (int(0), int(dtype.tail())),
        (int(1), int(tail)),
        (int(2), operation.to_value()),
        (int(5), Value::Bytes(blob)),
        (int(7), int(fidelity)),
    ];
    if let Some(n) = name {
        m.push((int(4), Value::text(n)));
    }
    if let Some(u) = spectrum.array_units.get(key) {
        m.push((int(6), write_unit(u)?));
    }
    if let Some(p) = spectrum.array_params.get(key).filter(|p| !p.is_empty()) {
        m.push((int(8), write_params(p)?));
    }
    if let Some(p) = spectrum
        .array_user_params
        .get(key)
        .filter(|p| !p.is_empty())
    {
        m.push((int(9), write_user_params(p)?));
    }
    if let Some(p) = spectrum.array_processing.get(key).filter(|p| !p.is_empty()) {
        m.push((int(10), write_processing(p)?));
    }
    if let Some(e) = spectrum.array_extensions.get(key).filter(|e| !e.is_empty()) {
        m.push((int(11), write_extensions(e)));
    }
    Ok(Value::Map(m))
}

/// Largest safe integer as f64, for writer checks.
pub const MAX_SAFE_F64: f64 = MAX_SAFE as f64;
