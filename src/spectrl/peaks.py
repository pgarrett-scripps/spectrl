"""Peak array assembly, canonical form, and top_n helper."""

from __future__ import annotations

import dataclasses
import re

import numpy as np
from numpy.typing import NDArray

from ._format import (
    EXTRA_NUMLIN_ARRAY_TAILS,
    EXTRA_NUMPIC_ARRAY_TAILS,
    EXTRA_NUMSLOF_ARRAY_TAILS,
    ION_MOBILITY_ARRAY_TAILS,
    MAX_ARRAY_LENGTH,
    MAX_SAFE_INTEGER,
)
from .codecs import get_codec
from .codecs.numpress import DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, _safe_slof_fp
from .cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ARRAY_NON_STANDARD,
    COMP_BYTE_SHUFFLED_ZSTD,
    COMP_NUMLIN_ZLIB,
    COMP_NUMLIN_ZSTD,
    COMP_NUMPIC_ZLIB,
    COMP_NUMPIC_ZSTD,
    COMP_NUMSLOF_ZLIB,
    COMP_NUMSLOF_ZSTD,
    COMP_ZLIB,
    COMP_ZSTD,
    TYPE_FLOAT32,
    TYPE_FLOAT64,
    TYPE_INT32,
    accession_tail,
    encode_unit,
)
from .header import DESC_ARRAY, DESC_COMP, DESC_FP, DESC_NAME, DESC_TYPE, DESC_UNIT
from .model import ArrayEncoding, InlineSpectrum

# A dict key that looks like a CV accession (e.g. "MS:1000517") names a standard
# array by its accession; any other key is a non-standard array (MS:1000786).
_MS_ACCESSION_RE = re.compile(r"^MS:\d{7}$")
_ANY_ACCESSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$")
_CORE_ARRAY_ALIASES = {
    "MS:1000514": "mz",
    "MS:1000515": "intensity",
    "MS:1000516": "charge",
}
_RESERVED_EXTRA_NAMES = {"mz", "intensity", "charge"}

_CODEC_NAMES = {
    "zlib": COMP_ZLIB,
    "zstd": COMP_ZSTD,
    "byte-shuffled-zstd": COMP_BYTE_SHUFFLED_ZSTD,
    "numlin-zlib": COMP_NUMLIN_ZLIB,
    "numlin-zstd": COMP_NUMLIN_ZSTD,
    "numslof-zlib": COMP_NUMSLOF_ZLIB,
    "numslof-zstd": COMP_NUMSLOF_ZSTD,
    "numpic-zlib": COMP_NUMPIC_ZLIB,
    "numpic-zstd": COMP_NUMPIC_ZSTD,
}
_LOSSY_CODECS = {
    COMP_NUMLIN_ZLIB,
    COMP_NUMLIN_ZSTD,
    COMP_NUMSLOF_ZLIB,
    COMP_NUMSLOF_ZSTD,
    COMP_NUMPIC_ZLIB,
    COMP_NUMPIC_ZSTD,
}
_LINEAR_EXTRA_ARRAYS = set(EXTRA_NUMLIN_ARRAY_TAILS) | set(ION_MOBILITY_ARRAY_TAILS)
_SLOF_EXTRA_ARRAYS = set(EXTRA_NUMSLOF_ARRAY_TAILS)
_PIC_EXTRA_ARRAYS = set(EXTRA_NUMPIC_ARRAY_TAILS)


def _parse_encoding(value: ArrayEncoding | str | int | dict | None) -> ArrayEncoding:
    if value is None:
        return ArrayEncoding()
    if isinstance(value, ArrayEncoding):
        return value
    if isinstance(value, (str, int)):
        return ArrayEncoding(codec=value)
    if isinstance(value, dict):
        unknown = set(value) - {"codec", "fixed_point"}
        if unknown:
            raise ValueError(f"unknown array encoding option(s): {', '.join(sorted(unknown))}")
        return ArrayEncoding(codec=value.get("codec", "auto"), fixed_point=value.get("fixed_point"))
    raise TypeError(f"invalid array encoding {value!r}")


