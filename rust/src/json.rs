//! JSON interchange for the command-line tool and the parity harnesses.
//!
//! The field names follow the reference implementation's `spectrum_to_dict`
//! form: snake_case fields, plain number lists for arrays, `array_dtypes` and
//! `extra_array_dtypes` for non-float64 arrays, and `{"$spectrl": "bytes",
//! "hex": ...}` / `{"$spectrl": "map", "items": [[k, v], ...]}` for CBOR byte
//! strings and non-text-keyed maps inside extension data and operation
//! parameters.

use std::collections::BTreeMap;

use serde_json::{Map, Number, Value as Json, json};

use crate::cbor::{MAX_SAFE, Value};
use crate::codecs::{Array, DType};
use crate::error::{Error, Result};
use crate::model::*;

fn fail<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::encode(message))
}

// ---------------------------------------------------------------------------
// JSON -> model

type Obj = Map<String, Json>;

fn object<'a>(value: &'a Json, what: &str) -> Result<&'a Obj> {
    value
        .as_object()
        .ok_or_else(|| Error::encode(format!("{what} must be a JSON object")))
}

fn fields<'a>(value: &'a Json, what: &str, allowed: &[&str]) -> Result<&'a Obj> {
    let obj = object(value, what)?;
    if let Some(k) = obj.keys().find(|k| !allowed.contains(&k.as_str())) {
        return fail(format!("unknown {what} field {k:?}"));
    }
    Ok(obj)
}

fn opt<'a>(obj: &'a Obj, key: &str) -> Option<&'a Json> {
    obj.get(key).filter(|v| !v.is_null())
}

fn list<'a>(obj: &'a Obj, key: &str) -> Result<&'a [Json]> {
    match opt(obj, key) {
        None => Ok(&[]),
        Some(Json::Array(a)) => Ok(a),
        Some(_) => fail(format!("{key} must be a list")),
    }
}

fn opt_text(obj: &Obj, key: &str) -> Result<Option<String>> {
    match opt(obj, key) {
        None => Ok(None),
        Some(Json::String(s)) => Ok(Some(s.clone())),
        Some(_) => fail(format!("{key} must be text")),
    }
}

fn opt_int(obj: &Obj, key: &str) -> Result<Option<i64>> {
    match opt(obj, key) {
        None => Ok(None),
        Some(v) => match v.as_i64() {
            Some(i) => Ok(Some(i)),
            None => match v.as_f64() {
                Some(f) if f.fract() == 0.0 && f.abs() <= MAX_SAFE as f64 => Ok(Some(f as i64)),
                _ => fail(format!("{key} must be an integer")),
            },
        },
    }
}

fn scalar(value: Option<&Json>) -> Result<Scalar> {
    Ok(match value {
        None | Some(Json::Null) => Scalar::Null,
        Some(Json::String(s)) => Scalar::Text(s.clone()),
        Some(Json::Number(n)) => {
            if let Some(i) = n.as_i64() {
                if i.abs() > MAX_SAFE {
                    return fail("integer parameter values must be within the safe integer range");
                }
            } else if n.as_u64().is_some() {
                return fail("integer parameter values must be within the safe integer range");
            }
            Scalar::Number(n.as_f64().expect("finite JSON number"))
        }
        Some(_) => return fail("parameter values must be null, a number or text"),
    })
}

fn cv_param(value: &Json) -> Result<CvParam> {
    let obj = fields(
        value,
        "CV parameter",
        &["accession", "value", "unit_accession"],
    )?;
    let Some(accession) = opt_text(obj, "accession")? else {
        return fail("a CV parameter needs an accession");
    };
    Ok(CvParam {
        accession,
        value: scalar(obj.get("value"))?,
        unit_accession: opt_text(obj, "unit_accession")?,
    })
}

fn cv_params(obj: &Obj, key: &str) -> Result<Vec<CvParam>> {
    list(obj, key)?.iter().map(cv_param).collect()
}

