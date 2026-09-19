"""Whole-document compression presets with bounded decompression."""

from __future__ import annotations

import importlib.util
import zlib

from .codecs._zlibutil import bounded_decompress

NAMES = {"raw": "r", "zlib": "z", "brotli": "b", "r": "r", "z": "z", "b": "b"}


def _brotli():
    try:
        import brotli
    except ImportError as exc:
        raise ValueError("Brotli support is unavailable. Install spectrl[brotli].") from exc
    return brotli


def compress_payload(raw: bytes, compression: str, cap: int) -> tuple[str, bytes]:
    if len(raw) > cap:
        raise ValueError(f"CBOR payload exceeds {cap} bytes")
    if compression == "auto":
        modes = ["z", "r"]
        if importlib.util.find_spec("brotli") is not None:
            modes.append("b")
        candidates = [(mode, _pack(raw, mode)) for mode in modes]
        candidates = [item for item in candidates if len(item[1]) <= cap]
        return min(candidates, key=lambda item: len(item[1]))
    try:
        mode = NAMES[compression]
    except (KeyError, TypeError) as exc:
        raise ValueError("payload compression must be raw, zlib, brotli, or auto") from exc
    packed = _pack(raw, mode)
    if len(packed) > cap:
        raise ValueError(f"compressed payload exceeds {cap} bytes")
    return mode, packed


def _pack(raw, mode):
    if mode == "r":
        return raw
    if mode == "z":
        return zlib.compress(raw, 6)
    return _brotli().compress(raw, quality=5)


def decompress_payload(packed: bytes, mode: str, cap: int) -> bytes:
    if mode == "r":
        return packed
    if mode == "z":
        return bounded_decompress(packed, cap)
    if mode != "b":
        raise ValueError(f"unsupported payload mode: {mode!r}")
    decoder = _brotli().Decompressor()
    chunks = []
    count = 0
    data = packed
    while True:
        chunk = decoder.process(data, output_buffer_limit=min(65536, cap - count + 1))
        count += len(chunk)
        if count > cap:
            raise ValueError(f"brotli output exceeds the {cap}-byte limit")
        chunks.append(chunk)
        if decoder.is_finished():
            return b"".join(chunks)
        if not chunk:
            raise ValueError("truncated brotli payload")
        data = b""
