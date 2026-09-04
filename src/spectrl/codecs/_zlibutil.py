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
    d = zlib.decompressobj()
    out = d.decompress(blob, 0 if max_bytes is None else max_bytes + 1)
    if max_bytes is not None and (len(out) > max_bytes or d.unconsumed_tail):
        raise ValueError(
            f"array blob decompresses beyond the {max_bytes}-byte bound implied by the declared array length"
        )
    if not d.eof:
        raise ValueError("truncated zlib stream")
    if d.unused_data:
        raise ValueError("trailing data after zlib stream")
    return out