def _codec_tail(codec: str | int) -> int | None:
    if codec == "auto":
        return None
    if isinstance(codec, int):
        return codec
    if _MS_ACCESSION_RE.fullmatch(codec):
        return accession_tail(codec)
    try:
        return _CODEC_NAMES[codec]
    except KeyError:
        raise ValueError(f"unknown array codec {codec!r}") from None


def _default_extra_codec(array_tail: int, arr: np.ndarray, lossless: bool) -> tuple[int, float | None, int]:
    type_tail = _type_tail_for_dtype(arr.dtype)
    if lossless:
        return COMP_ZLIB, None, type_tail
    if array_tail in _LINEAR_EXTRA_ARRAYS and not _has_negative(arr):
        return COMP_NUMLIN_ZLIB, DEFAULT_NUMLIN_FP, TYPE_FLOAT64
    if array_tail in _SLOF_EXTRA_ARRAYS and not _has_negative(arr):
        return COMP_NUMSLOF_ZLIB, _safe_slof_fp(np.asarray(arr, dtype=np.float64), DEFAULT_NUMSLOF_FP), TYPE_FLOAT64
    if array_tail in _PIC_EXTRA_ARRAYS and not _has_negative(arr):
        return COMP_NUMPIC_ZLIB, None, TYPE_FLOAT64
    return COMP_ZLIB, None, type_tail


def _extra_key_to_array(key: str) -> tuple[int, str | None]:
    """Map an extra-array key to (array_tail, name). Accession keys → (tail, None)."""
    key = str(key)
    if key in _CORE_ARRAY_ALIASES:
        raise ValueError(f"core array accession {key} must use the dedicated {_CORE_ARRAY_ALIASES[key]!r} field")
    if key == "MS:1000786":
        raise ValueError("MS:1000786 is represented by a free-text extra-array name, not used as the key itself")
    if key in _RESERVED_EXTRA_NAMES:
        raise ValueError(f"non-standard array name {key!r} is reserved for a core array")
    if _MS_ACCESSION_RE.fullmatch(key):
        return accession_tail(key), None
    if _ANY_ACCESSION_RE.fullmatch(key):
        raise ValueError(f"standard binary-array accessions must be seven-digit PSI-MS accessions, got {key!r}")
    return ARRAY_NON_STANDARD, key