fn user_param(value: &Json) -> Result<UserParam> {
    let obj = fields(
        value,
        "user parameter",
        &["name", "value", "unit_accession"],
    )?;
    let Some(name) = opt_text(obj, "name")? else {
        return fail("a user parameter needs a name");
    };
    Ok(UserParam {
        name,
        value: scalar(obj.get("value"))?,
        unit_accession: opt_text(obj, "unit_accession")?,
    })
}

fn user_params(obj: &Obj, key: &str) -> Result<Vec<UserParam>> {
    list(obj, key)?.iter().map(user_param).collect()
}

fn group(value: &Json) -> Result<Group> {
    let obj = fields(value, "parameter group", &["params", "user_params"])?;
    Ok(Group {
        params: cv_params(obj, "params")?,
        user_params: user_params(obj, "user_params")?,
    })
}

fn opt_group(obj: &Obj, key: &str) -> Result<Option<Group>> {
    opt(obj, key).map(group).transpose()
}

fn software(value: &Json) -> Result<Software> {
    let o = fields(
        value,
        "software",
        &["params", "user_params", "id", "name", "version"],
    )?;
    Ok(Software {
        params: cv_params(o, "params")?,
        user_params: user_params(o, "user_params")?,
        id: opt_text(o, "id")?,
        name: opt_text(o, "name")?,
        version: opt_text(o, "version")?,
    })
}

fn source(value: &Json) -> Result<Source> {
    let o = fields(
        value,
        "source",
        &[
            "params",
            "user_params",
            "id",
            "name",
            "location",
            "external_ids",
            "spectrum_ref",
        ],
    )?;
    Ok(Source {
        params: cv_params(o, "params")?,
        user_params: user_params(o, "user_params")?,
        id: opt_text(o, "id")?,
        name: opt_text(o, "name")?,
        location: opt_text(o, "location")?,
        external_ids: list(o, "external_ids")?
            .iter()
            .map(|v| {
                v.as_str()
                    .map(str::to_string)
                    .ok_or_else(|| Error::encode("external IDs must be text"))
            })
            .collect::<Result<_>>()?,
        spectrum_ref: opt_text(o, "spectrum_ref")?,
    })
}

fn acquisition(value: &Json) -> Result<Acquisition> {
    let o = fields(value, "acquisition", &["instrument"])?;
    let instrument = match opt(o, "instrument") {
        None => None,
        Some(v) => {
            let i = fields(
                v,
                "instrument",
                &[
                    "params",
                    "user_params",
                    "id",
                    "name",
                    "components",
                    "software",
                ],
            )?;
            Some(Instrument {
                params: cv_params(i, "params")?,
                user_params: user_params(i, "user_params")?,
                id: opt_text(i, "id")?,
                name: opt_text(i, "name")?,
                components: list(i, "components")?
                    .iter()
                    .map(|c| {
                        let c =
                            fields(c, "component", &["params", "user_params", "kind", "order"])?;
                        Ok(Component {
                            params: cv_params(c, "params")?,
                            user_params: user_params(c, "user_params")?,
                            kind: opt_text(c, "kind")?,
                            order: opt_int(c, "order")?,
                        })
                    })
                    .collect::<Result<_>>()?,
                software: opt(i, "software").map(software).transpose()?,
            })
        }
    };
    Ok(Acquisition { instrument })
}

