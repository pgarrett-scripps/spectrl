//! The CBOR subset spectrl uses: a strict reader and a canonical writer.
//!
//! Reader (section 1): definite lengths only, no tags, simple values limited
//! to false/true/null, finite floats that are not integral safe values,
//! integers within the JavaScript safe range, int or text map keys without
//! duplicates, valid UTF-8, nesting depth at most 32 and at most 100,000 items.
//! Minimal head widths are not required.
//!
//! Writer: shortest heads, shortest exact float width, integral safe floats as
//! integers, map keys sorted by encoded length then bytes.

use std::collections::HashSet;

use crate::error::{Error, Result, bail};

/// 2^53 - 1, the largest integer a binary64 represents exactly with all
/// integers below it.
pub const MAX_SAFE: i64 = 9_007_199_254_740_991;
pub const MAX_DEPTH: usize = 32;
pub const MAX_ITEMS: usize = 100_000;

/// One CBOR data item from the supported subset.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Int(i64),
    Float(f64),
    Bytes(Vec<u8>),
    Text(String),
    Array(Vec<Value>),
    /// Entries in document order (decoding) or insertion order (writing).
    Map(Vec<(Value, Value)>),
    Bool(bool),
    Null,
}

impl Value {
    pub fn as_int(&self) -> Option<i64> {
        match self {
            Value::Int(v) => Some(*v),
            _ => None,
        }
    }

    pub fn as_text(&self) -> Option<&str> {
        match self {
            Value::Text(v) => Some(v),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(v) => Some(v),
            _ => None,
        }
    }

    pub fn as_map(&self) -> Option<&[(Value, Value)]> {
        match self {
            Value::Map(v) => Some(v),
            _ => None,
        }
    }

    /// Look up a map entry by key.
    pub fn get(&self, key: &Value) -> Option<&Value> {
        self.as_map()?
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v)
    }

    /// A short type name for error messages.
    pub fn type_name(&self) -> &'static str {
        match self {
            Value::Int(_) => "integer",
            Value::Float(_) => "float",
            Value::Bytes(_) => "bytes",
            Value::Text(_) => "text",
            Value::Array(_) => "array",
            Value::Map(_) => "map",
            Value::Bool(_) => "boolean",
            Value::Null => "null",
        }
    }

    pub fn text(value: impl Into<String>) -> Value {
        Value::Text(value.into())
    }
}

// ---------------------------------------------------------------------------
// Reader

/// Decode one complete CBOR document. Trailing bytes are an error.
pub fn decode(data: &[u8]) -> Result<Value> {
    let mut reader = Reader {
        data,
        pos: 0,
        items: 0,
    };
    let value = reader.value(1)?;
    if reader.pos != data.len() {
        bail!("invalid CBOR: trailing data after the document");
    }
    Ok(value)
}

struct Reader<'a> {
    data: &'a [u8],
    pos: usize,
    items: usize,
}

#[derive(Hash, PartialEq, Eq)]
enum Key<'a> {
    Int(i64),
    Text(&'a str),
}

