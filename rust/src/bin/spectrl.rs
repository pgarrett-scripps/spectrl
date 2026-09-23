//! `spectrl` command-line tool: encode, decode, inspect, and a JSON-lines
//! batch mode used by the cross-implementation parity harnesses.

use std::io::{self, BufRead, Read, Write};
use std::panic::{self, AssertUnwindSafe};
use std::process::ExitCode;

use serde_json::{Value as Json, json};
use spectrl::json::{number, spectrum_from_json, spectrum_to_json, to_hex};
use spectrl::{
    ArrayInfo, Compression, EncodeOptions, decode_token, encode_spectrum, inspect_token,
};

const USAGE: &str = "\
usage:
  spectrl encode [--lossless] [--compression raw|zlib|brotli|auto] [FILE|-]
      read a spectrum_to_dict JSON object, print the token
  spectrl decode [TOKEN|-]      print the decoded spectrum as JSON
  spectrl inspect [TOKEN|-]     print the array descriptors as JSON, without decoding values
  spectrl batch                 JSON lines on stdin, one result line per request:
      {\"op\":\"encode\",\"name\",\"spec\",\"options\":{\"lossless\",\"compression\"}}
      {\"op\":\"verdict\",\"token\"}   {\"op\":\"decode\",\"token\"}   {\"op\":\"inspect\",\"token\"}
  spectrl --version";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("encode") => cmd_encode(&args[1..]),
        Some("decode") => read_arg(&args[1..]).and_then(|t| {
            let d = decode_token(t.trim()).map_err(|e| e.to_string())?;
            Ok(spectrum_to_json(&d.spectrum, Some(&d.checksum)).to_string())
        }),
        Some("inspect") => read_arg(&args[1..]).and_then(|t| {
            let info = inspect_token(t.trim()).map_err(|e| e.to_string())?;
            Ok(Json::Array(info.iter().map(info_json).collect()).to_string())
        }),
        Some("batch") => return batch(),
        Some("--version" | "-V") => Ok(format!("spectrl {}", env!("CARGO_PKG_VERSION"))),
        Some("--help" | "-h") => Ok(USAGE.to_string()),
        _ => Err(USAGE.to_string()),
    };
    match result {
        Ok(text) => {
            println!("{text}");
            ExitCode::SUCCESS
        }
        Err(message) => {
            eprintln!("spectrl: {message}");
            ExitCode::FAILURE
        }
    }
}

fn read_arg(args: &[String]) -> Result<String, String> {
    match args {
        [] => read_stdin(),
        [a] if a == "-" => read_stdin(),
        [a] => Ok(a.clone()),
        _ => Err(USAGE.to_string()),
    }
}

fn read_stdin() -> Result<String, String> {
    let mut s = String::new();
    io::stdin()
        .read_to_string(&mut s)
        .map_err(|e| e.to_string())?;
    Ok(s)
}

fn cmd_encode(args: &[String]) -> Result<String, String> {
    let mut options = EncodeOptions::default();
    let mut file = None;
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--lossless" => options.lossless = true,
            "--compression" => {
                let name = it.next().ok_or("--compression needs a value")?;
                options.compression = Compression::from_name(name)
                    .ok_or_else(|| format!("unknown compression {name:?}"))?;
            }
            _ if file.is_none() => file = Some(a.clone()),
            _ => return Err(USAGE.to_string()),
        }
    }
    let text = match file.as_deref() {
        None | Some("-") => read_stdin()?,
        Some(path) => std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?,
    };
    let value: Json = serde_json::from_str(&text).map_err(|e| format!("invalid JSON: {e}"))?;
    let spectrum = spectrum_from_json(&value).map_err(|e| e.to_string())?;
    encode_spectrum(&spectrum, options).map_err(|e| e.to_string())
}

fn info_json(a: &ArrayInfo) -> Json {
    json!({
        "key": a.key,
        "array_type": a.array_type,
        "name": a.name,
        "dtype": a.dtype.name(),
        "operation": spectrl::json::cbor_json(&a.operation.to_value()),
        "fidelity": a.fidelity,
        "available": a.available,
        "byte_count": a.byte_count,
        "unit_accession": a.unit,
    })
}

