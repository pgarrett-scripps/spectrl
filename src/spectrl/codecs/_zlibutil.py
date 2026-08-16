"""Bounded zlib decompression.

Tokens are decoded from untrusted URLs; an unbounded ``zlib.decompress`` lets a
few-hundred-KB token expand to hundreds of MB (a decompression bomb). Every
codec decodes through :func:`bounded_decompress`, with the bound derived from
the token's declared array length by the caller.
"""

from __future__ import annotations

import zlib


def bounded_decompress(blob: bytes, max_bytes: int | None = None) -> bytes:
    """Decompress ``blob``, raising ValueError if the output would exceed ``max_bytes``."""
    if max_bytes is None:
        return zlib.decompress(blob)
    d = zlib.decompressobj()
    out = d.decompress(blob, max_bytes)
    if d.unconsumed_tail:
        raise ValueError(
            f"array blob decompresses beyond the {max_bytes}-byte bound implied by the declared array length"
        )
    return out
