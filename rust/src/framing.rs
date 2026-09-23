//! Token framing (section 1): five parts, CRC-32, canonical base64url, and
//! bounded payload expansion.

use flate2::{Compress, Compression, Decompress, FlushCompress, FlushDecompress, Status};

use crate::base64url;
use crate::error::{Error, Result, bail};

/// Limit for both the base64url-decoded payload and the expanded CBOR.
pub const MAX_PAYLOAD_BYTES: usize = 16 * 1024 * 1024;
pub const MAGIC: &str = "spectrl";
pub const VERSION: &str = "v3";
pub const ZLIB_LEVEL: u32 = 6;
pub const BROTLI_QUALITY: u32 = 5;
pub const BROTLI_LGWIN: u32 = 22;

/// Payload compression, as written in the third token part.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum Mode {
    Raw,
    Zlib,
    Brotli,
}

impl Mode {
    pub fn letter(self) -> char {
        match self {
            Mode::Raw => 'r',
            Mode::Zlib => 'z',
            Mode::Brotli => 'b',
        }
    }

    pub fn from_letter(text: &str) -> Option<Mode> {
        match text {
            "r" => Some(Mode::Raw),
            "z" => Some(Mode::Zlib),
            "b" => Some(Mode::Brotli),
            _ => None,
        }
    }
}

/// The checksum string for the text before the last dot.
pub fn checksum(prefix: &str) -> String {
    format!("{:08x}", crc32fast::hash(prefix.as_bytes()))
}

/// A token split into its parts, checksum verified.
pub struct Frame<'a> {
    pub mode: Mode,
    pub payload: &'a str,
    pub checksum: &'a str,
}

/// Check the five-part shape, identifier, version, mode and checksum.
pub fn split(token: &str) -> Result<Frame<'_>> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 5 {
        bail!(
            "a spectrl token has exactly five dot-separated parts, found {}",
            parts.len()
        );
    }
    if parts[0] != MAGIC {
        bail!("not a spectrl token: identifier {:?}", parts[0]);
    }
    if parts[1] != VERSION {
        bail!(
            "unsupported spectrl version {:?}; this reader supports v3 only",
            parts[1]
        );
    }
    let Some(mode) = Mode::from_letter(parts[2]) else {
        bail!("unsupported payload mode {:?}", parts[2]);
    };
    let sum = parts[4];
    if sum.len() != 8
        || !sum
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        bail!("checksum must be eight lowercase hexadecimal characters");
    }
    let prefix = &token[..token.len() - 9];
    if checksum(prefix) != sum {
        bail!("checksum mismatch: the token is corrupted or incomplete");
    }
    Ok(Frame {
        mode,
        payload: parts[3],
        checksum: sum,
    })
}

/// Decode the payload text and expand it to CBOR bytes, bounded.
pub fn expand(frame: &Frame<'_>) -> Result<Vec<u8>> {
    // Four base64url characters carry three bytes; reject before decoding.
    if frame.payload.len() / 4 * 3 > MAX_PAYLOAD_BYTES + 2 {
        bail!("payload exceeds the 16 MiB limit");
    }
    let payload = base64url::decode(frame.payload)?;
    if payload.len() > MAX_PAYLOAD_BYTES {
        bail!("payload exceeds the 16 MiB limit");
    }
    match frame.mode {
        Mode::Raw => Ok(payload),
        Mode::Zlib => inflate(&payload),
        Mode::Brotli => brotli_expand(&payload),
    }
}

fn zlib_error(detail: &str) -> Error {
    Error::decode(format!("invalid compressed CBOR payload: {detail}"))
}

/// One RFC 1950 stream, no preset dictionary, nothing after it.
pub fn inflate(data: &[u8]) -> Result<Vec<u8>> {
    if data.len() < 2 {
        return Err(zlib_error("truncated zlib stream"));
    }
    let (cmf, flg) = (data[0], data[1]);
    if cmf & 0x0f != 8 || cmf >> 4 > 7 || ((cmf as u16) << 8 | flg as u16) % 31 != 0 {
        return Err(zlib_error("not a zlib stream"));
    }
    if flg & 0x20 != 0 {
        return Err(zlib_error("preset dictionaries are not allowed"));
    }
    let mut inflater = Decompress::new(true);
    let mut out = Vec::new();
    let mut buf = vec![0u8; 64 * 1024];
    loop {
        let before_in = inflater.total_in() as usize;
        let before_out = inflater.total_out();
        let status = inflater
            .decompress(&data[before_in..], &mut buf, FlushDecompress::None)
            .map_err(|e| zlib_error(&e.to_string()))?;
        let produced = (inflater.total_out() - before_out) as usize;
        if out.len() + produced > MAX_PAYLOAD_BYTES {
            bail!("invalid compressed CBOR payload: expanded CBOR exceeds the 16 MiB limit");
        }
        out.extend_from_slice(&buf[..produced]);
        match status {
            Status::StreamEnd => break,
            Status::Ok | Status::BufError => {
                let consumed = inflater.total_in() as usize - before_in;
                if produced == 0 && consumed == 0 {
                    return Err(zlib_error("truncated zlib stream"));
                }
            }
        }
    }
    if inflater.total_in() as usize != data.len() {
        return Err(zlib_error("trailing data after the zlib stream"));
    }
    Ok(out)
}

