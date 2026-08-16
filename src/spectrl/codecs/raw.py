"""Lossless little-endian + zlib codec, data-type aware.

Standard peak arrays (m/z, intensity, charge, ion mobility) are always float64.
Extra arrays may declare float32 or int32 to preserve their mzML data type; the
declared type is carried in the array descriptor (`type`) and drives encode/decode.
"""

import zlib

import numpy as np

from ..cv import TYPE_FLOAT32, TYPE_FLOAT64, TYPE_INT32
from ._zlibutil import bounded_decompress

# Binary data-type tail → little-endian numpy dtype string.
_TYPE_TO_NP: dict[int, str] = {
    TYPE_FLOAT64: "<f8",
    TYPE_FLOAT32: "<f4",
    TYPE_INT32: "<i4",
}


def _np_dtype(type_tail: int) -> str:
    """Return the little-endian numpy dtype for a binary data-type tail (default float64)."""
    try:
        return _TYPE_TO_NP[type_tail]
    except KeyError:
        raise ValueError(f"unsupported binary data type tail {type_tail}") from None


def encode_zlib_raw(data: np.ndarray, type_tail: int = TYPE_FLOAT64) -> bytes:
    """Encode array as raw little-endian bytes of the declared type, then zlib."""
    raw = data.astype(_np_dtype(type_tail)).tobytes()
    return zlib.compress(raw)


def decode_zlib_raw(blob: bytes, type_tail: int = TYPE_FLOAT64, max_bytes: int | None = None) -> np.ndarray:
    """Decode zlib-compressed little-endian bytes back to an array of the declared type."""
    raw = bounded_decompress(blob, max_bytes)
    dtype = np.dtype(_np_dtype(type_tail))
    if len(raw) % dtype.itemsize != 0:
        raise ValueError(f"raw array blob length {len(raw)} is not a multiple of the {dtype.itemsize}-byte data type")
    return np.frombuffer(raw, dtype=dtype).copy()
