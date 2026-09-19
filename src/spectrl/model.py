"""Data models for spectrl encode input (InlineSpectrum) and decode output (DecodedSpectrum)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True)
class ArrayEncoding:
    """Numeric encoding override. None selects the profile default."""

    encoding: object | None = None


@dataclass
class SpectrlCvParam:
    """A CV parameter for use within spectrl, mirroring mzML cvParam semantics.

    Accession and unit_accession use 'ONTOLOGY:NNNNNNN' format (e.g. 'MS:1000511', 'UO:0000031').
    A None value indicates a flag parameter (presence is the meaning).
    """

    accession: str
    value: float | int | str | None = None
    unit_accession: str | None = None


@dataclass
class SpectrlUserParam:
    """A free-text user parameter (mzML userParam) with no CV accession.

    Carries an arbitrary name plus an optional value, XSD type annotation, and
    unit accession. Use a SpectrlCvParam instead whenever a CV term exists.
    """

    name: str
    value: str | float | int | None = None
    type: str | None = None  # XSD type annotation, e.g. "xsd:float"
    unit_accession: str | None = None


@dataclass
class SpectrlScanWindow:
    """A scan window with lower/upper m/z limits as CV params."""

    params: list[SpectrlCvParam] = field(default_factory=list)
    user_params: list[SpectrlUserParam] = field(default_factory=list)


@dataclass
class SpectrlScan:
    """A single scan event with timing and window metadata."""

    params: list[SpectrlCvParam] = field(default_factory=list)
    windows: list[SpectrlScanWindow] = field(default_factory=list)
    user_params: list[SpectrlUserParam] = field(default_factory=list)

    source: dict | None = None
    acquisition: dict | None = None
    processing: list[dict] = field(default_factory=list)


@dataclass
class SpectrlIsolationWindow:
    """An isolation window with target m/z and offset params."""

    params: list[SpectrlCvParam] = field(default_factory=list)
    user_params: list[SpectrlUserParam] = field(default_factory=list)


@dataclass
class SpectrlSelectedIon:
    """A selected ion with m/z, charge, intensity params."""

    params: list[SpectrlCvParam] = field(default_factory=list)
    user_params: list[SpectrlUserParam] = field(default_factory=list)


@dataclass
class SpectrlActivation:
    """Activation method params (method as flag + energy as value)."""

    params: list[SpectrlCvParam] = field(default_factory=list)
    user_params: list[SpectrlUserParam] = field(default_factory=list)


@dataclass
class SpectrlPrecursor:
    """A precursor entry with isolation window, selected ions, and activation."""

    isolation_window: SpectrlIsolationWindow | None = None
    selected_ions: list[SpectrlSelectedIon] = field(default_factory=list)
    activation: SpectrlActivation | None = None

    source: dict | None = None
    acquisition: dict | None = None
    processing: list[dict] = field(default_factory=list)


@dataclass
class SpectrlProduct:
    """A product entry with an isolation window."""

    isolation_window: SpectrlIsolationWindow | None = None


@dataclass
class InlineSpectrum:
    """Input model for spectrl encoding. Mirrors mzML spectrum structure.

    Attributes:
        default_array_length: Number of peaks (mzML @defaultArrayLength).
        mz: m/z array, must be sorted ascending.
        intensity: Intensity array.
        charge: Optional per-peak charge array.
        id: Spectrum identifier string (mzML @id), e.g. 'scan=12298'.
        params: Spectrum-level CV params (ms level, polarity, centroid flag, TIC, etc.).
        scans: List of scan entries.
        scan_combination: Optional scan-list combination CV param.
        precursors: List of precursor entries.
        products: List of product entries.
        extra_arrays: Additional per-peak binary arrays, including every ion-
            mobility variant, keyed by a PSI-MS accession (e.g. 'MS:1003008') or
            a free-text name for a non-standard array (carried as MS:1000786).
            Each value is a per-peak ndarray; float64/float32/int32 dtypes are
            preserved.
        array_names: Optional nonempty array names keyed by mz, intensity,
            charge, or an extra-array key. A custom array name must match its key.
    """

    default_array_length: int
    mz: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    intensity: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    charge: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    id: str | None = None
    params: list[SpectrlCvParam] = field(default_factory=list)
    scans: list[SpectrlScan] = field(default_factory=list)
    scan_combination: SpectrlCvParam | None = None
    precursors: list[SpectrlPrecursor] = field(default_factory=list)
    products: list[SpectrlProduct] = field(default_factory=list)
    extra_arrays: dict[str, NDArray] = field(default_factory=dict)
    array_units: dict[str, str] = field(default_factory=dict)
    array_params: dict[str, list[SpectrlCvParam]] = field(default_factory=dict)
    array_user_params: dict[str, list[SpectrlUserParam]] = field(default_factory=dict)
    array_processing: dict[str, list[dict]] = field(default_factory=dict)
    array_extensions: dict[str, dict] = field(default_factory=dict)
    source: dict | None = None
    acquisition: dict | None = None
    processing: list[dict] = field(default_factory=list)
    extensions: dict = field(default_factory=dict)

    user_params: list[SpectrlUserParam] = field(default_factory=list)

    array_names: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize ordinary Python array-likes at the public API boundary."""
        for name in ("mz", "intensity", "charge"):
            values = getattr(self, name)
            if values is not None and np.asarray(values).dtype.kind not in "fiu":
                raise ValueError(f"Array '{name}' must contain real numbers")
        if self.mz is not None:
            self.mz = _normalize_array(self.mz)
        if self.intensity is not None:
            self.intensity = _normalize_array(self.intensity)
        if self.charge is not None:
            self.charge = _normalize_array(self.charge)
        self.extra_arrays = {str(key): np.asarray(values) for key, values in self.extra_arrays.items()}
        self.array_units = {str(key): str(unit) for key, unit in self.array_units.items()}


