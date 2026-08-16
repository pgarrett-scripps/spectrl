"""Peak array assembly, canonical form, and top_n helper."""

from __future__ import annotations

import dataclasses
import re

import numpy as np
from numpy.typing import NDArray

from ._format import MAX_ARRAY_LENGTH
from .codecs import get_codec
from .codecs.numpress import DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, _safe_slof_fp
from .cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ARRAY_NON_STANDARD,
    COMP_NUMLIN_ZLIB,
    COMP_NUMPIC_ZLIB,
    COMP_NUMSLOF_ZLIB,
    COMP_ZLIB,
    TYPE_FLOAT32,
    TYPE_FLOAT64,
    TYPE_INT32,
    accession_tail,
)
from .header import DESC_ARRAY, DESC_COMP, DESC_FP, DESC_NAME, DESC_TYPE
from .model import InlineSpectrum

# A dict key that looks like a CV accession (e.g. "MS:1000517") names a standard
# array by its accession; any other key is a non-standard array (MS:1000786).
_ACCESSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:\d+$")


def _extra_key_to_array(key: str) -> tuple[int, str | None]:
    """Map an extra-array key to (array_tail, name). Accession keys → (tail, None)."""
    if _ACCESSION_RE.match(key):
        return accession_tail(key), None
    return ARRAY_NON_STANDARD, key


def _type_tail_for_dtype(dtype: np.dtype) -> int:
    """Pick the binary data-type tail to preserve an array's dtype (default float64).

    Integer dtypes wider than int32 (int64, uint32, uint64) are rejected rather
    than silently downcast to float64, which would lose precision above 2**53.
    """
    k = np.dtype(dtype)
    if k == np.float32:
        return TYPE_FLOAT32
    if (k.kind == "i" and k.itemsize <= 4) or (k.kind == "u" and k.itemsize <= 2):
        return TYPE_INT32
    if k.kind in ("i", "u"):
        raise ValueError(
            f"extra array dtype {k} cannot be preserved (wire types are int32/float32/float64); "
            "convert explicitly to int32 or float64 first."
        )
    return TYPE_FLOAT64


def canonical_sort(spec: InlineSpectrum) -> InlineSpectrum:
    """Return a copy of spec with peaks sorted m/z-ascending.

    If mz is None, returns spec unchanged.
    """
    if spec.mz is None or len(spec.mz) == 0:
        return spec
    order = np.argsort(spec.mz, kind="stable")
    return dataclasses.replace(
        spec,
        mz=spec.mz[order],
        intensity=spec.intensity[order] if spec.intensity is not None else None,
        charge=spec.charge[order] if spec.charge is not None else None,
        ion_mobility=spec.ion_mobility[order] if spec.ion_mobility is not None else None,
        extra_arrays={k: (v[order] if len(v) == len(order) else v) for k, v in spec.extra_arrays.items()},
    )


def _has_negative(arr) -> bool:
    a = np.asarray(arr)
    return a.size > 0 and float(a.min()) < 0


def _validate_arrays(spec: InlineSpectrum) -> None:
    """Raise ValueError on NaN/Inf, negative m/z, or array-length inconsistencies."""
    if isinstance(spec.default_array_length, (bool, np.bool_)) or not isinstance(
        spec.default_array_length, (int, np.integer)
    ):
        raise ValueError("default_array_length must be a non-negative integer")
    n = int(spec.default_array_length)
    if n < 0:
        raise ValueError("default_array_length must be a non-negative integer")
    if n > MAX_ARRAY_LENGTH:
        raise ValueError(f"default_array_length exceeds the {MAX_ARRAY_LENGTH} peak limit")
    if (spec.ion_mobility is None) != (spec.ion_mobility_type is None):
        raise ValueError("ion_mobility and ion_mobility_type must be provided together")
    arrays = [
        ("mz", spec.mz),
        ("intensity", spec.intensity),
        ("charge", spec.charge),
        ("ion_mobility", spec.ion_mobility),
        *spec.extra_arrays.items(),
    ]
    for name, arr in arrays:
        if arr is None:
            continue
        arr = np.asarray(arr)
        if len(arr) != n:
            raise ValueError(
                f"Array '{name}' has {len(arr)} values, but default_array_length is {n}; "
                "all peak arrays must have the same length."
            )
        # Only float arrays can hold NaN/Inf; integer extra arrays are always finite.
        if arr.dtype.kind == "f" and (np.any(np.isnan(arr)) or np.any(np.isinf(arr))):
            raise ValueError(f"Array '{name}' contains NaN or Inf values, which are not allowed in canonical form.")
    if spec.mz is not None and _has_negative(spec.mz):
        raise ValueError("Array 'mz' contains negative values; m/z must be non-negative.")


