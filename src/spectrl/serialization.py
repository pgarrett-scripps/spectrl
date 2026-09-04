"""Round-trippable JSON-shaped spectrum serialization."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from .model import (
    DecodedSpectrum,
    InlineSpectrum,
    SpectrlActivation,
    SpectrlCvParam,
    SpectrlIsolationWindow,
    SpectrlPrecursor,
    SpectrlProduct,
    SpectrlScan,
    SpectrlScanWindow,
    SpectrlSelectedIon,
    SpectrlUserParam,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if dataclasses.is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def spectrum_to_dict(spec: InlineSpectrum | DecodedSpectrum) -> dict[str, Any]:
    """Convert a spectrum to the canonical CLI JSON representation."""
    out = _json_value(spec)
    out["extra_array_dtypes"] = {key: str(arr.dtype) for key, arr in spec.extra_arrays.items()}
    out.pop("checksum", None)
    out.pop("format_version", None)
    return out


def _cv(d: dict) -> SpectrlCvParam:
    return SpectrlCvParam(**d)


def _user(d: dict) -> SpectrlUserParam:
    return SpectrlUserParam(**d)


def _scan(d: dict) -> SpectrlScan:
    return SpectrlScan(
        params=[_cv(v) for v in d.get("params", [])],
        windows=[SpectrlScanWindow(params=[_cv(v) for v in w.get("params", [])]) for w in d.get("windows", [])],
        user_params=[_user(v) for v in d.get("user_params", [])],
    )


def _precursor(d: dict) -> SpectrlPrecursor:
    iw = d.get("isolation_window")
    act = d.get("activation")
    return SpectrlPrecursor(
        isolation_window=SpectrlIsolationWindow(params=[_cv(v) for v in iw.get("params", [])]) if iw else None,
        selected_ions=[
            SpectrlSelectedIon(params=[_cv(v) for v in si.get("params", [])]) for si in d.get("selected_ions", [])
        ],
        activation=SpectrlActivation(params=[_cv(v) for v in act.get("params", [])]) if act else None,
    )


def spectrum_from_dict(data: dict[str, Any]) -> InlineSpectrum:
    """Build an InlineSpectrum from canonical CLI JSON."""
    if not isinstance(data, dict):
        raise ValueError("expected a spectrum JSON object")
    if not isinstance(data.get("extra_arrays", {}), dict):
        raise ValueError("extra_arrays must be an object")
    extra = {}
    dtypes = data.get("extra_array_dtypes", {})
    if not isinstance(dtypes, dict):
        raise ValueError("extra_array_dtypes must be an object")
    if set(dtypes) - set(data.get("extra_arrays", {})):
        raise ValueError("extra_array_dtypes contains an unknown array")
    for key, values in data.get("extra_arrays", {}).items():
        dtype = dtypes.get(key, "float64")
        if dtype not in {"int32", "float32", "float64"}:
            raise ValueError(f"unsupported extra array dtype {dtype!r}")
        raw = np.asarray(values)
        if raw.ndim != 1 or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
            raise ValueError(f"invalid numeric array {key!r}")
        if dtype == "int32" and (np.any(raw < -(2**31)) or np.any(raw > 2**31 - 1) or np.any(raw != np.floor(raw))):
            raise ValueError(f"array {key!r} cannot be represented as int32")
        with np.errstate(over="ignore"):
            extra[key] = np.asarray(values, dtype=dtype)
        if not np.isfinite(extra[key]).all():
            raise ValueError(f"array {key!r} exceeds {dtype}")
    mz = data.get("mz")
    n = data.get("default_array_length", len(mz) if mz is not None else 0)
    combo = data.get("scan_combination")
    return InlineSpectrum(
        default_array_length=n,
        mz=mz,
        intensity=data.get("intensity"),
        charge=data.get("charge"),
        id=data.get("id"),
        params=[_cv(v) for v in data.get("params", [])],
        scans=[_scan(v) for v in data.get("scans", [])],
        scan_combination=_cv(combo) if combo else None,
        precursors=[_precursor(v) for v in data.get("precursors", [])],
        products=[
            SpectrlProduct(
                isolation_window=SpectrlIsolationWindow(
                    params=[_cv(v) for v in p["isolation_window"].get("params", [])]
                )
                if p.get("isolation_window")
                else None
            )
            for p in data.get("products", [])
        ],
        interp=data.get("interp"),
        extra_arrays=extra,
        array_units=data.get("array_units", {}),
        user_params=[_user(v) for v in data.get("user_params", [])],
    )