fn processing_list(value: Option<&Json>) -> Result<Vec<Processing>> {
    let Some(value) = value.filter(|v| !v.is_null()) else {
        return Ok(Vec::new());
    };
    let Json::Array(items) = value else {
        return fail("processing must be a list");
    };
    items
        .iter()
        .map(|p| {
            let o = fields(
                p,
                "processing",
                &[
                    "params",
                    "user_params",
                    "software",
                    "operation",
                    "revision",
                    "parameters",
                    "source_params",
                ],
            )?;
            let parameters = match opt(o, "parameters") {
                None => None,
                Some(v) => match to_cbor(v)? {
                    Value::Map(entries) => Some(
                        entries
                            .into_iter()
                            .map(|(k, v)| match k {
                                Value::Text(s) => Ok((s, v)),
                                _ => fail("processing parameters must be a string-keyed map"),
                            })
                            .collect::<Result<_>>()?,
                    ),
                    _ => return fail("processing parameters must be a map"),
                },
            };
            Ok(Processing {
                params: cv_params(o, "params")?,
                user_params: user_params(o, "user_params")?,
                software: opt(o, "software").map(software).transpose()?,
                operation: opt_text(o, "operation")?,
                revision: opt_int(o, "revision")?,
                parameters,
                source_params: cv_params(o, "source_params")?,
            })
        })
        .collect()
}

fn extensions(value: Option<&Json>) -> Result<Extensions> {
    let Some(value) = value.filter(|v| !v.is_null()) else {
        return Ok(Vec::new());
    };
    let obj = object(value, "extensions")?;
    obj.iter()
        .map(|(name, e)| {
            let o = fields(e, "extension", &["revision", "required", "data"])?;
            let Some(revision) = opt_int(o, "revision")? else {
                return fail("an extension needs a revision");
            };
            let Some(Json::Bool(required)) = o.get("required") else {
                return fail("an extension needs a boolean required flag");
            };
            let Some(data) = o.get("data") else {
                return fail("an extension needs data");
            };
            Ok((
                name.clone(),
                Extension {
                    revision,
                    required: *required,
                    data: to_cbor(data)?,
                },
            ))
        })
        .collect()
}

/// A JSON value to a CBOR value, with `$spectrl` escapes.
pub fn to_cbor(value: &Json) -> Result<Value> {
    Ok(match value {
        Json::Null => Value::Null,
        Json::Bool(b) => Value::Bool(*b),
        Json::Number(n) => {
            if let Some(i) = n.as_i64() {
                if i.abs() > MAX_SAFE {
                    return fail("integers must be within the safe integer range");
                }
                Value::Int(i)
            } else if n.as_u64().is_some() {
                return fail("integers must be within the safe integer range");
            } else {
                Value::Float(n.as_f64().expect("finite JSON number"))
            }
        }
        Json::String(s) => Value::Text(s.clone()),
        Json::Array(a) => Value::Array(a.iter().map(to_cbor).collect::<Result<_>>()?),
        Json::Object(o) => {
            match (o.get("$spectrl").and_then(Json::as_str), o.len()) {
                (Some("bytes"), 2) if o.contains_key("hex") => {
                    let hex = o["hex"]
                        .as_str()
                        .ok_or_else(|| Error::encode("bytes hex must be text"))?;
                    return Ok(Value::Bytes(from_hex(hex)?));
                }
                (Some("map"), 2) if o.contains_key("items") => {
                    let Json::Array(items) = &o["items"] else {
                        return fail("map items must be a list");
                    };
                    let mut entries = Vec::with_capacity(items.len());
                    for item in items {
                        match item.as_array().map(Vec::as_slice) {
                            Some([k, v]) => entries.push((to_cbor(k)?, to_cbor(v)?)),
                            _ => return fail("map items must be [key, value] pairs"),
                        }
                    }
                    return Ok(Value::Map(entries));
                }
                _ => {}
            }
            Value::Map(
                o.iter()
                    .map(|(k, v)| Ok((Value::Text(k.clone()), to_cbor(v)?)))
                    .collect::<Result<_>>()?,
            )
        }
    })
}

pub fn from_hex(hex: &str) -> Result<Vec<u8>> {
    if hex.len() % 2 != 0 {
        return fail("hex text must have an even length");
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| {
            u8::from_str_radix(&hex[i..i + 2], 16).map_err(|_| Error::encode("invalid hex text"))
        })
        .collect()
}

