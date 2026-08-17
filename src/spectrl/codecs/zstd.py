"""PSI-MS Zstandard codecs, including byte shuffle and Numpress pipelines."""

from __future__ import annotations

import io

import numpy as np
import zstandard

from ..cv import TYPE_FLOAT64
from .numpress import (
    decode_numlin_raw,
    decode_numpic_raw,
    decode_numslof_raw,
    encode_numlin_raw,
    encode_numpic_raw,
    encode_numslof_raw,
)
from .raw import _np_dtype


def _compress(raw: bytes) -> bytes:
    return zstandard.ZstdCompressor(level=3).compress(raw)


def bounded_zstd_decompress(blob: bytes, max_bytes: int | None) -> bytes:
    if max_bytes is None:
        return zstandard.ZstdDecompressor().decompress(blob)
    with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(blob)) as reader:
        raw = reader.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError(f"zstd decompressed data exceeds the {max_bytes}-byte limit")
    return raw


def _raw_bytes(data: np.ndarray, type_tail: int) -> bytes:
    return np.asarray(data).astype(_np_dtype(type_tail)).tobytes()


def _decode_raw(raw: bytes, type_tail: int) -> np.ndarray:
    dtype = np.dtype(_np_dtype(type_tail))
    if len(raw) % dtype.itemsize != 0:
        raise ValueError(f"raw array blob length {len(raw)} is not a multiple of the {dtype.itemsize}-byte data type")
    return np.frombuffer(raw, dtype=dtype).copy()


def encode_zstd_raw(data: np.ndarray, type_tail: int = TYPE_FLOAT64) -> bytes:
    return _compress(_raw_bytes(data, type_tail))


def decode_zstd_raw(blob: bytes, type_tail: int = TYPE_FLOAT64, max_bytes: int | None = None) -> np.ndarray:
    return _decode_raw(bounded_zstd_decompress(blob, max_bytes), type_tail)


def encode_byte_shuffled_zstd(data: np.ndarray, type_tail: int = TYPE_FLOAT64) -> bytes:
    dtype = np.dtype(_np_dtype(type_tail))
    raw = np.frombuffer(_raw_bytes(data, type_tail), dtype=np.uint8).reshape(-1, dtype.itemsize)
    return _compress(raw.T.copy().tobytes())


def decode_byte_shuffled_zstd(blob: bytes, type_tail: int = TYPE_FLOAT64, max_bytes: int | None = None) -> np.ndarray:
    shuffled = bounded_zstd_decompress(blob, max_bytes)
    dtype = np.dtype(_np_dtype(type_tail))
    if len(shuffled) % dtype.itemsize != 0:
        raise ValueError(f"shuffled array blob length {len(shuffled)} is not a multiple of {dtype.itemsize}")
    n = len(shuffled) // dtype.itemsize
    raw = np.frombuffer(shuffled, dtype=np.uint8).reshape(dtype.itemsize, n).T.copy().tobytes()
    return _decode_raw(raw, type_tail)


def encode_numlin_zstd(data: np.ndarray, fp: float | None = None) -> bytes:
    return _compress(encode_numlin_raw(data, fp))


def decode_numlin_zstd(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    return decode_numlin_raw(bounded_zstd_decompress(blob, max_bytes))


def encode_numslof_zstd(data: np.ndarray, fp: float | None = None) -> bytes:
    return _compress(encode_numslof_raw(data, fp))


def decode_numslof_zstd(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    return decode_numslof_raw(bounded_zstd_decompress(blob, max_bytes))


def encode_numpic_zstd(data: np.ndarray) -> bytes:
    return _compress(encode_numpic_raw(data))


def decode_numpic_zstd(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    return decode_numpic_raw(bounded_zstd_decompress(blob, max_bytes))