pub fn deflate(data: &[u8]) -> Vec<u8> {
    let mut compressor = Compress::new(Compression::new(ZLIB_LEVEL), true);
    let mut out = Vec::with_capacity(data.len() / 2 + 64);
    loop {
        if out.capacity() - out.len() < 1024 {
            out.reserve(out.capacity().max(4096));
        }
        let before_in = compressor.total_in() as usize;
        let status = compressor
            .compress_vec(&data[before_in..], &mut out, FlushCompress::Finish)
            .expect("zlib deflate with in-memory buffers cannot fail");
        if status == Status::StreamEnd {
            return out;
        }
    }
}

// Brotli goes through the reference C library (via `brotlic`), the same code
// the Python and Node writers call, because the pure-Rust encoder chooses
// different (valid) bit streams at quality 5. See SPEC-NOTES.md.
#[cfg(feature = "brotli")]
fn brotli_expand(data: &[u8]) -> Result<Vec<u8>> {
    use brotlic::BrotliDecoder;
    use brotlic::decode::DecoderInfo;

    let mut decoder = BrotliDecoder::new();
    let mut out = Vec::new();
    let mut buf = vec![0u8; 64 * 1024];
    let mut in_off = 0usize;
    loop {
        let step = decoder
            .decompress(&data[in_off..], &mut buf)
            .map_err(|_| zlib_error("corrupt Brotli stream"))?;
        in_off += step.bytes_read;
        if out.len() + step.bytes_written > MAX_PAYLOAD_BYTES {
            bail!("invalid compressed CBOR payload: expanded CBOR exceeds the 16 MiB limit");
        }
        out.extend_from_slice(&buf[..step.bytes_written]);
        match step.info {
            DecoderInfo::Finished => break,
            DecoderInfo::NeedsMoreOutput => continue,
            DecoderInfo::NeedsMoreInput => return Err(zlib_error("truncated Brotli stream")),
        }
    }
    if in_off != data.len() {
        return Err(zlib_error("trailing data after the Brotli stream"));
    }
    Ok(out)
}

#[cfg(not(feature = "brotli"))]
fn brotli_expand(_data: &[u8]) -> Result<Vec<u8>> {
    Err(Error::unsupported(
        "Brotli payloads need the `brotli` feature, which this build omits",
    ))
}

#[cfg(feature = "brotli")]
pub fn brotli_compress(data: &[u8]) -> Result<Vec<u8>> {
    use brotlic::{CompressionMode, Quality, WindowSize, compress, compress_bound};

    let quality = Quality::new(BROTLI_QUALITY as u8).expect("quality 5 is valid");
    let window = WindowSize::new(BROTLI_LGWIN as u8).expect("lgwin 22 is valid");
    let mut out = vec![0u8; compress_bound(data.len(), quality).unwrap_or(data.len() + 1024)];
    let n = compress(data, &mut out, quality, window, CompressionMode::Generic)
        .map_err(|_| Error::encode("Brotli compression failed"))?;
    out.truncate(n);
    Ok(out)
}

#[cfg(not(feature = "brotli"))]
pub fn brotli_compress(_data: &[u8]) -> Result<Vec<u8>> {
    Err(Error::unsupported(
        "Brotli payloads need the `brotli` feature, which this build omits",
    ))
}

pub fn brotli_available() -> bool {
    cfg!(feature = "brotli")
}

/// Frame a payload that is already compressed for `mode`.
pub fn frame(mode: Mode, payload: &[u8]) -> String {
    let prefix = format!(
        "{MAGIC}.{VERSION}.{}.{}",
        mode.letter(),
        base64url::encode(payload)
    );
    let sum = checksum(&prefix);
    format!("{prefix}.{sum}")
}
