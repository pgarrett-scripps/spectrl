"""Encoding quality reports and explicit sharing budgets."""

from __future__ import annotations

import dataclasses

import numpy as np

from .cbor_format import decode_cbor, encode_cbor
from .introspection import inspect_token
from .model import InlineSpectrum
from .peaks import _validate_arrays, canonical_sort, top_n


def _user_param_count(spec: InlineSpectrum) -> int:
    return len(spec.user_params) + sum(len(scan.user_params) for scan in spec.scans)


def encoding_report(spec: InlineSpectrum, **options) -> dict:
    """Encode once and measure errors against the sorted source, without warnings.

    Accepts encode options except max_len. Relative errors exclude zero reference
    values, reported separately. An unavailable or unrepresentable metric is None.
    No peak selection is performed. The returned token is the one measured.
    """
    token = encode_cbor(spec, **options)
    decoded = decode_cbor(token)
    source = canonical_sort(spec)
    arrays = []
    descriptors = inspect_token(token)
    keys = [key for key in ("mz", "intensity", "charge") if getattr(source, key) is not None]
    keys += sorted(source.extra_arrays)
    for key, desc in zip(keys, descriptors, strict=True):
        original = getattr(source, key) if key in {"mz", "intensity", "charge"} else source.extra_arrays[key]
        restored = getattr(decoded, key) if key in {"mz", "intensity", "charge"} else decoded.extra_arrays[key]
        a = np.asarray(original, dtype=np.longdouble)
        b = np.asarray(restored, dtype=np.longdouble)
        delta = np.abs(b - a)
        nonzero = a != 0
        relative = delta[nonzero] / np.abs(a[nonzero])

        def finite(value):
            return float(value) if abs(value) <= np.finfo(np.float64).max else None

        item = {
            "key": key,
            **desc,
            "source_dtype": str(original.dtype),
            "decoded_dtype": str(restored.dtype),
            "raw_bytes": original.nbytes,
            "exact": original.dtype == restored.dtype and original.tobytes() == restored.tobytes(),
            "max_absolute_error": finite(delta.max()) if len(delta) else 0.0,
            "max_relative_error": finite(relative.max()) if len(relative) else None,
            "mean_relative_error": finite(relative.mean()) if len(relative) else None,
            "zero_reference_values": int(np.sum(~nonzero)),
            "changed_zero_values": int(np.sum((~nonzero) & (delta != 0))),
        }
        if key == "mz":
            item["max_error_ppm"] = finite(relative.max() * 1e6) if len(relative) else None
            item["mean_error_ppm"] = finite(relative.mean() * 1e6) if len(relative) else None
        arrays.append(item)
    return {
        "token": token,
        "token_bytes": len(token),
        "peak_count": source.default_array_length,
        "raw_array_bytes": sum(item["raw_bytes"] for item in arrays),
        "arrays": arrays,
        "omitted_user_params": _user_param_count(source) if options.get("drop_user_params") else 0,
        "all_arrays_exact": all(item["exact"] for item in arrays),
    }


def fit_to_budget(
    spec: InlineSpectrum,
    max_bytes: int,
    *,
    base_url: str | None = None,
    allow_peak_trimming: bool = False,
    min_peaks: int = 1,
    **options,
) -> dict:
    """Return a measured candidate within a token or fragment-URL byte budget.

    Peak removal requires allow_peak_trimming=True. User-param removal requires
    drop_user_params=True in options. Binary refinement returns the largest
    fitting candidate visited, not a guarantee of the global maximum because
    compressed size need not be monotonic. The source is never mutated.
    """
    from . import to_fragment

    _validate_arrays(spec)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    if isinstance(min_peaks, bool) or not isinstance(min_peaks, int) or min_peaks < 0:
        raise ValueError("min_peaks must be a non-negative integer")
    original_n = spec.default_array_length
    minimum = min(min_peaks, original_n)

    def candidate(n):
        selected = spec if n == original_n else top_n(spec, n)
        token = encode_cbor(selected, **options)
        carrier = token if base_url is None else to_fragment(token, base_url)
        return selected, token, carrier, len(carrier.encode("utf-8"))

    best = candidate(original_n)
    if best[3] > max_bytes:
        if not allow_peak_trimming:
            raise OverflowError(
                "spectrum exceeds the share budget, enable peak trimming explicitly or change the budget"
            )
        if spec.intensity is None:
            raise ValueError("peak trimming requires an intensity array")
        best = candidate(minimum)
        if best[3] > max_bytes:
            raise OverflowError("metadata and minimum peaks exceed the share budget")
        low, high = minimum, original_n
        while high - low > 1:
            mid = (low + high) // 2
            trial = candidate(mid)
            if trial[3] <= max_bytes:
                best, low = trial, mid
            else:
                high = mid
    selected, token, carrier, size = best
    if options.get("drop_user_params"):
        selected = dataclasses.replace(
            selected, user_params=[], scans=[dataclasses.replace(scan, user_params=[]) for scan in selected.scans]
        )
    return {
        "spectrum": selected,
        "token": token,
        "carrier": carrier,
        "carrier_bytes": size,
        "max_bytes": max_bytes,
        "original_peaks": original_n,
        "kept_peaks": selected.default_array_length,
        "dropped_peaks": original_n - selected.default_array_length,
        "omitted_user_params": _user_param_count(spec) if options.get("drop_user_params") else 0,
    }
