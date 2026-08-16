"""Base64url encoding/decoding (no padding) and the spectrl magic/version.

A spectrl2 token is ``spectrl2.<base64url(cbor_document)>[.<hash>]``: a single
CBOR document (header + array blobs embedded as byte strings) with an optional
trailing integrity hash; see cbor_format.
"""

import base64
import re

from ._format import FORMAT_VERSION as FORMAT_VERSION
from ._format import MAGIC as MAGIC
from .errors import SpectrlDecodeError

_B64URL_RE = re.compile(r"^[A-Za-z0-9_-]*={0,2}$")


def b64url_encode(data: bytes) -> str:
    """Encode bytes to base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(s: str) -> bytes:
    """Decode a base64url string (with or without padding) to bytes.

    Strict: rejects characters outside the base64url alphabet and impossible
    lengths, instead of silently discarding them.
    """
    if not _B64URL_RE.match(s):
        raise SpectrlDecodeError("invalid base64url payload: non-alphabet characters")
    unpadded = s.rstrip("=")
    if len(unpadded) % 4 == 1:
        raise SpectrlDecodeError("invalid base64url payload: impossible length")
    pad = (-len(unpadded)) % 4
    return base64.urlsafe_b64decode(unpadded + "=" * pad)