pub fn to_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn array(value: &Json, dtype: &str, key: &str) -> Result<Array> {
    let Some(dtype) = DType::from_name(dtype) else {
        return fail(format!("unsupported array dtype {dtype:?}"));
    };
    let Json::Array(items) = value else {
        return fail(format!("array {key:?} must be a list of numbers"));
    };
    let mut values = Vec::with_capacity(items.len());
    for item in items {
        let Some(v) = item.as_f64().filter(|_| item.is_number()) else {
            return fail(format!("array {key:?} must contain only numbers"));
        };
        values.push(v);
    }
    Ok(match dtype {
        DType::F64 => Array::F64(values),
        DType::F32 => {
            let out: Vec<f32> = values.iter().map(|&v| v as f32).collect();
            if out.iter().any(|v| !v.is_finite()) {
                return fail(format!("array {key:?} exceeds float32"));
            }
            Array::F32(out)
        }
        DType::I32 => {
            if values
                .iter()
                .any(|&v| v.fract() != 0.0 || v < i32::MIN as f64 || v > i32::MAX as f64)
            {
                return fail(format!("array {key:?} cannot be represented as int32"));
            }
            Array::I32(values.iter().map(|&v| v as i32).collect())
        }
    })
}

fn string_map(value: Option<&Json>, what: &str) -> Result<BTreeMap<String, String>> {
    let mut out = BTreeMap::new();
    if let Some(v) = value.filter(|v| !v.is_null()) {
        for (k, v) in object(v, what)? {
            let Json::String(s) = v else {
                return fail(format!("{what} values must be text"));
            };
            out.insert(k.clone(), s.clone());
        }
    }
    Ok(out)
}

fn keyed<T>(
    value: Option<&Json>,
    what: &str,
    item: impl Fn(&Json) -> Result<T>,
) -> Result<BTreeMap<String, T>> {
    let mut out = BTreeMap::new();
    if let Some(v) = value.filter(|v| !v.is_null()) {
        for (k, v) in object(v, what)? {
            out.insert(k.clone(), item(v)?);
        }
    }
    Ok(out)
}

const SPECTRUM_FIELDS: &[&str] = &[
    "default_array_length",
    "id",
    "mz",
    "intensity",
    "charge",
    "extra_arrays",
    "array_dtypes",
    "extra_array_dtypes",
    "params",
    "scans",
    "scan_combination",
    "precursors",
    "products",
    "user_params",
    "source",
    "acquisition",
    "processing",
    "extensions",
    "cv_versions",
    "array_names",
    "array_units",
    "array_params",
    "array_user_params",
    "array_processing",
    "array_extensions",
    "checksum",
    "format_version",
];

