"""Supported little-endian numeric types."""

from ..cv import TYPE_FLOAT32, TYPE_FLOAT64, TYPE_INT32

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
