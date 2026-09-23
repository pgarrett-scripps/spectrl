//! Every entry of every shared vector file under `../test-vectors/`.

use std::path::PathBuf;

use serde_json::{Value as Json, json};
use spectrl::cbor::{self, Value};
use spectrl::codecs::{self, Array, DType, Encoding, Rounded};
use spectrl::framing::{self, Mode};
use spectrl::json::{cbor_json, from_hex, spectrum_from_json, spectrum_to_json, to_hex};
use spectrl::{
    Compression, EncodeOptions, Error, Spectrum, decode_token, encode_spectrum, inspect_token,
};

fn vectors_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../test-vectors")
}

fn load(name: &str) -> Json {
    let path = vectors_dir().join(name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    serde_json::from_str(&text).unwrap()
}

fn entries(doc: &Json) -> Vec<Json> {
    match doc {
        Json::Array(a) => a.clone(),
        _ => doc["vectors"].as_array().expect("a vectors list").clone(),
    }
}

fn raw_token(cbor_bytes: &[u8]) -> String {
    framing::frame(Mode::Raw, cbor_bytes)
}

/// `expected` must be contained in `actual`: object keys of `expected` only,
/// a missing key matching null, lists of equal length, numbers compared as
/// binary64 with the tolerance where `tol` is set.
fn contains(
    actual: &Json,
    expected: &Json,
    tol: Option<(f64, f64)>,
    path: &str,
) -> Result<(), String> {
    match (actual, expected) {
        (Json::Number(a), Json::Number(e)) => {
            let (a, e) = (a.as_f64().unwrap(), e.as_f64().unwrap());
            let ok = match tol {
                Some((abs, rel)) => (a - e).abs() <= abs + rel * e.abs(),
                None => a == e,
            };
            if ok {
                Ok(())
            } else {
                Err(format!("{path}: {a:?} != {e:?}"))
            }
        }
        (Json::Object(a), Json::Object(e)) => {
            for (k, ev) in e {
                let av = a.get(k).unwrap_or(&Json::Null);
                // Tolerance covers array values only; metadata is exact.
                let array_key = matches!(
                    k.as_str(),
                    "mz" | "intensity" | "charge" | "extra_arrays" | "values"
                );
                let child_tol = if array_key || path.contains(".extra_arrays.") {
                    tol
                } else {
                    None
                };
                contains(av, ev, child_tol, &format!("{path}.{k}"))?;
            }
            Ok(())
        }
        (Json::Array(a), Json::Array(e)) => {
            if a.len() != e.len() {
                return Err(format!("{path}: length {} != {}", a.len(), e.len()));
            }
            for (i, (av, ev)) in a.iter().zip(e).enumerate() {
                contains(av, ev, tol, &format!("{path}[{i}]"))?;
            }
            Ok(())
        }
        (Json::Array(a), Json::Object(e)) if e.is_empty() && a.is_empty() => Ok(()),
        _ if actual == expected => Ok(()),
        _ => Err(format!("{path}: {actual} != {expected}")),
    }
}

/// The decoded form the vectors record: extra arrays as `{dtype, values}`.
fn decoded_json(token: &str) -> Result<Json, Error> {
    let d = decode_token(token)?;
    let mut out = spectrum_to_json(&d.spectrum, Some(&d.checksum));
    out["extra_arrays"] = Json::Object(
        d.spectrum
            .extra_arrays
            .iter()
            .map(|(k, a)| {
                (
                    k.clone(),
                    json!({"dtype": a.dtype().name(), "values": spectrl::json::array_json(a)}),
                )
            })
            .collect(),
    );
    Ok(out)
}

fn check_decoded_vectors(file: &str) {
    let doc = load(file);
    let list = entries(&doc);
    assert!(!list.is_empty());
    let mut failures = Vec::new();
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let token = v["token"].as_str().unwrap();
        let t = &v["tolerance"];
        let tol = (
            t["abs"].as_f64().unwrap_or(0.0),
            t["rel"].as_f64().unwrap_or(0.0),
        );
        let tol = if v["mode"] == "lossless" {
            (0.0, 0.0)
        } else {
            tol
        };
        match decoded_json(token) {
            Err(e) => failures.push(format!("{name}: {e}")),
            Ok(actual) => {
                if let Err(e) = contains(&actual, &v["decoded"], Some(tol), name) {
                    failures.push(e);
                }
            }
        }
        // Inspection agrees on the array list.
        let info = inspect_token(token).unwrap_or_else(|e| panic!("{name}: inspect: {e}"));
        let d = decode_token(token).unwrap();
        assert_eq!(info.len(), d.spectrum.arrays().len(), "{name}");
    }
    assert!(
        failures.is_empty(),
        "{file}: {} of {} failed:\n{}",
        failures.len(),
        list.len(),
        failures.join("\n")
    );
    eprintln!("{file}: {} entries passed", list.len());
}