/// Build a source spectrum from its JSON form.
pub fn spectrum_from_json(value: &Json) -> Result<Spectrum> {
    let o = fields(value, "spectrum", SPECTRUM_FIELDS)?;
    let core_types = string_map(o.get("array_dtypes"), "array_dtypes")?;
    let extra_types = string_map(o.get("extra_array_dtypes"), "extra_array_dtypes")?;
    let mut s = Spectrum::default();
    for (key, _) in CORE_ARRAYS {
        match opt(o, key) {
            Some(v) => {
                *s.core_mut(key).expect("core key") = Some(array(
                    v,
                    core_types.get(key).map_or("float64", String::as_str),
                    key,
                )?)
            }
            None if core_types.contains_key(key) => return fail("dtype declared for absent array"),
            None => {}
        }
    }
    if let Some(k) = core_types
        .keys()
        .find(|k| !CORE_ARRAYS.iter().any(|(c, _)| c == k))
    {
        return fail(format!("array_dtypes names unknown array {k:?}"));
    }
    if let Some(extra) = opt(o, "extra_arrays") {
        for (k, v) in object(extra, "extra_arrays")? {
            s.extra_arrays.insert(
                k.clone(),
                array(v, extra_types.get(k).map_or("float64", String::as_str), k)?,
            );
        }
    }
    if let Some(k) = extra_types
        .keys()
        .find(|k| !s.extra_arrays.contains_key(*k))
    {
        return fail(format!("extra_array_dtypes names unknown array {k:?}"));
    }
    s.default_array_length = match opt_int(o, "default_array_length")? {
        Some(n) if n >= 0 => n as usize,
        Some(_) => return fail("default_array_length must be nonnegative"),
        None => s.mz.as_ref().map_or(0, Array::len),
    };
    s.id = opt_text(o, "id")?;
    s.params = cv_params(o, "params")?;
    s.scans = list(o, "scans")?
        .iter()
        .map(|v| {
            let so = fields(
                v,
                "scan",
                &[
                    "params",
                    "windows",
                    "user_params",
                    "source",
                    "acquisition",
                    "processing",
                ],
            )?;
            Ok(Scan {
                params: cv_params(so, "params")?,
                windows: list(so, "windows")?
                    .iter()
                    .map(group)
                    .collect::<Result<_>>()?,
                user_params: user_params(so, "user_params")?,
                source: opt(so, "source").map(source).transpose()?,
                acquisition: opt(so, "acquisition").map(acquisition).transpose()?,
                processing: processing_list(so.get("processing"))?,
            })
        })
        .collect::<Result<_>>()?;
    s.scan_combination = match opt(o, "scan_combination") {
        None => None,
        Some(v) => {
            let c = cv_param(v)?;
            if c.value != Scalar::Null || c.unit_accession.is_some() {
                return fail("the scan combination is a flag without value or unit");
            }
            Some(c.accession)
        }
    };
    s.precursors = list(o, "precursors")?
        .iter()
        .map(|v| {
            let po = fields(
                v,
                "precursor",
                &[
                    "isolation_window",
                    "selected_ions",
                    "activation",
                    "source",
                    "acquisition",
                    "processing",
                ],
            )?;
            Ok(Precursor {
                isolation_window: opt_group(po, "isolation_window")?,
                selected_ions: list(po, "selected_ions")?
                    .iter()
                    .map(group)
                    .collect::<Result<_>>()?,
                activation: opt_group(po, "activation")?,
                source: opt(po, "source").map(source).transpose()?,
                acquisition: opt(po, "acquisition").map(acquisition).transpose()?,
                processing: processing_list(po.get("processing"))?,
            })
        })
        .collect::<Result<_>>()?;
    s.products = list(o, "products")?
        .iter()
        .map(|v| {
            let po = fields(v, "product", &["isolation_window"])?;
            Ok(Product {
                isolation_window: opt_group(po, "isolation_window")?,
            })
        })
        .collect::<Result<_>>()?;
    s.user_params = user_params(o, "user_params")?;
    s.source = opt(o, "source").map(source).transpose()?;
    s.acquisition = opt(o, "acquisition").map(acquisition).transpose()?;
    s.processing = processing_list(o.get("processing"))?;
    s.extensions = extensions(o.get("extensions"))?;
    s.cv_versions = string_map(o.get("cv_versions"), "cv_versions")?
        .into_iter()
        .collect();
    s.array_names = string_map(o.get("array_names"), "array_names")?;
    s.array_units = string_map(o.get("array_units"), "array_units")?;
    s.array_params = keyed(o.get("array_params"), "array_params", |v| match v {
        Json::Array(a) => a.iter().map(cv_param).collect(),
        _ => fail("array_params values must be lists"),
    })?;
    s.array_user_params = keyed(
        o.get("array_user_params"),
        "array_user_params",
        |v| match v {
            Json::Array(a) => a.iter().map(user_param).collect(),
            _ => fail("array_user_params values must be lists"),
        },
    )?;
    s.array_processing = keyed(o.get("array_processing"), "array_processing", |v| {
        processing_list(Some(v))
    })?;
    s.array_extensions = keyed(o.get("array_extensions"), "array_extensions", |v| {
        extensions(Some(v))
    })?;
    Ok(s)
}

// ---------------------------------------------------------------------------
// model -> JSON

