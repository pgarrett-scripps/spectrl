"""Peak array assembly, canonical form, and top_n helper."""

from __future__ import annotations

import dataclasses
import re

import numpy as np

from ._format import DEFAULT_INTENSITY_SCALE, DEFAULT_MZ_PPM, MAX_ARRAY_LENGTH
from .cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ARRAY_NON_STANDARD,
    TYPE_FLOAT32,
    TYPE_FLOAT64,
    TYPE_INT32,
    accession_tail,
    encode_unit,
)
from .model import ArrayEncoding, InlineSpectrum

# A dict key that looks like a CV accession (e.g. "MS:1000517") names a standard
# array by its accession; any other key is a non-standard array (MS:1000786).
_MS_ACCESSION_RE = re.compile(r"^MS:[0-9]{7}$")
_ANY_ACCESSION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$")
_CORE_ARRAY_ALIASES = {
    "MS:1000514": "mz",
    "MS:1000515": "intensity",
    "MS:1000516": "charge",
}
_RESERVED_EXTRA_NAMES = {"mz", "intensity", "charge"}


def _parse_encoding(value) -> ArrayEncoding:
    if value is None or value == "auto":
        return ArrayEncoding()
    if isinstance(value, ArrayEncoding):
        return value
    if isinstance(value, dict) and "encoding" in value:
        if set(value) != {"encoding"}:
            raise ValueError("only encoding is accepted in an array override")
        return ArrayEncoding(**value)
    return ArrayEncoding(encoding=value)


def _extra_key_to_array(key: str) -> tuple[int, str | None]:
    """Map an extra-array key to (array_tail, name). Accession keys → (tail, None)."""
    key = str(key)
    if not key:
        raise ValueError("non-standard array name must not be empty")
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
    if k.kind == "f" and k.itemsize == 4:
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
    if not np.array_equal(order, np.arange(len(order))):
        from .context import check_array_mutation

        check_array_mutation(spec)
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
        if arr.ndim != 1:
            raise ValueError(f"Array '{name}' must be one-dimensional")
        if arr.dtype.kind not in "fiu" or (arr.dtype.kind == "f" and arr.dtype.itemsize > 8):
            raise ValueError(f"Array '{name}' must have a supported real numeric dtype")
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
    mz_ppm: float = DEFAULT_MZ_PPM,
    int_fp: float = DEFAULT_INTENSITY_SCALE,
    array_encodings: dict[str, ArrayEncoding | str | int | dict] | None = None,
    allow_unsafe_lossy_custom: bool = False,
) -> tuple[list[bytes], list[dict]]:
    from .context import encode_record, validate_extensions
    from .header import _encode_param_map, _encode_user_params
    from .pipeline import (
        ENCODING_NAMES,
        ENCODINGS,
        descriptor,
        encode_pipeline,
        operation,
    )

    for key in spec.extra_arrays:
        _extra_key_to_array(key)
    settings = _normalise_encoding_keys(array_encodings or {})
    arrays = [(key, getattr(spec, key)) for key in ("mz", "intensity", "charge")]
    arrays += [(key, spec.extra_arrays[key]) for key in sorted(spec.extra_arrays)]
    present = {key for key, array in arrays if array is not None}
    if set(settings) - present:
        raise ValueError("array_encodings contains unknown array key")
    for field in ("array_names", "array_params", "array_user_params", "array_processing", "array_extensions"):
        if set(getattr(spec, field)) - present:
            raise ValueError(f"{field} contains an absent or noncanonical array key")
    for key, name in spec.array_names.items():
        if not isinstance(name, str) or not name:
            raise ValueError("array name must be a non-empty string")
        if key in spec.extra_arrays and _extra_key_to_array(key)[0] == ARRAY_NON_STANDARD and name != key:
            raise ValueError("a non-standard array name must match its extra_arrays key")
    representation = {
        1000519,
        1000521,
        1000522,
        1000523,
        1000576,
        1000574,
        *range(1002312, 1002315),
        *range(1002746, 1002749),
        *range(1003780, 1003786),
    }
    for key, values in spec.array_params.items():
        identity = {"mz": ARRAY_MZ, "intensity": ARRAY_INTENSITY, "charge": ARRAY_CHARGE}.get(key)
        if identity is None:
            identity = _extra_key_to_array(key)[0]
        if any(
            p.accession.startswith("MS:")
            and p.accession[3:].isdigit()
            and int(p.accession[3:]) in representation | {identity}
            for p in values
        ):
            raise ValueError("array scientific parameters conflict with representation declarations")
    blobs, descriptors = [], []
    for key, array in arrays:
        if array is None:
            continue
        tail, name = {"mz": (ARRAY_MZ, None), "intensity": (ARRAY_INTENSITY, None), "charge": (ARRAY_CHARGE, None)}.get(
            key
        ) or _extra_key_to_array(key)
        setting = _parse_encoding(settings.get(key))
        dtype = _type_tail_for_dtype(array.dtype)
        automatic = setting.encoding is None
        default_enc = 2 if key == "mz" else 1 if key == "intensity" else 0
        default_params = None
        if not lossless and key in {"mz", "intensity"} and array.dtype.kind == "f" and not _has_negative(array):
            from .codecs.quantized import intensity_parameters, ppm_parameters

            try:
                default_params = ppm_parameters(array, mz_ppm) if key == "mz" else intensity_parameters(array, int_fp)
                default_enc = 3
            except ValueError:
                pass
        enc = descriptor(
            setting.encoding if not automatic else [3, 1, default_params] if default_enc == 3 else default_enc,
            ENCODING_NAMES,
        )
        implementation, params = operation(ENCODINGS, enc)
        if not implementation.lossless:
            if lossless:
                raise ValueError("lossy encoding requested while lossless=True")
            if key not in {"mz", "intensity"} and not allow_unsafe_lossy_custom:
                raise ValueError(f"array {key!r} needs explicit permission for custom lossy encoding")
            dtype = TYPE_FLOAT64 if dtype not in implementation.types else dtype
        try:
            blob, fidelity = encode_pipeline(array, dtype, enc)
        except ValueError:
            if not automatic:
                raise
            dtype = _type_tail_for_dtype(array.dtype)
            enc = [2 if key == "mz" else 1 if key == "intensity" else 0, 1]
            blob, fidelity = encode_pipeline(array, dtype, enc)
        desc = {0: dtype, 1: tail, 2: enc, 7: fidelity}
        name = spec.array_names.get(key, name)
        if name is not None:
            desc[4] = name
        unit = spec.array_units.get(key) or spec.array_units.get(f"MS:{tail}")
        if unit:
            desc[6] = encode_unit(unit)
        if spec.array_params.get(key):
            desc[8] = _encode_param_map(spec.array_params[key])
        if spec.array_user_params.get(key):
            desc[9] = _encode_user_params(spec.array_user_params[key])
        if spec.array_processing.get(key):
            desc[10] = [encode_record(x, "processing") for x in spec.array_processing[key]]
        if spec.array_extensions.get(key):
            validate_extensions(spec.array_extensions[key], require_supported=False)
            desc[11] = spec.array_extensions[key]
        blobs.append(blob)
        descriptors.append(desc)
    return blobs, descriptors


