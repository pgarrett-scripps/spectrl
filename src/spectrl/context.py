"""Compact selected-spectrum context and namespaced extension contracts."""

from __future__ import annotations

import copy
import re

from .model import SpectrlCvParam, SpectrlUserParam

FIELDS = {
    "params": 0,
    "user_params": 1,
    "id": 2,
    "name": 3,
    "version": 4,
    "location": 5,
    "external_ids": 6,
    "spectrum_ref": 7,
    "instrument": 8,
    "components": 9,
    "kind": 10,
    "order": 11,
    "software": 12,
    "operation": 13,
    "revision": 14,
    "parameters": 15,
    "source_params": 16,
}
ALLOWED = {
    "source": {"params", "user_params", "id", "name", "location", "external_ids", "spectrum_ref"},
    "acquisition": {"instrument"},
    "instrument": {"params", "user_params", "id", "name", "components", "software"},
    "component": {"params", "user_params", "kind", "order"},
    "software": {"params", "user_params", "id", "name", "version"},
    "processing": {"params", "user_params", "software", "operation", "revision", "parameters", "source_params"},
}
EXTENSIONS = {}
_NAMESPACE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+$")


def _params(values, cls):
    if not isinstance(values, list):
        raise ValueError("parameters must be a list")
    return [cls(**x) if isinstance(x, dict) else x for x in values]


def encode_record(value, kind):
    from .header import _encode_param_map, _encode_user_params

    if not isinstance(value, dict) or set(value) - ALLOWED[kind]:
        raise ValueError(f"invalid {kind} record fields")
    out = {}
    for key, val in value.items():
        if val is None:
            continue
        if key in {"params", "source_params"}:
            val = _encode_param_map(_params(val, SpectrlCvParam))
        elif key == "user_params":
            val = _encode_user_params(_params(val, SpectrlUserParam))
        elif key in {"instrument", "software"}:
            val = encode_record(val, key)
        elif key == "components":
            if not isinstance(val, list):
                raise ValueError("components must be a list")
            val = [encode_record(x, "component") for x in val]
        elif key == "external_ids":
            if not isinstance(val, list) or not all(isinstance(x, str) and x for x in val):
                raise ValueError("external_ids must be a list of nonempty strings")
        elif key in {"order", "revision"}:
            if type(val) is not int or not (0 if key == "order" else 1) <= val <= 9007199254740991:
                raise ValueError(f"{key} must be a valid nonnegative order or positive revision")
        elif key == "parameters":
            if not isinstance(val, dict) or not all(isinstance(x, str) for x in val):
                raise ValueError("processing parameters must be a string-keyed map")
        elif not isinstance(val, str):
            raise ValueError(f"{key} must be a string")
        if key == "kind" and val not in {"source", "analyzer", "detector"}:
            raise ValueError("invalid instrument component kind")
        out[FIELDS[key]] = val
    return out


def decode_record(value, kind):
    from .header import _decode_param_map, _decode_user_params

    reverse = {v: k for k, v in FIELDS.items()}
    if not isinstance(value, dict) or any(type(k) is not int or k not in reverse for k in value):
        raise ValueError(f"invalid {kind} record")
    out = {}
    for raw_key, val in value.items():
        key = reverse[raw_key]
        if key in {"params", "source_params"}:
            val = _decode_param_map(val)
        elif key == "user_params":
            val = _decode_user_params(val)
        elif key in {"instrument", "software"}:
            val = decode_record(val, key)
        elif key == "components":
            if not isinstance(val, list):
                raise ValueError("components must be a list")
            val = [decode_record(x, "component") for x in val]
        out[key] = val
    encode_record(out, kind)
    return out


def register_extension(identifier, validator, *, revision=1):
    if not isinstance(identifier, str) or not _NAMESPACE.fullmatch(identifier):
        raise ValueError("extension identifier must be namespaced")
    if type(revision) is not int or revision < 1 or not callable(validator):
        raise ValueError("invalid extension registration")
    if (identifier, revision) in EXTENSIONS:
        raise ValueError("extension already registered")
    EXTENSIONS[identifier, revision] = validator


def validate_extensions(value, *, require_supported=True):
    if not isinstance(value, dict):
        raise ValueError("extensions must be a map")
    for identifier, record in value.items():
        if not isinstance(identifier, str) or not _NAMESPACE.fullmatch(identifier):
            raise ValueError("extension identifier must be namespaced")
        if not isinstance(record, dict) or set(record) != {"revision", "required", "data"}:
            raise ValueError("extension requires revision, required, and data")
        revision = record["revision"]
        if type(revision) is not int or not 1 <= revision <= 9007199254740991 or type(record["required"]) is not bool:
            raise ValueError("invalid extension revision or required flag")
        validator = EXTENSIONS.get((identifier, revision))
        if validator:
            validator(record["data"])
        elif require_supported and record["required"]:
            raise ValueError(f"unsupported required extension {identifier}@{revision}")


def check_array_mutation(spec):
    """Unknown extension dependencies cannot safely survive a permutation or selection."""
    if spec.extensions or any(spec.array_extensions.values()):
        raise ValueError("array mutation requires explicitly removing or updating extensions first")


def record_change(spec, operation, parameters):
    """Keep acquisition-derived summaries under an explicit source scope."""
    summary_terms = {"MS:1000285", "MS:1000504", "MS:1000505", "MS:1000527", "MS:1000528"}
    summaries = [p for p in spec.params if p.accession in summary_terms]
    event = {"operation": operation, "revision": 1, "parameters": parameters}
    if summaries:
        event["source_params"] = copy.deepcopy(summaries)
    return [p for p in spec.params if p.accession not in summary_terms], [*spec.processing, event]