/// A finite number: integral safe values print as integers.
pub fn number(f: f64) -> Json {
    if f.fract() == 0.0 && f.abs() <= MAX_SAFE as f64 && !(f == 0.0 && f.is_sign_negative()) {
        Json::Number(Number::from(f as i64))
    } else {
        Number::from_f64(f).map_or(Json::Null, Json::Number)
    }
}

fn scalar_json(s: &Scalar) -> Json {
    match s {
        Scalar::Null => Json::Null,
        Scalar::Number(f) => number(*f),
        Scalar::Text(t) => Json::String(t.clone()),
    }
}

fn param_json(p: &CvParam) -> Json {
    json!({"accession": p.accession, "value": scalar_json(&p.value), "unit_accession": p.unit_accession})
}

fn params_json(ps: &[CvParam]) -> Json {
    Json::Array(ps.iter().map(param_json).collect())
}

fn user_json(ps: &[UserParam]) -> Json {
    Json::Array(
        ps.iter()
            .map(|p| json!({"name": p.name, "value": scalar_json(&p.value), "unit_accession": p.unit_accession}))
            .collect(),
    )
}

fn group_json(g: &Group) -> Json {
    json!({"params": params_json(&g.params), "user_params": user_json(&g.user_params)})
}

fn software_json(s: &Software) -> Json {
    json!({"params": params_json(&s.params), "user_params": user_json(&s.user_params),
           "id": s.id, "name": s.name, "version": s.version})
}

fn source_json(s: &Source) -> Json {
    json!({"params": params_json(&s.params), "user_params": user_json(&s.user_params), "id": s.id,
           "name": s.name, "location": s.location, "external_ids": s.external_ids, "spectrum_ref": s.spectrum_ref})
}

fn acquisition_json(a: &Acquisition) -> Json {
    json!({"instrument": a.instrument.as_ref().map(|i| json!({
        "params": params_json(&i.params), "user_params": user_json(&i.user_params), "id": i.id, "name": i.name,
        "components": i.components.iter().map(|c| json!({"params": params_json(&c.params),
            "user_params": user_json(&c.user_params), "kind": c.kind, "order": c.order})).collect::<Vec<_>>(),
        "software": i.software.as_ref().map(software_json),
    }))})
}

fn processing_json(ps: &[Processing]) -> Json {
    Json::Array(
        ps.iter()
            .map(|p| {
                json!({"params": params_json(&p.params), "user_params": user_json(&p.user_params),
                "software": p.software.as_ref().map(software_json), "operation": p.operation,
                "revision": p.revision,
                "parameters": p.parameters.as_ref().map(|m| Json::Object(
                    m.iter().map(|(k, v)| (k.clone(), cbor_json(v))).collect())),
                "source_params": params_json(&p.source_params)})
            })
            .collect(),
    )
}

fn extensions_json(e: &Extensions) -> Json {
    Json::Object(
        e.iter()
            .map(|(k, x)| (k.clone(), json!({"revision": x.revision, "required": x.required, "data": cbor_json(&x.data)})))
            .collect(),
    )
}

/// A CBOR value as JSON, with `$spectrl` escapes where JSON cannot say it.
pub fn cbor_json(v: &Value) -> Json {
    match v {
        Value::Null => Json::Null,
        Value::Bool(b) => Json::Bool(*b),
        Value::Int(i) => json!(i),
        Value::Float(f) => Number::from_f64(*f).map_or(Json::Null, Json::Number),
        Value::Text(s) => Json::String(s.clone()),
        Value::Bytes(b) => json!({"$spectrl": "bytes", "hex": to_hex(b)}),
        Value::Array(a) => Json::Array(a.iter().map(cbor_json).collect()),
        Value::Map(m) => {
            if m.iter()
                .all(|(k, _)| matches!(k, Value::Text(s) if s != "$spectrl"))
            {
                Json::Object(
                    m.iter()
                        .map(|(k, v)| (k.as_text().unwrap().to_string(), cbor_json(v)))
                        .collect(),
                )
            } else {
                json!({"$spectrl": "map", "items": m.iter().map(|(k, v)| json!([cbor_json(k), cbor_json(v)])).collect::<Vec<_>>()})
            }
        }
    }
}

