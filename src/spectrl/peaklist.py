"""Strict two-column peak-list import and export, without optional dependencies."""

from __future__ import annotations

import csv
import io
import math
import re

from ._format import MAX_ARRAY_LENGTH
from .model import DecodedSpectrum, InlineSpectrum
from .peaks import _validate_arrays

_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_HEADERS = {("mz", "intensity"), ("m/z", "intensity")}


def parse_peak_list(text: str, *, delimiter: str | None = None) -> InlineSpectrum:
    """Parse whitespace, CSV or TSV with optional m/z,intensity header.

    Blank lines and lines starting with # are ignored. Extra columns, missing
    values, non-finite numbers and negative m/z are rejected with line numbers.
    Input order and negative intensities are preserved.
    """
    if delimiter not in (None, ",", "\t", " "):
        raise ValueError("delimiter must be comma, tab, space, or None")
    mz, intensity = [], []
    first = True
    chosen = delimiter
    for number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if chosen is None:
            chosen = "," if "," in line else "\t" if "\t" in line else " "
        try:
            row = line.split() if chosen == " " else next(csv.reader([line], delimiter=chosen, strict=True))
        except csv.Error as exc:
            raise ValueError(f"line {number}: invalid delimited row") from exc
        row = [value.strip() for value in row]
        if first and tuple(value.lower() for value in row) in _HEADERS:
            first = False
            continue
        first = False
        if len(row) != 2 or any(not _NUMBER.fullmatch(value) for value in row):
            raise ValueError(f"line {number}: expected exactly two numeric columns: m/z and intensity")
        x, y = map(float, row)
        if not math.isfinite(x) or not math.isfinite(y) or x < 0:
            raise ValueError(f"line {number}: require finite values and non-negative m/z")
        mz.append(x)
        intensity.append(y)
        if len(mz) > MAX_ARRAY_LENGTH:
            raise ValueError(f"peak list exceeds the {MAX_ARRAY_LENGTH} peak limit")
    if not mz:
        raise ValueError("peak list contains no peaks")
    return InlineSpectrum(len(mz), mz=mz, intensity=intensity)


def format_peak_list(spec: InlineSpectrum | DecodedSpectrum, *, delimiter: str = "\t") -> str:
    """Export m/z and intensity only. Metadata and other arrays are not included."""
    if delimiter not in (",", "\t", " "):
        raise ValueError("delimiter must be comma, tab, or space")
    _validate_arrays(spec)
    if spec.mz is None or spec.intensity is None:
        raise ValueError("peak-list export requires m/z and intensity arrays")
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    writer.writerow(["mz", "intensity"])
    writer.writerows((repr(float(x)), repr(float(y))) for x, y in zip(spec.mz, spec.intensity, strict=True))
    return out.getvalue()