@dataclass
class DecodedSpectrum:
    """Output model from spectrl decoding.

    Mirrors InlineSpectrum but represents what was recovered from the token.
    The checksum field is verified during decode.
    """

    default_array_length: int
    mz: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    intensity: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    charge: NDArray[np.float64] | NDArray[np.float32] | NDArray[np.int32] | None = None
    id: str | None = None
    params: list[SpectrlCvParam] = field(default_factory=list)
    scans: list[SpectrlScan] = field(default_factory=list)
    scan_combination: SpectrlCvParam | None = None
    precursors: list[SpectrlPrecursor] = field(default_factory=list)
    products: list[SpectrlProduct] = field(default_factory=list)
    extra_arrays: dict[str, NDArray] = field(default_factory=dict)
    array_units: dict[str, str] = field(default_factory=dict)
    array_params: dict[str, list[SpectrlCvParam]] = field(default_factory=dict)
    array_user_params: dict[str, list[SpectrlUserParam]] = field(default_factory=dict)
    array_processing: dict[str, list[dict]] = field(default_factory=dict)
    array_extensions: dict[str, dict] = field(default_factory=dict)
    source: dict | None = None
    acquisition: dict | None = None
    processing: list[dict] = field(default_factory=list)
    extensions: dict = field(default_factory=dict)

    user_params: list[SpectrlUserParam] = field(default_factory=list)
    checksum: str = ""
    format_version: int = 3
    array_names: dict[str, str] = field(default_factory=dict)

    @property
    def mobility_arrays(self) -> dict[str, NDArray]:
        """A filtered view of accession-keyed ion-mobility arrays."""
        from .cv import ION_MOBILITY_ARRAY_TAILS, accession_tail

        tails = set(ION_MOBILITY_ARRAY_TAILS.values())
        return {
            accession: values
            for accession, values in self.extra_arrays.items()
            if accession.startswith("MS:") and accession_tail(accession) in tails
        }


def _normalize_array(values):
    if not isinstance(values, np.ndarray):
        return np.asarray(values, dtype=np.float64)
    if values.dtype.kind == "f" and values.dtype.itemsize in (4, 8):
        return values.astype(values.dtype.newbyteorder("="), copy=False)
    if values.dtype.kind in "iu" and (not values.size or (values.min() >= -(2**31) and values.max() < 2**31)):
        return values.astype(np.int32)
    raise ValueError("core arrays must be float32, float64, or integers representable as int32")