#[test]
fn vectors_json() {
    check_decoded_vectors("vectors.json");
}

#[test]
fn reverse_vectors_json() {
    check_decoded_vectors("reverse-vectors.json");
}

#[test]
fn negative_vectors_json() {
    let list = entries(&load("negative-vectors.json"));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let bytes = from_hex(v["cbor_hex"].as_str().unwrap()).unwrap();
        let err = match decode_token(&raw_token(&bytes)) {
            Ok(_) => panic!("{name}: accepted"),
            Err(e) => e.to_string(),
        };
        let wanted = v["error"].as_str().unwrap();
        assert!(
            wanted.split('|').any(|w| err.contains(w)),
            "{name}: error {err:?} does not mention {wanted:?}"
        );
    }
    eprintln!("negative-vectors.json: {} entries passed", list.len());
}

#[test]
fn cbor_hardening_json() {
    let list = entries(&load("cbor-hardening.json"));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let token = raw_token(&from_hex(v["hex"].as_str().unwrap()).unwrap());
        assert!(decode_token(&token).is_err(), "{name}: decode accepted");
        assert!(inspect_token(&token).is_err(), "{name}: inspect accepted");
    }
    eprintln!("cbor-hardening.json: {} entries passed", list.len());
}

#[test]
fn outer_payload_json() {
    let doc = load("outer-payload.json");
    let valid = doc["valid"].as_array().unwrap();
    for v in valid {
        let name = v["name"].as_str().unwrap();
        let token = v["token"].as_str().unwrap();
        let frame = framing::split(token).unwrap_or_else(|e| panic!("{name}: {e}"));
        if cfg!(not(feature = "brotli")) && frame.mode == framing::Mode::Brotli {
            continue; // this build reports Brotli as unsupported
        }
        let bytes = framing::expand(&frame).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(to_hex(&bytes), v["cbor_hex"].as_str().unwrap(), "{name}");
        let d = decode_token(token).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(d.spectrum.default_array_length, 0, "{name}");
        assert!(inspect_token(token).unwrap().is_empty(), "{name}");
    }
    let invalid = doc["invalid"].as_array().unwrap();
    for v in invalid {
        let name = v["name"].as_str().unwrap();
        let token = v["token"].as_str().unwrap();
        let wanted = v["error"].as_str().unwrap();
        let skip_brotli = cfg!(not(feature = "brotli"))
            && framing::split(token).is_ok_and(|f| f.mode == framing::Mode::Brotli);
        if skip_brotli {
            continue; // this build rejects every Brotli token as unsupported
        }
        for (reader, result) in [
            ("decode", decode_token(token).map(|_| ())),
            ("inspect", inspect_token(token).map(|_| ())),
        ] {
            let err = result
                .err()
                .unwrap_or_else(|| panic!("{name}: {reader} accepted"))
                .to_string();
            assert!(
                err.contains(wanted),
                "{name}: {reader} error {err:?} does not mention {wanted:?}"
            );
        }
    }
    eprintln!(
        "outer-payload.json: {} valid and {} invalid entries passed",
        valid.len(),
        invalid.len()
    );
}

#[test]
fn adversarial_vectors_json() {
    let list = entries(&load("adversarial-vectors.json"));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let token = v["token"].as_str().unwrap();
        let accepted = std::panic::catch_unwind(|| decode_token(token).is_ok())
            .unwrap_or_else(|_| panic!("{name}: panicked instead of returning a decode error"));
        assert_eq!(accepted, v["expect"] == "accept", "{name} ({})", v["rule"]);
    }
    eprintln!("adversarial-vectors.json: {} entries passed", list.len());
}

fn dtype_of(tail: i64) -> DType {
    DType::from_tail(tail).expect("known type")
}

