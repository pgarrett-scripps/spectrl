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
        extra_arrays=data.get("extra_arrays", {}),
        array_units=data.get("array_units", {}),
        user_params=[_user(v) for v in data.get("user_params", [])],
    )