def _normalise_encoding_keys(
    encodings: dict[str, ArrayEncoding | str | int | dict],
) -> dict[str, ArrayEncoding | str | int | dict]:
    normalised: dict[str, ArrayEncoding | str | int | dict] = {}
    original: dict[str, str] = {}
    for raw_key, value in encodings.items():
        key = str(raw_key)
        canonical = _CORE_ARRAY_ALIASES.get(key, key)
        if canonical in normalised:
            raise ValueError(
                f"array_encodings contains conflicting aliases {original[canonical]!r} and {key!r} for {canonical!r}"
            )
        normalised[canonical] = value
        original[canonical] = key
    return normalised


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
    arrays = [
        ("mz", spec.mz),
        ("intensity", spec.intensity),
        ("charge", spec.charge),
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
    valid_unit_keys = {"mz", "intensity", "charge", *spec.extra_arrays}
    seen_unit_keys: dict[str, str] = {}
    for raw_key, unit in spec.array_units.items():
        key = _CORE_ARRAY_ALIASES.get(str(raw_key), str(raw_key))
        if key not in valid_unit_keys:
            raise ValueError(f"array_units contains unknown array key {raw_key!r}")
        if key in seen_unit_keys:
            raise ValueError(f"array_units contains conflicting aliases {seen_unit_keys[key]!r} and {raw_key!r}")
        seen_unit_keys[key] = str(raw_key)
        if not _ANY_ACCESSION_RE.fullmatch(unit):
            raise ValueError(f"invalid unit accession for array {key!r}: {unit!r}")
        try:
            encode_unit(unit)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid unit accession for array {key!r}: {unit!r}") from exc


def build_array_blobs(
    spec: InlineSpectrum,
    lossless: bool,
    mz_fp: float = DEFAULT_NUMLIN_FP,
    int_fp: float = DEFAULT_NUMSLOF_FP,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
) -> tuple[list[bytes], list[dict]]:
    """Encode all peak arrays and return (blobs, descriptors).

    Returns a list of raw byte blobs and matching array descriptor dicts (without 'seg').
    The caller assigns seg indices.
    """
    blobs: list[bytes] = []
    descriptors: list[dict] = []
    encodings = _normalise_encoding_keys(array_encodings or {})

    valid_keys = {"mz", "intensity", "charge", *(str(key) for key in spec.extra_arrays)}
    unknown_keys = set(encodings) - valid_keys
    if unknown_keys:
        raise ValueError(f"array_encodings contains unknown array key(s): {', '.join(sorted(unknown_keys))}")

    def resolve(
        key: str,
        array: NDArray,
        default_comp: int,
        default_fp_value: float | None,
        default_type: int = TYPE_FLOAT64,
    ) -> tuple[int, float | None, int]:
        setting = _parse_encoding(encodings.get(key))
        comp = _codec_tail(setting.codec)
        if comp is None:
            return default_comp, default_fp_value, default_type
        if lossless and comp in _LOSSY_CODECS:
            raise ValueError(f"array '{key}' requests lossy codec {setting.codec!r} while lossless=True")
        fp_codecs = {COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD}
        if comp not in fp_codecs and setting.fixed_point is not None:
            raise ValueError(f"array '{key}' sets fixed_point for a codec that takes no fixed point")
        if setting.fixed_point is not None and (
            isinstance(setting.fixed_point, (bool, np.bool_))
            or not isinstance(setting.fixed_point, (int, np.integer))
            or setting.fixed_point <= 0
            or setting.fixed_point > MAX_SAFE_INTEGER
        ):
            raise ValueError(f"array '{key}' fixed_point must be a positive whole number")
        linear = {COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD}
        slof = {COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD}
        pic = {COMP_NUMPIC_ZLIB, COMP_NUMPIC_ZSTD}
        lossy_allowed = (
            linear
            if key == "mz"
            else linear | slof
            if key == "intensity"
            else pic
            if key == "charge"
            else linear
            if key.startswith("MS:") and accession_tail(key) in _LINEAR_EXTRA_ARRAYS
            else linear | slof
            if key.startswith("MS:") and accession_tail(key) in _SLOF_EXTRA_ARRAYS
            else pic
            if key.startswith("MS:") and accession_tail(key) in _PIC_EXTRA_ARRAYS
            else set()
        )
        semantic_unknown = key not in {"mz", "intensity", "charge"} and (
            not key.startswith("MS:")
            or accession_tail(key) not in (_LINEAR_EXTRA_ARRAYS | _SLOF_EXTRA_ARRAYS | _PIC_EXTRA_ARRAYS)
        )
        if comp in _LOSSY_CODECS and comp not in lossy_allowed and not (semantic_unknown and allow_unsafe_lossy_custom):
            raise ValueError(f"array '{key}' is not compatible with codec {setting.codec!r}")
        if comp in _LOSSY_CODECS and _has_negative(array):
            raise ValueError(f"array '{key}' contains negative values and cannot use codec {setting.codec!r}")
        if comp in pic and np.any(np.asarray(array) != np.rint(np.asarray(array))):
            raise ValueError(f"array '{key}' contains fractional values and cannot use a positive-integer codec")
        type_tail = TYPE_FLOAT64 if comp in _LOSSY_CODECS else default_type
        fp = setting.fixed_point
        if comp in {COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD}:
            fp = mz_fp if fp is None else fp
        elif comp in {COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD}:
            desired = int_fp if fp is None else fp
            safe = _safe_slof_fp(np.asarray(array, dtype=np.float64), desired)
            if setting.fixed_point is not None and safe != desired:
                raise ValueError(f"array '{key}' fixed_point {desired} would overflow the SLOF representation")
            fp = safe
        else:
            fp = None
        return comp, fp, type_tail

    def add_array(
        array: NDArray,
        array_tail: int,
        comp_tail: int,
        fp: int | None,
        type_tail: int = TYPE_FLOAT64,
        name: str | None = None,
        unit: str | None = None,
    ) -> None:
        codec = get_codec(comp_tail)
        blob = codec.encode(array, fp, type_tail)
        blobs.append(blob)
        desc: dict = {
            DESC_TYPE: type_tail,
            DESC_ARRAY: array_tail,
            DESC_COMP: comp_tail,
        }
        if fp is not None:
            desc[DESC_FP] = int(fp)
        if name is not None:
            desc[DESC_NAME] = name
        if unit is not None:
            desc[DESC_UNIT] = encode_unit(unit)
        descriptors.append(desc)

    if spec.mz is not None:
        comp = COMP_ZLIB if lossless else COMP_NUMLIN_ZLIB
        fp = None if lossless else mz_fp
        comp, fp, type_tail = resolve("mz", spec.mz, comp, fp)
        add_array(
            spec.mz,
            ARRAY_MZ,
            comp,
            fp,
            type_tail,
            unit=spec.array_units.get("mz") or spec.array_units.get("MS:1000514"),
        )

    if spec.intensity is not None:
        # The slof codec computes log(v + 1) and cannot represent negative values
        # (baseline-subtracted data may contain them), so fall back to lossless
        # zlib when the array contains any negative value.
        use_zlib = lossless or _has_negative(spec.intensity)
        comp = COMP_ZLIB if use_zlib else COMP_NUMSLOF_ZLIB
        # Clamp the slof fixed point here so the descriptor records the fp the
        # blob actually uses (large intensities force a smaller fp).
        fp = None if use_zlib else _safe_slof_fp(np.asarray(spec.intensity, dtype=np.float64), int_fp)
        comp, fp, type_tail = resolve("intensity", spec.intensity, comp, fp)
        add_array(
            spec.intensity,
            ARRAY_INTENSITY,
            comp,
            fp,
            type_tail,
            unit=spec.array_units.get("intensity") or spec.array_units.get("MS:1000515"),
        )

    if spec.charge is not None:
        # The PIC integer codec only handles non-negative values; charge arrays
        # may carry negative sentinels (e.g. unassigned/singleton), so fall back
        # to lossless zlib when the array contains any negative value.
        comp = COMP_ZLIB if (lossless or _has_negative(spec.charge)) else COMP_NUMPIC_ZLIB
        comp, fp, type_tail = resolve("charge", spec.charge, comp, None)
        add_array(
            spec.charge,
            ARRAY_CHARGE,
            comp,
            fp,
            type_tail,
            unit=spec.array_units.get("charge") or spec.array_units.get("MS:1000516"),
        )

    # Known PSI-MS auxiliary arrays receive conservative semantic defaults.
    # Unknown and non-standard arrays remain lossless. Explicit settings win.
    for key in sorted(spec.extra_arrays):
        arr = np.asarray(spec.extra_arrays[key])
        array_tail, name = _extra_key_to_array(key)
        default_comp, fp, type_tail = _default_extra_codec(array_tail, arr, lossless)
        comp, fp, type_tail = resolve(key, arr, default_comp, fp, type_tail)
        add_array(arr, array_tail, comp, fp, type_tail=type_tail, name=name, unit=spec.array_units.get(key))

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
        extra_arrays={k: (v[top_idx] if len(v) == len(spec.intensity) else v) for k, v in spec.extra_arrays.items()},
    )