impl Reader<'_> {
    fn remaining(&self) -> usize {
        self.data.len() - self.pos
    }

    fn byte(&mut self) -> Result<u8> {
        let Some(&b) = self.data.get(self.pos) else {
            bail!("invalid CBOR: truncated item");
        };
        self.pos += 1;
        Ok(b)
    }

    fn take(&mut self, n: u64) -> Result<&[u8]> {
        if n > self.remaining() as u64 {
            bail!("invalid CBOR: truncated item");
        }
        let n = n as usize;
        let slice = &self.data[self.pos..self.pos + n];
        self.pos += n;
        Ok(slice)
    }

    fn argument(&mut self, info: u8) -> Result<u64> {
        Ok(match info {
            0..=23 => info as u64,
            24 => self.take(1)?[0] as u64,
            25 => u16::from_be_bytes(self.take(2)?.try_into().unwrap()) as u64,
            26 => u32::from_be_bytes(self.take(4)?.try_into().unwrap()) as u64,
            27 => u64::from_be_bytes(self.take(8)?.try_into().unwrap()),
            31 => bail!("invalid CBOR: indefinite lengths are not supported"),
            _ => bail!("invalid CBOR: reserved additional information {info}"),
        })
    }

    fn count(&mut self, n: u64) -> Result<()> {
        if n > (MAX_ITEMS - self.items) as u64 {
            bail!("invalid CBOR: more than {MAX_ITEMS} items");
        }
        self.items += n as usize;
        Ok(())
    }

    fn value(&mut self, depth: usize) -> Result<Value> {
        self.count(1)?;
        let initial = self.byte()?;
        let major = initial >> 5;
        let info = initial & 0x1f;
        match major {
            0 => {
                let n = self.argument(info)?;
                if n > MAX_SAFE as u64 {
                    bail!("invalid CBOR: integer outside the safe integer range");
                }
                Ok(Value::Int(n as i64))
            }
            1 => {
                let n = self.argument(info)?;
                if n > (MAX_SAFE - 1) as u64 {
                    bail!("invalid CBOR: integer outside the safe integer range");
                }
                Ok(Value::Int(-1 - n as i64))
            }
            2 => {
                let n = self.argument(info)?;
                Ok(Value::Bytes(self.take(n)?.to_vec()))
            }
            3 => {
                let n = self.argument(info)?;
                let bytes = self.take(n)?;
                match std::str::from_utf8(bytes) {
                    Ok(s) => Ok(Value::Text(s.to_owned())),
                    Err(_) => bail!("invalid CBOR: text is not valid UTF-8"),
                }
            }
            4 => {
                let n = self.argument(info)?;
                if depth > MAX_DEPTH {
                    bail!("invalid CBOR: nesting deeper than {MAX_DEPTH}");
                }
                // Every element needs at least one byte.
                if n > self.remaining() as u64 {
                    bail!("invalid CBOR: truncated array");
                }
                if n > (MAX_ITEMS - self.items) as u64 {
                    bail!("invalid CBOR: more than {MAX_ITEMS} items");
                }
                let mut items = Vec::with_capacity(n as usize);
                for _ in 0..n {
                    items.push(self.value(depth + 1)?);
                }
                Ok(Value::Array(items))
            }
            5 => {
                let n = self.argument(info)?;
                if depth > MAX_DEPTH {
                    bail!("invalid CBOR: nesting deeper than {MAX_DEPTH}");
                }
                if n > (self.remaining() / 2) as u64 {
                    bail!("invalid CBOR: truncated map");
                }
                if n.saturating_mul(2) > (MAX_ITEMS - self.items) as u64 {
                    bail!("invalid CBOR: more than {MAX_ITEMS} items");
                }
                let mut entries = Vec::with_capacity(n as usize);
                for _ in 0..n {
                    let key = self.value(depth + 1)?;
                    if !matches!(key, Value::Int(_) | Value::Text(_)) {
                        bail!(
                            "invalid CBOR: map keys must be integers or text, not {}",
                            key.type_name()
                        );
                    }
                    let value = self.value(depth + 1)?;
                    entries.push((key, value));
                }
                let mut seen = HashSet::with_capacity(entries.len());
                for (key, _) in &entries {
                    let k = match key {
                        Value::Int(i) => Key::Int(*i),
                        Value::Text(s) => Key::Text(s),
                        _ => unreachable!(),
                    };
                    if !seen.insert(k) {
                        bail!("invalid CBOR: duplicate map key");
                    }
                }
                Ok(Value::Map(entries))
            }
            6 => bail!("invalid CBOR: tags are not supported"),
            _ => match info {
                20 => Ok(Value::Bool(false)),
                21 => Ok(Value::Bool(true)),
                22 => Ok(Value::Null),
                23 => bail!("invalid CBOR: undefined is not supported"),
                25 => {
                    let bits = u16::from_be_bytes(self.take(2)?.try_into().unwrap());
                    float(f16_to_f64(bits))
                }
                26 => {
                    let bits = u32::from_be_bytes(self.take(4)?.try_into().unwrap());
                    float(f32::from_bits(bits) as f64)
                }
                27 => {
                    let bits = u64::from_be_bytes(self.take(8)?.try_into().unwrap());
                    float(f64::from_bits(bits))
                }
                31 => bail!("invalid CBOR: unexpected break"),
                _ => bail!("invalid CBOR: unsupported simple value"),
            },
        }
    }
}

fn float(v: f64) -> Result<Value> {
    if !v.is_finite() {
        bail!("invalid CBOR: non-finite number");
    }
    if is_integral_safe(v) {
        bail!("invalid CBOR: integral float must be written as an integer");
    }
    Ok(Value::Float(v))
}

/// True for a finite value that is a whole number within the safe range,
/// including both zeros.
pub fn is_integral_safe(v: f64) -> bool {
    v.is_finite() && v.trunc() == v && v.abs() <= MAX_SAFE as f64
}

fn f16_to_f64(bits: u16) -> f64 {
    let sign = if bits & 0x8000 != 0 { -1.0 } else { 1.0 };
    let exp = ((bits >> 10) & 0x1f) as i32;
    let mant = (bits & 0x3ff) as f64;
    let magnitude = match exp {
        0 => mant * 2f64.powi(-24),
        31 => {
            if mant == 0.0 {
                f64::INFINITY
            } else {
                f64::NAN
            }
        }
        _ => (1.0 + mant / 1024.0) * 2f64.powi(exp - 15),
    };
    sign * magnitude
}

// ---------------------------------------------------------------------------
// Writer

/// Encode a value canonically. Fails on a non-finite float, an integer
/// outside the safe range, an unsupported map key, or a duplicate key after
/// canonicalization (for example `2` and `2.0`).
pub fn encode(value: &Value) -> Result<Vec<u8>> {
    let mut out = Vec::new();
    write(value, &mut out)?;
    Ok(out)
}