#[test]
fn rounded_float_json() {
    let list = entries(&load("rounded-float.json"));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let dtype = dtype_of(v["type"].as_i64().unwrap());
        let p = &v["parameters"];
        let enc = Encoding::Rounded(Rounded {
            bits: p["bits"].as_u64().unwrap() as u32,
            width: p["width"].as_u64().unwrap() as usize,
        });
        let count = v["count"].as_u64().unwrap() as usize;
        let source =
            Array::from_le_bytes(dtype, &from_hex(v["source_hex"].as_str().unwrap()).unwrap());
        let (blob, out_type) =
            codecs::encode(&source, &enc).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(out_type, dtype, "{name}");
        assert_eq!(
            to_hex(&blob),
            v["blob_hex"].as_str().unwrap(),
            "{name}: blob"
        );
        let back = codecs::decode(&blob, count, dtype, &enc).unwrap();
        assert_eq!(
            to_hex(&back.to_le_bytes()),
            v["decoded_hex"].as_str().unwrap(),
            "{name}: decode"
        );
        let d =
            decode_token(v["token"].as_str().unwrap()).unwrap_or_else(|e| panic!("{name}: {e}"));
        let got = d.spectrum.intensity.as_ref().expect("intensity");
        assert_eq!(got.dtype(), dtype, "{name}");
        assert_eq!(
            to_hex(&got.to_le_bytes()),
            v["decoded_hex"].as_str().unwrap(),
            "{name}: token"
        );
    }
    eprintln!("rounded-float.json: {} entries passed", list.len());
}

/// A header as the pipeline vectors record it: integer keys as text, byte
/// strings as `"<bytes>"`.
fn header_json(v: &Value) -> Json {
    match v {
        Value::Bytes(_) => json!("<bytes>"),
        Value::Array(a) => Json::Array(a.iter().map(header_json).collect()),
        Value::Map(m) => Json::Object(
            m.iter()
                .map(|(k, v)| {
                    let key = match k {
                        Value::Int(i) => i.to_string(),
                        Value::Text(s) => s.clone(),
                        other => cbor_json(other).to_string(),
                    };
                    (key, header_json(v))
                })
                .collect(),
        ),
        other => cbor_json(other),
    }
}

#[test]
fn v3_pipelines_json() {
    let list = entries(&load("v3-pipelines.json"));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let token = v["token"].as_str().unwrap();
        let d = decode_token(token).unwrap_or_else(|e| panic!("{name}: {e}"));
        let dtype = DType::from_name(v["dtype"].as_str().unwrap()).unwrap();
        for a in [&d.spectrum.mz, &d.spectrum.intensity] {
            let a = a
                .as_ref()
                .unwrap_or_else(|| panic!("{name}: missing array"));
            assert_eq!(a.dtype(), dtype, "{name}");
            assert_eq!(
                to_hex(&a.to_le_bytes()),
                v["hex"].as_str().unwrap(),
                "{name}"
            );
        }
        let frame = framing::split(token).unwrap();
        let root = cbor::decode(&framing::expand(&frame).unwrap()).unwrap();
        contains(&header_json(&root), &v["metadata"], None, name).unwrap();
        contains(&v["metadata"], &header_json(&root), None, name).unwrap();
    }
    eprintln!("v3-pipelines.json: {} entries passed", list.len());
}

fn check_delta(file: &str) {
    let list = entries(&load(file));
    for v in &list {
        let name = v["name"].as_str().unwrap();
        let width = v["item_size"].as_u64().unwrap() as usize;
        let raw = from_hex(v["raw_hex"].as_str().unwrap()).unwrap();
        let shuffled = codecs::delta_shuffle(&raw, width);
        assert_eq!(
            to_hex(&shuffled),
            v["shuffled_hex"].as_str().unwrap(),
            "{name}"
        );
        assert_eq!(codecs::undelta_unshuffle(&shuffled, width), raw, "{name}");
        assert_eq!(
            to_hex(&framing::deflate(&shuffled)),
            v["zlib_hex"].as_str().unwrap(),
            "{name}: zlib"
        );
    }
    eprintln!("{file}: {} entries passed", list.len());
}

#[test]
fn delta_proposal_json() {
    check_delta("delta-proposal.json");
}

#[test]
fn delta_proposal_reverse_json() {
    check_delta("delta-proposal-reverse.json");
}

#[test]
fn token_parity_json() {
    let expected = load("token-parity.json");
    let inputs = load("token-parity-inputs.json");
    let mut count = 0;
    for case in inputs.as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let spectrum: Spectrum =
            spectrum_from_json(&case["spec"]).unwrap_or_else(|e| panic!("{name}: {e}"));
        for (profile, lossless) in [("lossless", true), ("lossy", false)] {
            let token = encode_spectrum(
                &spectrum,
                EncodeOptions {
                    lossless,
                    compression: Compression::Raw,
                },
            )
            .unwrap_or_else(|e| panic!("{name}/{profile}: {e}"));
            assert_eq!(
                token,
                expected[name][profile].as_str().unwrap(),
                "{name}/{profile}"
            );
            decode_token(&token).unwrap_or_else(|e| panic!("{name}/{profile}: own token: {e}"));
            count += 1;
        }
    }
    assert_eq!(count, 2 * expected.as_object().unwrap().len());
    eprintln!("token-parity.json: {count} tokens identical");
}
