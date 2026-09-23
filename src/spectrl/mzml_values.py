"""Translate mzML user-parameter values into Spectrl's native scalar domain.

XML type annotations guide import only; they are never stored in Spectrl.
Unannotated values and nonnumeric XML types remain text, without guessing from
their spelling. Declared numeric values must fit Spectrl's numeric domain.
"""

from __future__ import annotations

import math
import re
from decimal import Decimal

from .model import SpectrlUserParam

_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_DECIMAL = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_REAL = re.compile(_DECIMAL + r"(?:[eE][+-]?[0-9]+)?\Z")
_DECIMAL_ONLY = re.compile(_DECIMAL + r"\Z")
_SAFE = 2**53 - 1
_INTEGER_BOUNDS = {
    "integer": (-_SAFE, _SAFE),
    "long": (-(2**63), 2**63 - 1),
    "int": (-(2**31), 2**31 - 1),
    "short": (-(2**15), 2**15 - 1),
    "byte": (-128, 127),
    "nonNegativeInteger": (0, _SAFE),
    "positiveInteger": (1, _SAFE),
    "nonPositiveInteger": (-_SAFE, 0),
    "negativeInteger": (-_SAFE, -1),
    "unsignedLong": (0, 2**64 - 1),
    "unsignedInt": (0, 2**32 - 1),
    "unsignedShort": (0, 2**16 - 1),
    "unsignedByte": (0, 255),
}


def user_param(element) -> SpectrlUserParam:
    """Import one XML userParam, consuming its optional numeric type hint."""
    value = element.get("value")
    declared = (element.get("type") or "").strip()
    prefix, separator, local = declared.partition(":")
    kind = local if separator and prefix in {"xsd", "xs"} else declared
    if value is not None and kind in {*_INTEGER_BOUNDS, "float", "double", "decimal"}:
        text = value.strip()
        try:
            if kind in _INTEGER_BOUNDS:
                if not _INTEGER.fullmatch(text):
                    raise ValueError("expected an integer")
                value = int(text)
                low, high = _INTEGER_BOUNDS[kind]
                if not max(low, -_SAFE) <= value <= min(high, _SAFE):
                    raise ValueError("integer outside supported range")
            else:
                pattern = _DECIMAL_ONLY if kind == "decimal" else _REAL
                if not pattern.fullmatch(text):
                    raise ValueError("expected a finite number")
                value = float(text)
                if not math.isfinite(value) or (value == 0 and Decimal(text) != 0):
                    raise ValueError("number outside supported range")
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"invalid mzML user parameter {element.get('name')!r} ({declared}): {exc}") from exc
    return SpectrlUserParam(
        name=element.get("name"),
        value=value,
        unit_accession=element.get("unitAccession") or None,
    )
