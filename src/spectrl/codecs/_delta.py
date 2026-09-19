"""Bit-exact unsigned modular differences and byte shuffle for v3 encoding 2."""

from __future__ import annotations

import numpy as np


def _validate(raw: bytes, item_size: int) -> None:
    if item_size not in (4, 8):
        raise ValueError("delta shuffle requires 4-byte or 8-byte words")
    if len(raw) % item_size:
        raise ValueError("delta shuffle data length must be a multiple of the word size")


def delta_shuffle(raw: bytes, item_size: int) -> bytes:
    """Difference little-endian unsigned words modulo their width, then shuffle."""
    _validate(raw, item_size)
    words = np.frombuffer(raw, dtype=f"<u{item_size}").copy()
    words[1:] = words[1:] - words[:-1]
    return words.view(np.uint8).reshape(-1, item_size).T.copy().tobytes()


def delta_unshuffle(data: bytes, item_size: int) -> bytes:
    """Invert byte shuffling and modular differences without floating arithmetic."""
    _validate(data, item_size)
    raw = np.frombuffer(data, dtype=np.uint8).reshape(item_size, -1).T.copy().tobytes()
    words = np.frombuffer(raw, dtype=f"<u{item_size}")
    return np.cumsum(words, dtype=words.dtype).astype(f"<u{item_size}").tobytes()
