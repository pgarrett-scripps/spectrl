"""Pure-Python MS-Numpress codecs (linear, slof, pic).

A dependency-free fallback for environments where the C-extension
``pynumpress`` cannot be installed, most importantly Pyodide / the browser,
where spectrl runs inside spxtacular's WebAssembly Python. Ported faithfully
from the reference C++ implementation (Teleman et al., ms-numpress) via the
TypeScript port in ``js/src/numpress.ts``, so the byte output is identical to
``pynumpress``: tokens produced by either backend round-trip and share the same
token checksum.

Only the three raw MS-Numpress transforms live here; the ``+ zlib`` wrapping and
the safe fixed-point clamping stay in :mod:`spectrl.codecs.numpress`, which
selects this backend when ``pynumpress`` is unavailable.
"""

from __future__ import annotations

import math
import struct

import numpy as np

_U32 = 0xFFFFFFFF
_MASK = 0xF0000000


# ---------------------------------------------------------------------------
# variable-length unsigned-32 int as half-bytes (nibbles)
# ---------------------------------------------------------------------------


def _encode_int(x: int, half: bytearray, offset: int) -> int:
    """Write the nibble encoding of unsigned-32 ``x`` into ``half`` at ``offset``.

    Returns the number of nibbles written. Mirrors ``encodeInt`` in the C++/TS
    reference exactly (including the leading/trailing sentinel nibbles).
    """
    x &= _U32
    init = x & _MASK

    if init == 0:
        lead = 8
        for i in range(8):
            if (x & (_MASK >> (4 * i))) != 0:
                lead = i
                break
        half[offset] = lead
        for i in range(lead, 8):
            half[offset + 1 + i - lead] = (x >> (4 * (i - lead))) & 0xF
        return 1 + 8 - lead
    elif init == _MASK:
        lead = 7
        for i in range(8):
            m = _MASK >> (4 * i)
            if (x & m) != m:
                lead = i
                break
        half[offset] = lead + 8
        for i in range(lead, 8):
            half[offset + 1 + i - lead] = (x >> (4 * (i - lead))) & 0xF
        return 1 + 8 - lead
    else:
        half[offset] = 0
        for i in range(8):
            half[offset + 1 + i] = (x >> (4 * i)) & 0xF
        return 9


class _IntState:
    __slots__ = ("di", "half")

    def __init__(self) -> None:
        self.di = 0
        self.half = 0


def _decode_int(data: bytes, st: _IntState) -> int:
    """Decode one nibble-packed unsigned-32 int from ``data``, advancing ``st``."""
    if st.half == 0:
        head = data[st.di] >> 4
    else:
        head = data[st.di] & 0xF
        st.di += 1
    st.half = 1 - st.half

    res = 0
    if head <= 8:
        n = head
    else:
        n = head - 8
        for i in range(n):
            res = (res | (_MASK >> (4 * i))) & _U32

    if n == 8:
        return res & _U32

    for i in range(n, 8):
        if st.half == 0:
            hb = data[st.di] >> 4
        else:
            hb = data[st.di] & 0xF
            st.di += 1
        res = (res | (hb << ((i - n) * 4))) & _U32
        st.half = 1 - st.half
    return res & _U32


# ---------------------------------------------------------------------------
# fixed point + little-endian 32-bit helpers
# ---------------------------------------------------------------------------


def _write_u32le(out: bytearray, v: int) -> None:
    v &= _U32
    out.append(v & 0xFF)
    out.append((v >> 8) & 0xFF)
    out.append((v >> 16) & 0xFF)
    out.append((v >> 24) & 0xFF)


def _read_u32le(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8) | (data[off + 2] << 16) | (data[off + 3] << 24)


def _flush_half_bytes(out: bytearray, half: bytearray, hbc: int) -> int:
    """Emit complete bytes from the ``half`` nibble buffer; return the new count.

    Shared by ``encode_linear`` and ``encode_pic``; a leftover odd nibble is
    carried forward into ``half[0]``.
    """
    hbi = 1
    while hbi < hbc:
        out.append(((half[hbi - 1] << 4) | (half[hbi] & 0xF)) & 0xFF)
        hbi += 2
    if hbc % 2 != 0:
        half[0] = half[hbc - 1]
        return 1
    return 0


# ---------------------------------------------------------------------------
# linear
# ---------------------------------------------------------------------------