fn f64_hex(a: Option<&spectrl::Array>) -> Json {
    a.map_or(Json::Null, |a| {
        Json::String(to_hex(
            &a.to_f64()
                .iter()
                .flat_map(|v| v.to_le_bytes())
                .collect::<Vec<u8>>(),
        ))
    })
}

fn encode_request(req: &Json) -> Json {
    let name = req.get("name").cloned().unwrap_or(Json::Null);
    let run = || -> Result<Json, String> {
        let spec = req.get("spec").ok_or("missing spec")?;
        let o = req.get("options").cloned().unwrap_or(json!({}));
        let options = EncodeOptions {
            lossless: o.get("lossless").and_then(Json::as_bool).unwrap_or(false),
            compression: match o.get("compression").and_then(Json::as_str) {
                None => Compression::default(),
                Some(c) => {
                    Compression::from_name(c).ok_or_else(|| format!("unknown compression {c:?}"))?
                }
            },
        };
        let spectrum = spectrum_from_json(spec).map_err(|e| e.to_string())?;
        let token = encode_spectrum(&spectrum, options).map_err(|e| e.to_string())?;
        let d = decode_token(&token).map_err(|e| format!("decoding own token: {e}"))?;
        let s = &d.spectrum;
        Ok(json!({"name": name, "token": token, "decoded": {
            "mz": f64_hex(s.mz.as_ref()), "intensity": f64_hex(s.intensity.as_ref()), "charge": f64_hex(s.charge.as_ref()),
        }}))
    };
    run().unwrap_or_else(|e| json!({"name": name, "error": e}))
}

/// The verdict shape `scripts/adversarial_corpus.py` produces.
fn verdict(token: &str) -> Json {
    match decode_token(token) {
        Err(_) => json!({"ok": false}),
        Ok(d) => {
            let s = &d.spectrum;
            json!({
                "ok": true,
                "n": s.default_array_length,
                "nparams": s.params.len(),
                "nuser": s.user_params.len(),
                "arrays": s.extra_arrays.keys().collect::<Vec<_>>(),
                "mz": s.mz.as_ref().map(|a| a.to_f64().into_iter().take(3).map(number).collect::<Vec<_>>()),
                "units": s.array_units,
            })
        }
    }
}

fn handle(req: &Json) -> Json {
    let token = || req.get("token").and_then(Json::as_str).unwrap_or("");
    match req.get("op").and_then(Json::as_str) {
        Some("encode") => encode_request(req),
        Some("verdict") => verdict(token()),
        Some("decode") => match decode_token(token()) {
            Ok(d) => {
                json!({"ok": true, "decoded": spectrum_to_json(&d.spectrum, Some(&d.checksum))})
            }
            Err(e) => json!({"ok": false, "error": e.to_string()}),
        },
        Some("inspect") => match inspect_token(token()) {
            Ok(info) => {
                json!({"ok": true, "arrays": info.iter().map(info_json).collect::<Vec<_>>()})
            }
            Err(e) => json!({"ok": false, "error": e.to_string()}),
        },
        other => json!({"ok": false, "error": format!("unknown op {other:?}")}),
    }
}

fn batch() -> ExitCode {
    // A panic is reported as an escape in the result line, not on stderr.
    panic::set_hook(Box::new(|_| {}));
    let stdin = io::stdin();
    let mut out = io::BufWriter::new(io::stdout().lock());
    for line in stdin.lock().lines() {
        let Ok(line) = line else {
            return ExitCode::FAILURE;
        };
        if line.trim().is_empty() {
            continue;
        }
        let result = match serde_json::from_str::<Json>(&line) {
            Err(e) => json!({"ok": false, "error": format!("invalid JSON request: {e}")}),
            Ok(req) => panic::catch_unwind(AssertUnwindSafe(|| handle(&req))).unwrap_or_else(|p| {
                let message = p
                    .downcast_ref::<String>()
                    .cloned()
                    .or_else(|| p.downcast_ref::<&str>().map(|s| s.to_string()))
                    .unwrap_or_default();
                json!({"ok": false, "escape": "panic", "message": message.chars().take(200).collect::<String>()})
            }),
        };
        if writeln!(out, "{result}").is_err() {
            return ExitCode::FAILURE;
        }
    }
    let _ = out.flush();
    ExitCode::SUCCESS
}
