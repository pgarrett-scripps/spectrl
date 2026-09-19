"""Round-trippable JSON representation including v3 dtypes and context."""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np

from . import model


def _json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if dataclasses.is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, bytes):
        return {"$spectrl": "bytes", "hex": value.hex()}
    if isinstance(value, dict):
        if "$spectrl" in value or any(not isinstance(key, str) for key in value):
            return {"$spectrl": "map", "items": [[_json_value(k), _json_value(v)] for k, v in value.items()]}
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def spectrum_to_dict(spec):
    out = _json_value(spec)
    out["array_dtypes"] = {
        key: str(getattr(spec, key).dtype) for key in ("mz", "intensity", "charge") if getattr(spec, key) is not None
    }
    out["extra_array_dtypes"] = {key: str(arr.dtype) for key, arr in spec.extra_arrays.items()}
    out.pop("checksum", None)
    out.pop("format_version", None)
    return out


def _array(values, dtype):
    if dtype not in {"int32", "float32", "float64"}:
        raise ValueError(f"unsupported array dtype {dtype!r}")
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
        raise ValueError("invalid numeric array")
    if dtype == "int32" and (np.any(raw < -(2**31)) or np.any(raw >= 2**31) or np.any(raw != np.floor(raw))):
        raise ValueError("array cannot be represented as int32")
    with np.errstate(over="ignore"):
        arr = np.asarray(values, dtype=dtype)
    if not np.isfinite(arr).all():
        raise ValueError("array exceeds declared dtype")
    return arr


def _construct(cls, data):
    if not isinstance(data, dict):
        raise ValueError("expected a metadata object")
    list_classes = {
        "params": model.SpectrlCvParam,
        "user_params": model.SpectrlUserParam,
        "scans": model.SpectrlScan,
        "windows": model.SpectrlScanWindow,
        "precursors": model.SpectrlPrecursor,
        "products": model.SpectrlProduct,
        "selected_ions": model.SpectrlSelectedIon,
    }
    single_classes = {
        "isolation_window": model.SpectrlIsolationWindow,
        "activation": model.SpectrlActivation,
        "scan_combination": model.SpectrlCvParam,
    }
    result = dict(data)
    for key, typ in list_classes.items():
        if key in result:
            result[key] = [_construct(typ, v) for v in result[key]]
    for key, typ in single_classes.items():
        if result.get(key) is not None:
            result[key] = _construct(typ, result[key])
    return cls(**result)


def _from_json_value(value):
    if isinstance(value, list):
        return [_from_json_value(item) for item in value]
    if isinstance(value, dict):
        if value.get("$spectrl") == "bytes" and set(value) == {"$spectrl", "hex"}:
            return bytes.fromhex(value["hex"])
        if value.get("$spectrl") == "map" and set(value) == {"$spectrl", "items"}:
            return {_from_json_value(k): _from_json_value(v) for k, v in value["items"]}
        return {key: _from_json_value(item) for key, item in value.items()}
    return value


def spectrum_from_dict(data):
    if not isinstance(data, dict):
        raise ValueError("expected a spectrum JSON object")
    if "interp" in data or "interpretation" in data:
        raise ValueError("v3 does not accept identification fields")
    data = _from_json_value(data)
    data.pop("checksum", None)
    data.pop("format_version", None)
    core_types = data.pop("array_dtypes", {})
    extra_types = data.pop("extra_array_dtypes", {})
    extra = data.get("extra_arrays", {})
    if not isinstance(core_types, dict) or not isinstance(extra_types, dict) or not isinstance(extra, dict):
        raise ValueError("array dtype declarations and extra_arrays must be maps")
    if set(core_types) - {"mz", "intensity", "charge"} or set(extra_types) - set(extra):
        raise ValueError("array dtype contains an unknown array")
    for key in ("mz", "intensity", "charge"):
        if data.get(key) is not None:
            data[key] = _array(data[key], core_types.get(key, "float64"))
        elif key in core_types:
            raise ValueError("dtype declared for absent array")
    data["extra_arrays"] = {key: _array(values, extra_types.get(key, "float64")) for key, values in extra.items()}
    for field, cls in [("array_params", model.SpectrlCvParam), ("array_user_params", model.SpectrlUserParam)]:
        data[field] = {key: [_construct(cls, x) for x in values] for key, values in data.get(field, {}).items()}
    if "default_array_length" not in data:
        data["default_array_length"] = len(data["mz"]) if data.get("mz") is not None else 0
    return _construct(model.InlineSpectrum, data)
