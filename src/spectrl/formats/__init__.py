"""Convert one spectrum between a spectrl token and common spectrum files.

mzML is the interchange format: it carries everything a token does, and a
token written to mzML and read back is the same spectrum. MGF and MS2 are
convenience formats that hold a precursor and peaks, so writing to them drops
most of a token's context. Nothing is dropped silently: every writer returns a
ConversionResult listing what the target could not represent.

Reading a multi-spectrum file yields every spectrum, and the caller chooses.
Requiring a single-spectrum file would be the wrong trade -- ordinary runs hold
thousands -- so selection belongs to the caller, not to the file.
"""

from __future__ import annotations

from pathlib import Path

from ..model import DecodedSpectrum, InlineSpectrum
from ._mzml import write_mzml
from ._peaklist_formats import read_mgf, read_ms2, write_mgf, write_ms2
from ._report import ConversionResult

__all__ = [
    "ConversionResult",
    "FORMATS",
    "format_for_path",
    "read_file",
    "read_mgf",
    "read_ms2",
    "read_mzml",
    "write",
    "write_mgf",
    "write_ms2",
    "write_mzml",
]

FORMATS = ("mzml", "mgf", "ms2")

_SUFFIXES = {
    ".mzml": "mzml",
    ".mgf": "mgf",
    ".ms2": "ms2",
}


def format_for_path(path: str | Path) -> str:
    """The format a filename implies, ignoring a trailing .gz."""
    name = Path(path).name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    suffix = Path(name).suffix
    if suffix not in _SUFFIXES:
        known = ", ".join(sorted(_SUFFIXES))
        raise ValueError(f"cannot infer a spectrum format from {Path(path).name!r}; known suffixes: {known}")
    return _SUFFIXES[suffix]


def write(spectrum: DecodedSpectrum, format: str, **kwargs) -> ConversionResult:
    """Write one decoded spectrum in the named format."""
    writers = {"mzml": write_mzml, "mgf": write_mgf, "ms2": write_ms2}
    if format not in writers:
        raise ValueError(f"unknown output format {format!r}; expected one of {', '.join(FORMATS)}")
    return writers[format](spectrum, **kwargs)


def read_mzml(
    path: str | Path, *, index: int | None = None, spectrum_id: str | None = None, strict: bool = False
) -> list[InlineSpectrum]:
    """Read spectra from an mzML file, resolving run context.

    With no selector every spectrum is returned, which for an ordinary run is
    thousands, so callers that want one should pass `index` or `spectrum_id`
    and let the reader skip the rest.
    """
    from mzmlpy import Mzml  # noqa: PLC0415 - optional at import time

    from ..mzml import from_mzmlpy  # noqa: PLC0415

    with Mzml(str(path)) as run:
        if index is not None:
            return [from_mzmlpy(run.spectra[index], run=run, strict=strict)]
        if spectrum_id is not None:
            for spectrum in run.spectra:
                if spectrum.id == spectrum_id:
                    return [from_mzmlpy(spectrum, run=run, strict=strict)]
            raise KeyError(f"no spectrum with id {spectrum_id!r} in {path}")
        return [from_mzmlpy(spectrum, run=run, strict=strict) for spectrum in run.spectra]


def read_file(
    path: str | Path, *, index: int | None = None, spectrum_id: str | None = None, strict: bool = False
) -> list[InlineSpectrum]:
    """Read spectra from any supported file, choosing the reader by suffix."""
    format = format_for_path(path)
    if format == "mzml":
        return read_mzml(path, index=index, spectrum_id=spectrum_id, strict=strict)
    text = Path(path).read_text(encoding="utf-8")
    spectra = read_mgf(text) if format == "mgf" else read_ms2(text)
    if spectrum_id is not None:
        matched = [s for s in spectra if s.id == spectrum_id]
        if not matched:
            raise KeyError(f"no spectrum with id {spectrum_id!r} in {path}")
        return matched[:1]
    if index is not None:
        if not -len(spectra) <= index < len(spectra):
            raise IndexError(f"{path} holds {len(spectra)} spectra; index {index} is out of range")
        return [spectra[index]]
    return spectra
