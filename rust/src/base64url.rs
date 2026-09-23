//! Canonical unpadded RFC 4648 base64url.

use crate::error::{Result, bail};

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

pub fn encode(data: &[u8]) -> String {
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = (b[0] as u32) << 16 | (b[1] as u32) << 8 | b[2] as u32;
        let chars = chunk.len() + 1;
        for i in 0..chars {
            out.push(ALPHABET[(n >> (18 - 6 * i) & 63) as usize] as char);
        }
    }
    out
}

fn sextet(c: u8) -> Option<u32> {
    Some(match c {
        b'A'..=b'Z' => c - b'A',
        b'a'..=b'z' => c - b'a' + 26,
        b'0'..=b'9' => c - b'0' + 52,
        b'-' => 62,
        b'_' => 63,
        _ => return None,
    } as u32)
}

/// Decode, rejecting padding, foreign characters, impossible lengths and a
/// final character with nonzero unused bits.
pub fn decode(text: &str) -> Result<Vec<u8>> {
    let bytes = text.as_bytes();
    if bytes.contains(&b'=') {
        bail!("invalid base64url payload: padding is not allowed");
    }
    if bytes.len() % 4 == 1 {
        bail!("invalid base64url payload: impossible length");
    }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3 + 2);
    for chunk in bytes.chunks(4) {
        let mut n = 0u32;
        for (i, &c) in chunk.iter().enumerate() {
            let Some(v) = sextet(c) else {
                bail!("invalid base64url payload: unexpected character");
            };
            n |= v << (18 - 6 * i);
        }
        let produced = chunk.len() - 1;
        let unused_mask = match chunk.len() {
            2 => 0xffff,
            3 => 0xff,
            _ => 0,
        };
        if n & unused_mask != 0 {
            bail!("invalid base64url payload: noncanonical trailing bits");
        }
        for i in 0..produced {
            out.push((n >> (16 - 8 * i)) as u8);
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_lengths() {
        for len in 0..20usize {
            let data: Vec<u8> = (0..len as u8)
                .map(|b| b.wrapping_mul(37).wrapping_add(250))
                .collect();
            assert_eq!(decode(&encode(&data)).unwrap(), data);
        }
        assert!(decode("oQAB").is_ok());
        assert!(decode("oR").is_err());
        assert!(decode("oQ").is_ok());
        assert!(decode("A").is_err());
        assert!(decode("oQ==").is_err());
    }
}