fn head(major: u8, n: u64, out: &mut Vec<u8>) {
    let m = major << 5;
    if n < 24 {
        out.push(m | n as u8);
    } else if n <= 0xff {
        out.push(m | 24);
        out.push(n as u8);
    } else if n <= 0xffff {
        out.push(m | 25);
        out.extend_from_slice(&(n as u16).to_be_bytes());
    } else if n <= 0xffff_ffff {
        out.push(m | 26);
        out.extend_from_slice(&(n as u32).to_be_bytes());
    } else {
        out.push(m | 27);
        out.extend_from_slice(&n.to_be_bytes());
    }
}

fn write_int(v: i64, out: &mut Vec<u8>) -> Result<()> {
    if !(-MAX_SAFE..=MAX_SAFE).contains(&v) {
        return Err(Error::encode("integer outside the safe integer range"));
    }
    if v >= 0 {
        head(0, v as u64, out);
    } else {
        head(1, (-1 - v) as u64, out);
    }
    Ok(())
}

fn write(value: &Value, out: &mut Vec<u8>) -> Result<()> {
    match value {
        Value::Int(v) => write_int(*v, out)?,
        Value::Float(v) => {
            let v = *v;
            if !v.is_finite() {
                return Err(Error::encode("non-finite numbers cannot be encoded"));
            }
            if is_integral_safe(v) {
                write_int(v as i64, out)?;
            } else if let Some(half) = f64_to_f16_exact(v) {
                out.push(0xf9);
                out.extend_from_slice(&half.to_be_bytes());
            } else if (v as f32) as f64 == v {
                out.push(0xfa);
                out.extend_from_slice(&(v as f32).to_bits().to_be_bytes());
            } else {
                out.push(0xfb);
                out.extend_from_slice(&v.to_bits().to_be_bytes());
            }
        }
        Value::Bytes(b) => {
            head(2, b.len() as u64, out);
            out.extend_from_slice(b);
        }
        Value::Text(s) => {
            head(3, s.len() as u64, out);
            out.extend_from_slice(s.as_bytes());
        }
        Value::Array(items) => {
            head(4, items.len() as u64, out);
            for item in items {
                write(item, out)?;
            }
        }
        Value::Map(entries) => {
            let mut encoded = Vec::with_capacity(entries.len());
            for (k, v) in entries {
                if !matches!(k, Value::Int(_) | Value::Text(_)) {
                    return Err(Error::encode(format!(
                        "map keys must be integers or text, not {}",
                        k.type_name()
                    )));
                }
                encoded.push((encode(k)?, v));
            }
            encoded.sort_by(|a, b| a.0.len().cmp(&b.0.len()).then_with(|| a.0.cmp(&b.0)));
            for pair in encoded.windows(2) {
                if pair[0].0 == pair[1].0 {
                    return Err(Error::encode("duplicate map key"));
                }
            }
            head(5, encoded.len() as u64, out);
            for (k, v) in encoded {
                out.extend_from_slice(&k);
                write(v, out)?;
            }
        }
        Value::Bool(b) => out.push(if *b { 0xf5 } else { 0xf4 }),
        Value::Null => out.push(0xf6),
    }
    Ok(())
}

/// The binary16 bits of `v` when binary16 holds it exactly.
fn f64_to_f16_exact(v: f64) -> Option<u16> {
    if !v.is_finite() || v == 0.0 {
        return None;
    }
    let sign: u16 = if v.is_sign_negative() { 0x8000 } else { 0 };
    let a = v.abs();
    if a > 65504.0 || a < 2f64.powi(-24) {
        return None;
    }
    let bits = a.to_bits();
    let e = ((bits >> 52) & 0x7ff) as i32 - 1023;
    let mant = bits & ((1u64 << 52) - 1);
    if e >= -14 {
        if mant & ((1u64 << 42) - 1) != 0 {
            return None;
        }
        Some(sign | (((e + 15) as u16) << 10) | (mant >> 42) as u16)
    } else {
        let k = a * 2f64.powi(24);
        if k.trunc() != k || k >= 1024.0 {
            return None;
        }
        Some(sign | k as u16)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn half_precision_round_trip() {
        for bits in 0u16..=0xffff {
            let v = f16_to_f64(bits);
            if !v.is_finite() || v == 0.0 {
                continue;
            }
            assert_eq!(f64_to_f16_exact(v), Some(bits), "{bits:#x}");
        }
        assert_eq!(f64_to_f16_exact(0.1), None);
        assert_eq!(f64_to_f16_exact(65520.0), None);
    }

    #[test]
    fn canonical_floats() {
        assert_eq!(encode(&Value::Float(1.5)).unwrap(), [0xf9, 0x3e, 0x00]);
        assert_eq!(encode(&Value::Float(2.0)).unwrap(), [0x02]);
        assert_eq!(encode(&Value::Float(-0.0)).unwrap(), [0x00]);
        assert_eq!(encode(&Value::Float(1e20)).unwrap()[0], 0xfb);
        assert_eq!(encode(&Value::Float(1.0000001192092896)).unwrap()[0], 0xfa);
        assert_eq!(encode(&Value::Float(0.1)).unwrap()[0], 0xfb);
    }
}
