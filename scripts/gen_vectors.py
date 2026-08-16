"""Generate language-agnostic conformance test vectors from the Python reference impl.

Each vector pairs a canonical `spectrl2` token with the exact values a conformant
consumer must recover from it. Numpress decode is deterministic, so the stored
arrays are the *decoded* values and consumers MUST reproduce them (within a tiny
float epsilon). Lossless arrays MUST match exactly.

Output: test-vectors/vectors.json  (+ test-vectors/README.md is hand-written)

Run:  uv run python scripts/gen_vectors.py
"""

from __future__ import annotations

import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np

from spectrl import decode_token, encode_spectrum
from spectrl.model import (
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

OUT = Path(__file__).resolve().parent.parent / "test-vectors" / "vectors.json"


def _cvparam_json(p: SpectrlCvParam) -> dict:
    return {"accession": p.accession, "value": p.value, "unit_accession": p.unit_accession}


def _params_json(params) -> list:
    return [_cvparam_json(p) for p in params]


def _user_params_json(us) -> list:
    return [{"name": u.name, "value": u.value, "type": u.type, "unit_accession": u.unit_accession} for u in us]


def _decoded_json(token: str) -> dict:
    """Decode a token and serialise the recovered spectrum to plain JSON."""
    d = decode_token(token)

    def arr(a):
        return None if a is None else [float(x) for x in a]

    def extra(arrays):
        out = {}
        for k, a in arrays.items():
            vals = [int(x) for x in a] if a.dtype.kind == "i" else [float(x) for x in a]
            out[k] = {"dtype": str(a.dtype), "values": vals}
        return out

    return {
        "default_array_length": d.default_array_length,
        "id": d.id,
        "mz": arr(d.mz),
        "intensity": arr(d.intensity),
        "charge": arr(d.charge),
        "ion_mobility": arr(d.ion_mobility),
        "ion_mobility_type": d.ion_mobility_type,
        "extra_arrays": extra(d.extra_arrays),
        "params": _params_json(d.params),
        "scans": [
            {
                "params": _params_json(s.params),
                "windows": [{"params": _params_json(w.params)} for w in s.windows],
                "user_params": _user_params_json(s.user_params),
            }
            for s in d.scans
        ],
        "scan_combination": (None if d.scan_combination is None else _cvparam_json(d.scan_combination)),
        "precursors": [
            {
                "isolation_window": (
                    None if p.isolation_window is None else {"params": _params_json(p.isolation_window.params)}
                ),
                "selected_ions": [{"params": _params_json(si.params)} for si in p.selected_ions],
                "activation": (None if p.activation is None else {"params": _params_json(p.activation.params)}),
            }
            for p in d.precursors
        ],
        "products": [
            {
                "isolation_window": (
                    None if pr.isolation_window is None else {"params": _params_json(pr.isolation_window.params)}
                )
            }
            for pr in d.products
        ],
        "interp": d.interp,
        "user_params": _user_params_json(d.user_params),
        "hash": d.hash,
        "format_version": d.format_version,
    }


def _vector(name: str, description: str, spec: InlineSpectrum, *, lossless: bool, tol: dict | None) -> dict:
    token = encode_spectrum(spec, lossless=lossless)
    return {
        "name": name,
        "description": description,
        "mode": "lossless" if lossless else "lossy",
        "token": token,
        "tolerance": tol if not lossless else {"abs": 0.0, "rel": 0.0},
        "decoded": _decoded_json(token),
    }


# tolerance for lossy comparisons; numpress decode is deterministic so consumers
# should match the stored (already-decoded) arrays to near machine precision.
LOSSY_TOL = {"abs": 1e-6, "rel": 1e-6}
EXACT_TOL = {"abs": 1e-9, "rel": 0.0}


def _specs() -> list[tuple[str, str, InlineSpectrum]]:
    out: list[tuple[str, str, InlineSpectrum]] = []

    # 1. minimal: m/z + intensity only
    out.append(
        (
            "minimal",
            "m/z and intensity arrays only, no metadata",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([147.11, 175.119, 246.156]),
                intensity=np.array([1.0e5, 8.0e4, 3.2e4]),
            ),
        )
    )

    # 2. centroid MS2 with common spectrum params (int, flags)
    out.append(
        (
            "centroid_ms2_params",
            "MS2 centroid spectrum with ms-level (int), positive-scan flag, centroid flag, TIC",
            InlineSpectrum(
                default_array_length=4,
                mz=np.array([110.071, 175.119, 288.203, 405.221]),
                intensity=np.array([2.1e4, 9.9e4, 5.4e4, 1.2e4]),
                id="controllerType=0 controllerNumber=1 scan=1042",
                params=[
                    SpectrlCvParam(accession="MS:1000511", value=2),  # ms level
                    SpectrlCvParam(accession="MS:1000130"),  # positive scan
                    SpectrlCvParam(accession="MS:1000127"),  # centroid spectrum
                    SpectrlCvParam(accession="MS:1000285", value=187600.0),  # total ion current
                ],
            ),
        )
    )

    # 3. with charge array
    out.append(
        (
            "with_charge_array",
            "deconvoluted spectrum carrying a per-peak charge array",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([500.25, 750.4, 1001.5]),
                intensity=np.array([4.0e4, 2.0e4, 1.0e4]),
                charge=np.array([2.0, 1.0, 1.0]),
            ),
        )
    )

    # 3b. charge array with negative sentinels: PIC cannot encode negatives, so
    # lossy encoding must fall back to lossless zlib for the charge array
    out.append(
        (
            "negative_charge_sentinel",
            "charge array with a negative (unassigned/singleton) sentinel; lossy encode falls back "
            "to lossless zlib for the charge array and round-trips exactly",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([500.25, 750.4, 1001.5]),
                intensity=np.array([4.0e4, 2.0e4, 1.0e4]),
                charge=np.array([2.0, -1.0, 1.0]),
            ),
        )
    )

    # 3c. negative intensities: slof cannot encode negatives, so lossy encoding
    # must fall back to lossless zlib for the intensity array
    out.append(
        (
            "negative_intensity_fallback",
            "baseline-subtracted intensities with negative values; lossy encode falls back to "
            "lossless zlib for the intensity array and round-trips exactly",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([100.0, 200.0, 300.0]),
                intensity=np.array([-0.5, 1.0e4, -3.0]),
            ),
        )
    )

    # 4. scans with scan window + scan start time (float value with unit)
    out.append(
        (
            "scan_list_with_window",
            "scan list with scan-start-time (minute unit) and a scan window m/z range",
            InlineSpectrum(
                default_array_length=2,
                mz=np.array([200.1, 400.2]),
                intensity=np.array([5.0e4, 6.0e4]),
                params=[SpectrlCvParam(accession="MS:1000511", value=1)],
                scans=[
                    SpectrlScan(
                        params=[
                            SpectrlCvParam(accession="MS:1000016", value=15.34, unit_accession="UO:0000031"),
                        ],
                        windows=[
                            SpectrlScanWindow(
                                params=[
                                    SpectrlCvParam(accession="MS:1000501", value=100.0, unit_accession="MS:1000040"),
                                    SpectrlCvParam(accession="MS:1000500", value=2000.0, unit_accession="MS:1000040"),
                                ]
                            )
                        ],
                    )
                ],
            ),
        )
    )

    # 5. full precursor: isolation window + selected ion + activation
    out.append(
        (
            "precursor_full",
            "precursor with isolation window, selected ion (m/z, charge), and HCD activation",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([129.102, 258.156, 386.18]),
                intensity=np.array([3.0e4, 7.0e4, 2.0e4]),
                params=[SpectrlCvParam(accession="MS:1000511", value=2)],
                precursors=[
                    SpectrlPrecursor(
                        isolation_window=SpectrlIsolationWindow(
                            params=[
                                SpectrlCvParam(accession="MS:1000827", value=445.12),  # target m/z
                                SpectrlCvParam(accession="MS:1000828", value=0.75),  # lower offset
                                SpectrlCvParam(accession="MS:1000829", value=0.75),  # upper offset
                            ]
                        ),
                        selected_ions=[
                            SpectrlSelectedIon(
                                params=[
                                    SpectrlCvParam(accession="MS:1000744", value=445.12),  # selected ion m/z
                                    SpectrlCvParam(accession="MS:1000041", value=2),  # charge state
                                ]
                            )
                        ],
                        activation=SpectrlActivation(
                            params=[
                                SpectrlCvParam(accession="MS:1000422"),  # beam-type CID (HCD)
                                SpectrlCvParam(accession="MS:1000045", value=27.0, unit_accession="UO:0000266"),
                            ]
                        ),
                    )
                ],
                products=[
                    SpectrlProduct(
                        isolation_window=SpectrlIsolationWindow(
                            params=[SpectrlCvParam(accession="MS:1000827", value=445.12)]
                        )
                    )
                ],
            ),
        )
    )

    # 6. ProForma interpretation
    out.append(
        (
            "with_proforma",
            "spectrum carrying a ProForma 2.0 peptidoform interpretation string",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([147.113, 276.155, 389.239]),
                intensity=np.array([1.0e5, 5.0e4, 2.0e4]),
                interp="ELVIS[Phospho]K/2",
            ),
        )
    )

    # 7. ion mobility array (mean inverse reduced ion mobility, MS:1003008)
    out.append(
        (
            "ion_mobility",
            "spectrum with a per-peak ion-mobility array",
            InlineSpectrum(
                default_array_length=3,
                mz=np.array([300.1, 600.2, 900.3]),
                intensity=np.array([4.0e4, 3.0e4, 2.0e4]),
                ion_mobility=np.array([0.82, 0.91, 1.05]),
                ion_mobility_type="MS:1003008",
            ),
        )
    )

    # 8. string-valued param + non-UO unit on a value (exercises non-UO [ontology, tail] unit form)
    out.append(
        (
            "string_value_and_non_uo_unit",
            "a string-valued spectrum param plus a value carrying an MS-ontology (non-UO) unit",
            InlineSpectrum(
                default_array_length=2,
                mz=np.array([123.04, 456.07]),
                intensity=np.array([9.0e4, 1.0e4]),
                params=[
                    SpectrlCvParam(accession="MS:1000511", value=1),
                    SpectrlCvParam(accession="MS:1000512", value="FTMS + p ESI Full ms"),  # filter string
                    SpectrlCvParam(accession="MS:1000505", value=1.2e5, unit_accession="MS:1000131"),  # base peak int
                ],
            ),
        )
    )

    # 9b. auxiliary arrays: a named CV array + non-standard float32 + non-standard int32
    out.append(
        (
            "extra_arrays",
            "auxiliary per-peak arrays: signal-to-noise (named CV, float64), a non-standard float32 array, "
            "and a non-standard int32 array",
            InlineSpectrum(
                default_array_length=4,
                mz=np.array([150.05, 300.1, 450.2, 600.3]),
                intensity=np.array([8.0e4, 5.0e4, 3.0e4, 1.0e4]),
                extra_arrays={
                    "MS:1000517": np.array([120.0, 80.0, 45.0, 12.0]),  # signal-to-noise array
                    "iso_score": np.array([0.98, 0.91, 0.74, 0.55], dtype=np.float32),
                    "peak_flags": np.array([3, 1, 0, 2], dtype=np.int32),
                },
            ),
        )
    )

    # 9c. user params: free-text params at spectrum level + a scan-level param
    out.append(
        (
            "user_params",
            "free-text userParams: spectrum-level (typed value + unit) and a scan-level Thermo trailer extra",
            InlineSpectrum(
                default_array_length=2,
                mz=np.array([200.1, 400.2]),
                intensity=np.array([5.0e4, 6.0e4]),
                params=[SpectrlCvParam(accession="MS:1000511", value=2)],
                user_params=[
                    SpectrlUserParam(name="Mascot score", value=42.7, type="xsd:float"),
                    SpectrlUserParam(name="reanalysis note", value="rerun with semitryptic"),
                ],
                scans=[
                    SpectrlScan(
                        params=[SpectrlCvParam(accession="MS:1000016", value=20.5, unit_accession="UO:0000031")],
                        user_params=[
                            SpectrlUserParam(
                                name="[Thermo Trailer Extra]Monoisotopic M/Z:", value="445.1203", type="xsd:string"
                            ),
                        ],
                    )
                ],
            ),
        )
    )

    # 9. non-MS-ontology parameter key (exercises the string-key form, §5)
    out.append(
        (
            "non_ms_ontology_param_key",
            "a UO-ontology spectrum parameter, whose map key is the full accession string",
            InlineSpectrum(
                default_array_length=2,
                mz=np.array([123.04, 456.07]),
                intensity=np.array([9.0e4, 1.0e4]),
                params=[
                    SpectrlCvParam(accession="MS:1000511", value=1),
                    SpectrlCvParam(accession="UO:0000010", value=3.5),  # second (non-MS key)
                ],
            ),
        )
    )

    return out


def main() -> None:
    try:
        pyver = version("spectrl")
    except Exception:
        pyver = "0.1.0"

    vectors = []
    for name, desc, spec in _specs():
        vectors.append(_vector(name, desc, spec, lossless=False, tol=LOSSY_TOL))
        vectors.append(_vector(f"{name}__lossless", desc + " (lossless)", spec, lossless=True, tol=EXACT_TOL))

    doc = {
        "spectrl_format_version": 2,
        "generated_by": f"spectrl-python {pyver}",
        "note": (
            "Conformance vectors. A consumer MUST recover `decoded` from `token`. "
            "Numpress decode is deterministic; arrays should match the stored decoded "
            "values within `tolerance`. Lossless vectors MUST match exactly. The stored "
            "`hash` MUST verify."
        ),
        "vectors": vectors,
    }

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {len(vectors)} vectors to {out}")


if __name__ == "__main__":
    main()
