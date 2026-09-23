"""MGF and MS2: peak lists with a small precursor header.

Both formats describe one fragmentation spectrum. They carry a precursor m/z,
usually a charge, sometimes a retention time, and then the peaks. Everything
else a token holds -- acquisition context, processing history, scan windows,
source files, additional arrays, units, extensions -- has nowhere to go, so the
writers report it rather than dropping it silently.

Neither format has a specification in the sense mzML does. MGF is defined by
what Mascot accepts and MS2 by what its readers parse, so these writers emit the
common subset that tools agree on and the readers accept the variations seen in
practice.
"""

from __future__ import annotations

import math
import re

from ..model import DecodedSpectrum, InlineSpectrum, SpectrlCvParam, SpectrlPrecursor, SpectrlScan, SpectrlSelectedIon
from ._report import ConversionResult

SELECTED_ION_MZ = "MS:1000744"
CHARGE_STATE = "MS:1000041"
PEAK_INTENSITY = "MS:1000042"
SCAN_START_TIME = "MS:1000016"
MS_LEVEL = "MS:1000511"
UO_SECOND = "UO:0000010"
UO_MINUTE = "UO:0000031"


def _find(params, accession):
    for param in params or []:
        if param.accession == accession:
            return param.value
    return None


def _precursor_of(spectrum):
    """The first selected ion's m/z, charge and intensity, if there is one."""
    for precursor in spectrum.precursors or []:
        for ion in precursor.selected_ions or []:
            mz = _find(ion.params, SELECTED_ION_MZ)
            if mz is not None:
                return (
                    float(mz),
                    _find(ion.params, CHARGE_STATE),
                    _find(ion.params, PEAK_INTENSITY),
                )
    return None


def _retention_seconds(spectrum):
    """Scan start time in seconds. mzML records minutes as often as seconds."""
    for scan in spectrum.scans or []:
        for param in scan.params or []:
            if param.accession == SCAN_START_TIME and param.value is not None:
                value = float(param.value)
                return value * 60 if param.unit_accession == UO_MINUTE else value
    return None


def _inventory(spectrum, result: ConversionResult) -> None:
    """Report what a precursor-plus-peaks format cannot represent."""
    checks = [
        (spectrum.acquisition, "acquisition", "acquisition context (instrument and components)"),
        (spectrum.processing, "processing", "processing history"),
        (spectrum.source, "source", "source file metadata"),
        (spectrum.products, "products", "product ion selection"),
        (spectrum.extensions, "extensions", "spectrum extensions"),
        (spectrum.array_extensions, "array_extensions", "array extensions"),
        (spectrum.cv_versions, "cv_versions", "ontology version provenance"),
        (spectrum.user_params, "user_params", "spectrum user parameters"),
    ]
    for value, path, description in checks:
        if value:
            result.add("dropped", path, description)
    extra = [k for k in (spectrum.extra_arrays or {})]
    if extra:
        result.add("dropped", "extra_arrays", f"additional arrays ({', '.join(sorted(extra))})")
    if spectrum.charge is not None:
        result.add("dropped", "charge", "per-peak charge array")
    if any(scan.windows for scan in spectrum.scans or []):
        result.add("dropped", "scans.windows", "scan windows")
    # Spectrum-level CV params beyond the few the header encodes.
    carried = {MS_LEVEL}
    extras = sorted({p.accession for p in spectrum.params or []} - carried)
    if extras:
        result.add("dropped", "params", f"{len(extras)} spectrum CV parameter(s), including {extras[0]}")


def _peaks(spectrum):
    mz = spectrum.mz if spectrum.mz is not None else []
    intensity = spectrum.intensity if spectrum.intensity is not None else []
    return zip(mz, intensity, strict=False)


def _number(value: float) -> str:
    """Round-trippable shortest form, without numpy's array scalar repr."""
    return repr(float(value))


