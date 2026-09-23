"""Base64url encoding/decoding (no padding) and the spectrl magic/version.

A spectrl.v3 token is ``spectrl.v3.<mode>.<payload>.<checksum>``: a
raw or zlib-compressed CBOR document with a
required trailing CRC-32 checksum. See cbor_format.
"""

import base64
import re

from ._format import FORMAT_VERSION as FORMAT_VERSION
from ._format import MAGIC as MAGIC
from .errors import SpectrlDecodeError

_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]*$")
_B64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
# Bits of the final character that fall outside the decoded bytes. A canonical
# encoding leaves them zero, so exactly one spelling exists per payload.
_B64URL_TAIL_MASK = {2: 0b001111, 3: 0b000011}


def b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    """Decode a canonical unpadded base64url string to bytes.

    Strict: rejects characters outside the base64url alphabet, ``=`` padding,
    impossible lengths, and non-zero unused trailing bits. Each payload
    therefore has exactly one valid spelling, so a token string is a canonical
    encoding of its payload rather than one of several aliases.
    """
    if "=" in s:
        raise SpectrlDecodeError("invalid base64url payload: must be unpadded")
    if not _B64URL_RE.match(s):
        raise SpectrlDecodeError("invalid base64url payload: non-alphabet characters")
    remainder = len(s) % 4
    if remainder == 1:
        raise SpectrlDecodeError("invalid base64url payload: impossible length")
    if remainder and _B64URL_ALPHABET.index(s[-1]) & _B64URL_TAIL_MASK[remainder]:
        raise SpectrlDecodeError("invalid base64url payload: non-zero trailing bits")
    return base64.urlsafe_b64decode(s + "=" * ((-len(s)) % 4))
