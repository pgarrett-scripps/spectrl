//! The single error type every public operation returns.

use std::fmt;

/// What went wrong, in terms a caller can act on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ErrorKind {
    /// The token, payload, CBOR document or header violates the format.
    Decode,
    /// The token is well formed but needs a codec, compressor or required
    /// extension this reader does not implement. Inspection still works.
    Unsupported,
    /// The source spectrum or writer options cannot be written as a token.
    Encode,
}

/// A spectrl error: a kind plus a human-readable message.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Error {
    kind: ErrorKind,
    message: String,
}

impl Error {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Error {
            kind,
            message: message.into(),
        }
    }

    pub fn decode(message: impl Into<String>) -> Self {
        Error::new(ErrorKind::Decode, message)
    }

    pub fn unsupported(message: impl Into<String>) -> Self {
        Error::new(ErrorKind::Unsupported, message)
    }

    pub fn encode(message: impl Into<String>) -> Self {
        Error::new(ErrorKind::Encode, message)
    }

    pub fn kind(&self) -> ErrorKind {
        self.kind
    }

    pub fn message(&self) -> &str {
        &self.message
    }

    /// The same message under a different kind (a writer reports its own
    /// validation failures as encode errors).
    pub fn with_kind(mut self, kind: ErrorKind) -> Self {
        self.kind = kind;
        self
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for Error {}

pub type Result<T> = std::result::Result<T, Error>;

/// Shorthand for an early decode error.
macro_rules! bail {
    ($($arg:tt)*) => {
        return Err($crate::error::Error::decode(format!($($arg)*)))
    };
}
pub(crate) use bail;