def write_mgf(spectrum: DecodedSpectrum, *, title: str | None = None) -> ConversionResult:
    """Write one spectrum as a single-entry MGF.

    A spectrum with no precursor is written without PEPMASS and reported,
    because MGF's own convention expects one and many readers require it.
    """
    result = ConversionResult("", "mgf")
    _inventory(spectrum, result)
    precursor = _precursor_of(spectrum)
    lines = ["BEGIN IONS", f"TITLE={title or spectrum.id or 'spectrl'}"]
    if precursor is None:
        result.add(
            "no_precursor",
            "precursors",
            "no precursor ion, so no PEPMASS was written; most MGF readers expect one",
        )
    else:
        mz, charge, intensity = precursor
        lines.append(f"PEPMASS={_number(mz)}" + (f" {_number(float(intensity))}" if intensity is not None else ""))
        if charge is not None:
            value = int(float(charge))
            lines.append(f"CHARGE={abs(value)}{'+' if value >= 0 else '-'}")
    seconds = _retention_seconds(spectrum)
    if seconds is not None:
        lines.append(f"RTINSECONDS={_number(seconds)}")
    for mz, intensity in _peaks(spectrum):
        lines.append(f"{_number(mz)} {_number(intensity)}")
    lines.append("END IONS")
    result.text = "\n".join(lines) + "\n"
    return result


def write_ms2(spectrum: DecodedSpectrum, *, scan: int | None = None) -> ConversionResult:
    """Write one spectrum as a single-entry MS2 file."""
    result = ConversionResult("", "ms2")
    _inventory(spectrum, result)
    precursor = _precursor_of(spectrum)
    number = scan if scan is not None else _scan_number(spectrum.id)
    lines = [
        "H\tCreationDate\t",
        "H\tExtractor\tspectrl",
    ]
    if precursor is None:
        result.add(
            "no_precursor",
            "precursors",
            "no precursor ion; the MS2 S line requires a precursor m/z, so 0 was written",
        )
        lines.append(f"S\t{number}\t{number}\t0")
    else:
        mz, charge, _ = precursor
        lines.append(f"S\t{number}\t{number}\t{_number(mz)}")
        seconds = _retention_seconds(spectrum)
        if seconds is not None:
            lines.append(f"I\tRTime\t{_number(seconds / 60)}")
        if charge is not None:
            state = abs(int(float(charge))) or 1
            # The Z line's mass is the singly-protonated neutral mass.
            lines.append(f"Z\t{state}\t{_number(mz * state - (state - 1) * 1.00727646677)}")
    for mz, intensity in _peaks(spectrum):
        lines.append(f"{_number(mz)} {_number(intensity)}")
    result.text = "\n".join(lines) + "\n"
    return result


def _scan_number(spectrum_id: str | None) -> int:
    """A scan number for the S line, from a native id when one is present."""
    if spectrum_id:
        match = re.search(r"scan=(\d+)", spectrum_id) or re.search(r"(\d+)\s*$", spectrum_id)
        if match:
            return int(match.group(1))
    return 0


def _spectrum(mz, intensity, *, spectrum_id, ms_level, precursor, retention_seconds):
    """Build an InlineSpectrum from what a peak-list format supplies."""
    import numpy as np  # noqa: PLC0415

    params = [SpectrlCvParam(MS_LEVEL, ms_level)]
    scans = []
    if retention_seconds is not None:
        scans = [SpectrlScan(params=[SpectrlCvParam(SCAN_START_TIME, retention_seconds, UO_SECOND)])]
    precursors = []
    if precursor is not None:
        mz_value, charge, intensity_value = precursor
        ion = [SpectrlCvParam(SELECTED_ION_MZ, mz_value)]
        if charge is not None:
            ion.append(SpectrlCvParam(CHARGE_STATE, charge))
        if intensity_value is not None:
            ion.append(SpectrlCvParam(PEAK_INTENSITY, intensity_value))
        precursors = [SpectrlPrecursor(selected_ions=[SpectrlSelectedIon(params=ion)])]
    return InlineSpectrum(
        default_array_length=len(mz),
        mz=np.asarray(mz, dtype="float64"),
        intensity=np.asarray(intensity, dtype="float64"),
        id=spectrum_id,
        params=params,
        scans=scans,
        precursors=precursors,
    )


def _peak_line(line: str, number: int, where: str):
    parts = line.split()
    if len(parts) < 2:
        raise ValueError(f"{where} line {number}: expected 'mz intensity', got {line!r}")
    try:
        mz, intensity = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(f"{where} line {number}: peak values must be numbers, got {line!r}") from None
    if not (math.isfinite(mz) and math.isfinite(intensity)):
        raise ValueError(f"{where} line {number}: peak values must be finite")
    return mz, intensity