def top_n(spec: InlineSpectrum, n: int) -> InlineSpectrum:
    """Return a new InlineSpectrum keeping only the n most intense peaks.

    Peaks are re-sorted m/z-ascending after selection; n == 0 yields an empty
    spectrum. This is explicit caller-driven trimming; encoding never trims
    silently.
    """
    _validate_arrays(spec)
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < 0:
        raise ValueError(f"top_n: n must be >= 0, got {n}")
    if spec.intensity is None or n >= len(spec.intensity):
        return spec
    from .context import check_array_mutation, record_change

    check_array_mutation(spec)
    params, processing = record_change(
        spec,
        "spectrl:peak-selection",
        {
            "method": "highest-intensity",
            "inputPeakCount": spec.default_array_length,
            "outputPeakCount": int(n),
        },
    )
    if n == 0:
        top_idx = np.array([], dtype=np.intp)
    else:
        indices = np.arange(len(spec.intensity), dtype=np.intp)
        # Full ordering makes ties deterministic: higher intensity first, then
        # lower m/z (or original position when m/z is absent), then index.
        secondary = spec.mz if spec.mz is not None else indices
        # Every supported int32 value is exact in float64; negate after widening
        # so INT32_MIN cannot overflow and rank ahead of positive intensities.
        ranked = np.lexsort((indices, secondary, -np.asarray(spec.intensity, dtype=np.float64)))
        top_idx = ranked[:n]
        top_idx = top_idx[np.lexsort((top_idx, secondary[top_idx]))]

    return dataclasses.replace(
        spec,
        default_array_length=n,
        params=params,
        processing=processing,
        mz=spec.mz[top_idx] if spec.mz is not None else None,
        intensity=spec.intensity[top_idx],
        charge=spec.charge[top_idx] if spec.charge is not None else None,
        extra_arrays={k: (v[top_idx] if len(v) == len(spec.intensity) else v) for k, v in spec.extra_arrays.items()},
    )