def encode_linear(data: np.ndarray, fixed_point: float) -> np.ndarray:
    out = bytearray(struct.pack(">d", fixed_point))
    n = len(data)
    if n == 0:
        return np.frombuffer(bytes(out), dtype=np.uint8)

    i1 = math.floor(float(data[0]) * fixed_point + 0.5)
    _write_u32le(out, i1)
    if n == 1:
        return np.frombuffer(bytes(out), dtype=np.uint8)

    i2 = math.floor(float(data[1]) * fixed_point + 0.5)
    _write_u32le(out, i2)

    half = bytearray(16)
    hbc = 0
    for i in range(2, n):
        i0 = i1
        i1 = i2
        i2 = math.floor(float(data[i]) * fixed_point + 0.5)
        extrapol = i1 + (i1 - i0)
        diff = (i2 - extrapol) & _U32
        hbc += _encode_int(diff, half, hbc)
        hbc = _flush_half_bytes(out, half, hbc)
    if hbc == 1:
        out.append((half[0] << 4) & 0xFF)

    return np.frombuffer(bytes(out), dtype=np.uint8)


def decode_linear(data: np.ndarray) -> np.ndarray:
    buf = data.tobytes() if isinstance(data, np.ndarray) else bytes(data)
    size = len(buf)
    if size == 8:
        return np.empty(0, dtype=np.float64)
    if size < 8:
        raise ValueError("numpress linear: truncated (no fixed point)")

    fixed_point = struct.unpack(">d", buf[:8])[0]
    if size < 12:
        raise ValueError("numpress linear: truncated (no first value)")

    i1 = _read_u32le(buf, 8)
    result = [i1 / fixed_point]
    if size == 12:
        return np.array(result, dtype=np.float64)
    if size < 16:
        raise ValueError("numpress linear: truncated (no second value)")

    i2 = _read_u32le(buf, 12)
    result.append(i2 / fixed_point)

    st = _IntState()
    st.di = 16
    while st.di < size:
        if st.di == size - 1 and st.half == 1 and (buf[st.di] & 0xF) == 0:
            break
        i0 = i1
        i1 = i2
        raw = _decode_int(buf, st)
        diff = raw - 0x100000000 if raw >= 0x80000000 else raw
        extrapol = i1 + (i1 - i0)
        y = extrapol + diff
        result.append(y / fixed_point)
        i2 = y
    return np.array(result, dtype=np.float64)


# ---------------------------------------------------------------------------
# slof (short logged float)
# ---------------------------------------------------------------------------


def encode_slof(data: np.ndarray, fixed_point: float) -> np.ndarray:
    out = bytearray(struct.pack(">d", fixed_point))
    for v in data:
        x = math.floor(math.log(float(v) + 1) * fixed_point + 0.5) & 0xFFFF
        out.append(x & 0xFF)
        out.append((x >> 8) & 0xFF)
    return np.frombuffer(bytes(out), dtype=np.uint8)


def decode_slof(data: np.ndarray) -> np.ndarray:
    buf = data.tobytes() if isinstance(data, np.ndarray) else bytes(data)
    if len(buf) < 8 or len(buf) % 2:
        raise ValueError("numpress slof: truncated (no fixed point)")
    fixed_point = struct.unpack(">d", buf[:8])[0]
    result = []
    i = 8
    while i + 1 < len(buf):
        x = (buf[i] | (buf[i + 1] << 8)) & 0xFFFF
        result.append(math.exp(x / fixed_point) - 1)
        i += 2
    return np.array(result, dtype=np.float64)


# ---------------------------------------------------------------------------
# pic (positive integer count)
# ---------------------------------------------------------------------------


def encode_pic(data: np.ndarray) -> np.ndarray:
    out = bytearray()
    half = bytearray(16)
    hbc = 0
    for v in data:
        x = math.floor(float(v) + 0.5) & _U32
        hbc += _encode_int(x, half, hbc)
        hbc = _flush_half_bytes(out, half, hbc)
    if hbc == 1:
        out.append((half[0] << 4) & 0xFF)
    return np.frombuffer(bytes(out), dtype=np.uint8)


def decode_pic(data: np.ndarray) -> np.ndarray:
    buf = data.tobytes() if isinstance(data, np.ndarray) else bytes(data)
    size = len(buf)
    result = []
    st = _IntState()
    while st.di < size:
        if st.di == size - 1 and st.half == 1 and (buf[st.di] & 0xF) == 0:
            break
        result.append(_decode_int(buf, st))
    return np.array(result, dtype=np.float64)