_CHARGE = re.compile(r"^([+-]?\d+)([+-]?)$")


def _parse_charge(text: str) -> int | None:
    """MGF writes 2+, +2, or 2; a list like '2+ and 3+' is genuinely ambiguous."""
    token = text.strip().split()[0] if text.strip() else ""
    match = _CHARGE.match(token)
    if not match:
        return None
    value = int(match.group(1))
    return -abs(value) if match.group(2) == "-" else abs(value)


def read_mgf(text: str) -> list[InlineSpectrum]:
    """Parse every BEGIN IONS block in an MGF document."""
    spectra: list[InlineSpectrum] = []
    header: dict[str, str] = {}
    mz: list[float] = []
    intensity: list[float] = []
    inside = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(("#", ";", "!")):
            continue
        upper = line.upper()
        if upper == "BEGIN IONS":
            if inside:
                raise ValueError(f"MGF line {number}: BEGIN IONS inside an open block")
            inside, header, mz, intensity = True, {}, [], []
            continue
        if upper == "END IONS":
            if not inside:
                raise ValueError(f"MGF line {number}: END IONS without BEGIN IONS")
            spectra.append(_from_mgf_block(header, mz, intensity))
            inside = False
            continue
        if not inside:
            continue  # Global parameters before the first block apply to search, not to peaks.
        if "=" in line and not line[0].isdigit():
            key, _, value = line.partition("=")
            header[key.strip().upper()] = value.strip()
            continue
        a, b = _peak_line(line, number, "MGF")
        mz.append(a)
        intensity.append(b)
    if inside:
        raise ValueError("MGF ended inside an unterminated BEGIN IONS block")
    return spectra


def _from_mgf_block(header, mz, intensity):
    precursor = None
    if "PEPMASS" in header:
        parts = header["PEPMASS"].split()
        precursor = (
            float(parts[0]),
            _parse_charge(header["CHARGE"]) if "CHARGE" in header else None,
            float(parts[1]) if len(parts) > 1 else None,
        )
    seconds = None
    if "RTINSECONDS" in header:
        seconds = float(header["RTINSECONDS"].split()[0])
    return _spectrum(
        mz,
        intensity,
        spectrum_id=header.get("TITLE"),
        # MGF describes fragmentation, so a block without a precursor is still
        # read as MS2 rather than guessed at.
        ms_level=2,
        precursor=precursor,
        retention_seconds=seconds,
    )


_PROTON = 1.00727646677


def read_ms2(text: str) -> list[InlineSpectrum]:
    """Parse every S block in an MS2 document."""
    spectra: list[InlineSpectrum] = []
    current: dict | None = None
    mz: list[float] = []
    intensity: list[float] = []

    def flush():
        if current is not None:
            spectra.append(
                _spectrum(
                    mz,
                    intensity,
                    spectrum_id=f"scan={current['scan']}" if current["scan"] else None,
                    ms_level=2,
                    precursor=current["precursor"],
                    retention_seconds=current["rtime"],
                )
            )

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line:
            continue
        kind = line[0]
        if kind == "H":
            continue
        if kind == "S":
            flush()
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"MS2 line {number}: S line needs scan, scan and precursor m/z")
            precursor_mz = float(parts[3])
            current = {
                "scan": parts[1],
                "precursor": (precursor_mz, None, None) if precursor_mz else None,
                "rtime": None,
            }
            mz, intensity = [], []
            continue
        if current is None:
            continue
        if kind == "I":
            parts = line.split()
            if len(parts) >= 3 and parts[1].upper() == "RTIME":
                current["rtime"] = float(parts[2]) * 60  # MS2 records RTime in minutes.
            continue
        if kind == "Z":
            parts = line.split()
            if len(parts) >= 2 and current["precursor"]:
                state = int(float(parts[1]))
                mz_value, _, intensity_value = current["precursor"]
                current["precursor"] = (mz_value, state, intensity_value)
            continue
        if kind == "D":
            continue
        a, b = _peak_line(line, number, "MS2")
        mz.append(a)
        intensity.append(b)
    flush()
    return spectra