def build_array_blobs(
    spec: InlineSpectrum,
    lossless: bool,
    mz_fp: float = DEFAULT_NUMLIN_FP,
    int_fp: float = DEFAULT_NUMSLOF_FP,
) -> tuple[list[bytes], list[dict]]:
    """Encode all peak arrays and return (blobs, descriptors).

    Returns a list of raw byte blobs and matching array descriptor dicts (without 'seg').
    The caller assigns seg indices.
    """
    blobs: list[bytes] = []
    descriptors: list[dict] = []

    # A codec's canonical default fp, omitted from the descriptor when it is the
    # one in use: absent means "the default for this codec" ([§7.1] of the spec).
    # The fp is also carried inside the numpress stream itself, so this costs no
    # information -- it only removes a value that was constant in nearly every
    # token (the slof clamp fires only for very high intensities).
    default_fp = {COMP_NUMLIN_ZLIB: DEFAULT_NUMLIN_FP, COMP_NUMSLOF_ZLIB: DEFAULT_NUMSLOF_FP}

    def add_array(
        array: NDArray,
        array_tail: int,
        comp_tail: int,
        fp: int | None,
        type_tail: int = TYPE_FLOAT64,
        name: str | None = None,
    ) -> None:
        codec = get_codec(comp_tail)
        blob = codec.encode(array, fp, type_tail)
        blobs.append(blob)
        desc: dict = {
            DESC_TYPE: type_tail,
            DESC_ARRAY: array_tail,
            DESC_COMP: comp_tail,
        }
        if fp is not None and not lossless and fp != default_fp.get(comp_tail):
            desc[DESC_FP] = int(fp)
        if name is not None:
            desc[DESC_NAME] = name
        descriptors.append(desc)

    if spec.mz is not None:
        comp = COMP_ZLIB if lossless else COMP_NUMLIN_ZLIB
        fp = None if lossless else mz_fp
        add_array(spec.mz, ARRAY_MZ, comp, fp)

    if spec.intensity is not None:
        # The slof codec computes log(v + 1) and cannot represent negative values
        # (baseline-subtracted data may contain them), so fall back to lossless
        # zlib when the array contains any negative value.
        use_zlib = lossless or _has_negative(spec.intensity)
        comp = COMP_ZLIB if use_zlib else COMP_NUMSLOF_ZLIB
        # Clamp the slof fixed point here so the descriptor records the fp the
        # blob actually uses (large intensities force a smaller fp).
        fp = None if use_zlib else _safe_slof_fp(np.asarray(spec.intensity, dtype=np.float64), int_fp)
        add_array(spec.intensity, ARRAY_INTENSITY, comp, fp)

    if spec.charge is not None:
        # The PIC integer codec only handles non-negative values; charge arrays
        # may carry negative sentinels (e.g. unassigned/singleton), so fall back
        # to lossless zlib when the array contains any negative value.
        comp = COMP_ZLIB if (lossless or _has_negative(spec.charge)) else COMP_NUMPIC_ZLIB
        add_array(spec.charge, ARRAY_CHARGE, comp, None)

    if spec.ion_mobility is not None and spec.ion_mobility_type is not None:
        # The linear codec's rounding differs between backends for negative
        # values, so fall back to lossless zlib to keep byte-identity.
        use_zlib = lossless or _has_negative(spec.ion_mobility)
        im_array_tail = accession_tail(spec.ion_mobility_type)
        comp = COMP_ZLIB if use_zlib else COMP_NUMLIN_ZLIB
        fp = None if use_zlib else mz_fp
        add_array(spec.ion_mobility, im_array_tail, comp, fp)

    # Extra arrays: always raw + zlib (lossless), dtype preserved. Emitted in
    # sorted key order so the token (and its content hash) is deterministic.
    for key in sorted(spec.extra_arrays):
        arr = np.asarray(spec.extra_arrays[key])
        array_tail, name = _extra_key_to_array(key)
        add_array(arr, array_tail, COMP_ZLIB, None, type_tail=_type_tail_for_dtype(arr.dtype), name=name)

    return blobs, descriptors


def top_n(spec: InlineSpectrum, n: int) -> InlineSpectrum:
    """Return a new InlineSpectrum keeping only the n most intense peaks.

    Peaks are re-sorted m/z-ascending after selection; n == 0 yields an empty
    spectrum. This is explicit caller-driven trimming; encoding never trims
    silently.
    """
    if n < 0:
        raise ValueError(f"top_n: n must be >= 0, got {n}")
    if spec.intensity is None or n >= len(spec.intensity):
        return spec
    if n == 0:
        top_idx = np.array([], dtype=np.intp)
    else:
        indices = np.arange(len(spec.intensity), dtype=np.intp)
        # Full ordering makes ties deterministic: higher intensity first, then
        # lower m/z (or original position when m/z is absent), then index.
        secondary = spec.mz if spec.mz is not None else indices
        ranked = np.lexsort((indices, secondary, -np.asarray(spec.intensity)))
        top_idx = ranked[:n]
        top_idx = top_idx[np.lexsort((top_idx, secondary[top_idx]))]

    return dataclasses.replace(
        spec,
        default_array_length=n,
        mz=spec.mz[top_idx] if spec.mz is not None else None,
        intensity=spec.intensity[top_idx],
        charge=spec.charge[top_idx] if spec.charge is not None else None,
        ion_mobility=spec.ion_mobility[top_idx] if spec.ion_mobility is not None else None,
        extra_arrays={k: (v[top_idx] if len(v) == len(spec.intensity) else v) for k, v in spec.extra_arrays.items()},
    )
