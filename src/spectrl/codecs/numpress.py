"""MS-Numpress + zlib codecs.

Wraps the three MS-Numpress transforms (linear, slof, pic) with zlib. The raw
transforms come from one of two interchangeable, byte-identical backends:

- **pynumpress**: the C extension; preferred when importable.
- **pure Python** (:mod:`spectrl.codecs._numpress_py`): a dependency-free
  fallback used when ``pynumpress`` is not installed. This is what lets spectrl
  run in Pyodide / the browser (and anywhere a C toolchain is unavailable),
  where ``pynumpress`` has no wheel.

Backend selection is lazy: ``import spectrl`` never imports ``pynumpress``, so a
missing C extension is only a problem if you actually encode/decode a lossy
token, and even then the pure-Python path takes over transparently. Set
``SPECTRL_NUMPRESS_BACKEND=python`` (or ``pynumpress``) to pin one explicitly,
mainly for tests that assert the two backends agree.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from typing import Protocol

import numpy as np

from .._format import DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP
from ._zlibutil import bounded_decompress

# Fixed points are whole numbers: the two defaults are, and a clamped slof fp is
# floored to one. Rounding a clamped fp DOWN is the safe direction -- the clamp
# exists to keep log(max + 1) * fp under the uint16 ceiling, and a smaller fp
# only pushes that product further below it -- and it lets the descriptor carry
# fp as a CBOR integer (3 or 5 bytes) instead of a float64 (9).
# SLOF fp must satisfy: log(max_intensity + 1) * fp <= 65535 (uint16 max)
# Use 3600 which handles intensities up to ~8e7; clip to a safe value if larger.
_SLOF_UINT16_MAX = 65535.0


def _safe_slof_fp(data: np.ndarray, desired_fp: float) -> int:
    """Return a slof fp that won't overflow uint16 given the array's max value.

    Always a whole number, floored so the clamp can only get safer.
    """
    max_val = float(np.max(data)) if len(data) > 0 else 1.0
    max_val = max(max_val, 1.0)
    max_fp = _SLOF_UINT16_MAX / (math.log(max_val + 1) + 1e-9)
    return max(1, int(min(desired_fp, max_fp)))


# ---------------------------------------------------------------------------
# Backend selection (lazy: never imports pynumpress at module import time)
# ---------------------------------------------------------------------------


class _NumpressBackend(Protocol):
    name: str

    def encode_linear(self, data: np.ndarray, fp: float) -> np.ndarray: ...
    def decode_linear(self, raw: np.ndarray) -> np.ndarray: ...
    def encode_slof(self, data: np.ndarray, fp: float) -> np.ndarray: ...
    def decode_slof(self, raw: np.ndarray) -> np.ndarray: ...
    def encode_pic(self, data: np.ndarray) -> np.ndarray: ...
    def decode_pic(self, raw: np.ndarray) -> np.ndarray: ...


class _PynumpressBackend:
    name = "pynumpress"

    def __init__(self, mod) -> None:
        self._m = mod

    def encode_linear(self, data: np.ndarray, fp: float) -> np.ndarray:
        return np.asarray(self._m.encode_linear(data.astype(np.float64), fp), dtype=np.uint8)

    def decode_linear(self, raw: np.ndarray) -> np.ndarray:
        n = len(raw)
        # pynumpress 0.0.9 cannot decode a single-value linear blob (12 bytes: 8-byte
        # fixed point + one 4-byte int), though encode_linear emits exactly that. The
        # MS-Numpress reference decodes it (dataSize == 12 → one value); do so directly
        # to keep single-peak spectra round-trippable and cross-impl compatible.
        if 12 <= n < 16:
            buf = raw.tobytes()
            fixed_point = struct.unpack(">d", buf[:8])[0]
            first = int.from_bytes(buf[8:12], "little", signed=False)
            return np.array([first / fixed_point], dtype=np.float64)
        return np.array(self._m.decode_linear(raw), dtype=np.float64)

    def encode_slof(self, data: np.ndarray, fp: float) -> np.ndarray:
        return np.asarray(self._m.encode_slof(data.astype(np.float64), fp), dtype=np.uint8)

    def decode_slof(self, raw: np.ndarray) -> np.ndarray:
        return np.array(self._m.decode_slof(raw), dtype=np.float64)

    def encode_pic(self, data: np.ndarray) -> np.ndarray:
        return np.asarray(self._m.encode_pic(data.astype(np.float64)), dtype=np.uint8)

    def decode_pic(self, raw: np.ndarray) -> np.ndarray:
        return np.array(self._m.decode_pic(raw), dtype=np.float64)


class _PurePythonBackend:
    name = "python"

    def __init__(self) -> None:
        from . import _numpress_py as m

        self._m = m

    def encode_linear(self, data: np.ndarray, fp: float) -> np.ndarray:
        return self._m.encode_linear(data.astype(np.float64), fp)

    def decode_linear(self, raw: np.ndarray) -> np.ndarray:
        return self._m.decode_linear(raw)

    def encode_slof(self, data: np.ndarray, fp: float) -> np.ndarray:
        return self._m.encode_slof(data.astype(np.float64), fp)

    def decode_slof(self, raw: np.ndarray) -> np.ndarray:
        return self._m.decode_slof(raw)

    def encode_pic(self, data: np.ndarray) -> np.ndarray:
        return self._m.encode_pic(data.astype(np.float64))

    def decode_pic(self, raw: np.ndarray) -> np.ndarray:
        return self._m.decode_pic(raw)


_BACKEND: _NumpressBackend | None = None


def _resolve_backend() -> _NumpressBackend:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND

    choice = os.environ.get("SPECTRL_NUMPRESS_BACKEND", "auto").strip().lower()
    if choice in ("python", "pure", "purepython"):
        _BACKEND = _PurePythonBackend()
    elif choice in ("pynumpress", "c"):
        import pynumpress  # explicit request: let ImportError surface

        _BACKEND = _PynumpressBackend(pynumpress)
    else:  # "auto": prefer the C extension, fall back to pure Python
        try:
            import pynumpress

            _BACKEND = _PynumpressBackend(pynumpress)
        except ImportError:
            _BACKEND = _PurePythonBackend()
    return _BACKEND


def active_backend() -> str:
    """Return the name of the resolved numpress backend (``"pynumpress"`` or ``"python"``)."""
    return _resolve_backend().name


# ---------------------------------------------------------------------------
# Public codecs (raw transform via the selected backend, then zlib)
# ---------------------------------------------------------------------------


def _reject_negatives(data: np.ndarray, codec: str) -> np.ndarray:
    """Raise a catchable ValueError on negative input.

    The slof transform computes log(v + 1), which breaks for negatives, and the
    linear transform's rounding differs between the C and pure-Python backends
    for negatives (truncation vs floor), so byte-identity would be lost.
    Callers that may hold negative values fall back to a lossless codec.
    """
    arr = np.asarray(data, dtype=np.float64)
    if arr.size and float(arr.min()) < 0:
        raise ValueError(
            f"MS-Numpress {codec} codec cannot encode negative values; "
            "use a lossless codec for arrays that may contain negatives."
        )
    return arr


def encode_numlin_zlib(data: np.ndarray, fp: float | None = None) -> bytes:
    """Encode array with MS-Numpress linear prediction then zlib."""
    arr = _reject_negatives(data, "linear")
    fp = fp if fp is not None else DEFAULT_NUMLIN_FP
    encoded = _resolve_backend().encode_linear(arr, fp)
    return zlib.compress(encoded.tobytes())


def decode_numlin_zlib(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    """Decode MS-Numpress linear + zlib blob back to float64 array."""
    decompressed = bounded_decompress(blob, max_bytes)
    return _resolve_backend().decode_linear(np.frombuffer(decompressed, dtype=np.uint8))


def encode_numslof_zlib(data: np.ndarray, fp: float | None = None) -> bytes:
    """Encode array with MS-Numpress short logged float then zlib."""
    arr = _reject_negatives(data, "slof")
    desired = fp if fp is not None else DEFAULT_NUMSLOF_FP
    safe_fp = _safe_slof_fp(arr, desired)
    encoded = _resolve_backend().encode_slof(arr, safe_fp)
    return zlib.compress(encoded.tobytes())


def decode_numslof_zlib(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    """Decode MS-Numpress slof + zlib blob back to float64 array."""
    decompressed = bounded_decompress(blob, max_bytes)
    return _resolve_backend().decode_slof(np.frombuffer(decompressed, dtype=np.uint8))


def encode_numpic_zlib(data: np.ndarray, fp: float | None = None) -> bytes:
    """Encode array with MS-Numpress positive integer then zlib.

    MS-Numpress PIC represents only non-negative integers. pynumpress aborts the
    whole process (an uncatchable native C++ throw) on negative input, so reject
    negatives here with a catchable ``ValueError`` instead; callers that may hold
    negative values (e.g. a charge array with sentinels) should fall back to a
    lossless codec.
    """
    arr = _reject_negatives(data, "PIC")
    encoded = _resolve_backend().encode_pic(arr)
    return zlib.compress(encoded.tobytes())


def decode_numpic_zlib(blob: bytes, max_bytes: int | None = None) -> np.ndarray:
    """Decode MS-Numpress pic + zlib blob back to float64 array."""
    decompressed = bounded_decompress(blob, max_bytes)
    return _resolve_backend().decode_pic(np.frombuffer(decompressed, dtype=np.uint8))