pub fn array_json(a: &Array) -> Json {
    match a {
        Array::I32(v) => json!(v),
        _ => Json::Array(
            a.to_f64()
                .into_iter()
                .map(|f| Number::from_f64(f).map_or(Json::Null, Json::Number))
                .collect(),
        ),
    }
}

fn opt_array(a: &Option<Array>) -> Json {
    a.as_ref().map_or(Json::Null, array_json)
}

/// The decoded model in `spectrum_to_dict` form, plus `checksum` and
/// `format_version` when given.
pub fn spectrum_to_json(s: &Spectrum, checksum: Option<&str>) -> Json {
    let mut out = json!({
        "default_array_length": s.default_array_length,
        "id": s.id,
        "mz": opt_array(&s.mz),
        "intensity": opt_array(&s.intensity),
        "charge": opt_array(&s.charge),
        "extra_arrays": Json::Object(s.extra_arrays.iter().map(|(k, a)| (k.clone(), array_json(a))).collect()),
        "array_dtypes": Json::Object(CORE_ARRAYS.iter().filter_map(|(k, _)| s.core(k)
            .map(|a| (k.to_string(), json!(a.dtype().name())))).collect()),
        "extra_array_dtypes": Json::Object(s.extra_arrays.iter()
            .map(|(k, a)| (k.clone(), json!(a.dtype().name()))).collect()),
        "params": params_json(&s.params),
        "scans": s.scans.iter().map(|sc| json!({
            "params": params_json(&sc.params),
            "windows": sc.windows.iter().map(group_json).collect::<Vec<_>>(),
            "user_params": user_json(&sc.user_params),
            "source": sc.source.as_ref().map(source_json),
            "acquisition": sc.acquisition.as_ref().map(acquisition_json),
            "processing": processing_json(&sc.processing),
        })).collect::<Vec<_>>(),
        "scan_combination": s.scan_combination.as_ref()
            .map(|a| json!({"accession": a, "value": null, "unit_accession": null})),
        "precursors": s.precursors.iter().map(|p| json!({
            "isolation_window": p.isolation_window.as_ref().map(group_json),
            "selected_ions": p.selected_ions.iter().map(group_json).collect::<Vec<_>>(),
            "activation": p.activation.as_ref().map(group_json),
            "source": p.source.as_ref().map(source_json),
            "acquisition": p.acquisition.as_ref().map(acquisition_json),
            "processing": processing_json(&p.processing),
        })).collect::<Vec<_>>(),
        "products": s.products.iter()
            .map(|p| json!({"isolation_window": p.isolation_window.as_ref().map(group_json)}))
            .collect::<Vec<_>>(),
        "user_params": user_json(&s.user_params),
        "source": s.source.as_ref().map(source_json),
        "acquisition": s.acquisition.as_ref().map(acquisition_json),
        "processing": processing_json(&s.processing),
        "extensions": extensions_json(&s.extensions),
        "cv_versions": Json::Object(s.cv_versions.iter().map(|(k, v)| (k.clone(), json!(v))).collect()),
        "array_names": s.array_names,
        "array_units": s.array_units,
        "array_params": Json::Object(s.array_params.iter().map(|(k, v)| (k.clone(), params_json(v))).collect()),
        "array_user_params": Json::Object(s.array_user_params.iter().map(|(k, v)| (k.clone(), user_json(v))).collect()),
        "array_processing": Json::Object(s.array_processing.iter()
            .map(|(k, v)| (k.clone(), processing_json(v))).collect()),
        "array_extensions": Json::Object(s.array_extensions.iter()
            .map(|(k, v)| (k.clone(), extensions_json(v))).collect()),
    });
    if let Some(sum) = checksum {
        out["checksum"] = json!(sum);
        out["format_version"] = json!(3);
    }
    out
}
