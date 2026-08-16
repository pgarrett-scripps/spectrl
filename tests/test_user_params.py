"""Free-text userParams at spectrum and scan level (omit-when-empty)."""

from __future__ import annotations

import numpy as np

from spectrl import decode_token, encode_spectrum
from spectrl.model import InlineSpectrum, SpectrlCvParam, SpectrlScan, SpectrlUserParam


def _base(**kw):
    return InlineSpectrum(default_array_length=2, mz=np.array([100.0, 200.0]), intensity=np.array([1e3, 2e3]), **kw)


def test_empty_user_params_is_byte_identical():
    """Adding an empty user_params list MUST NOT change the token (omit-when-empty)."""
    assert encode_spectrum(_base()) == encode_spectrum(_base(user_params=[]))


def test_spectrum_user_params_roundtrip():
    spec = _base(
        user_params=[
            SpectrlUserParam(name="Mascot score", value=42.7, type="xsd:float"),
            SpectrlUserParam(name="note", value="rerun"),
            SpectrlUserParam(name="elapsed", value=3.5, unit_accession="UO:0000010"),
        ]
    )
    u = decode_token(encode_spectrum(spec)).user_params
    assert [p.name for p in u] == ["Mascot score", "note", "elapsed"]
    assert u[0].value == 42.7 and u[0].type == "xsd:float"
    assert u[1].value == "rerun" and u[1].type is None
    assert u[2].unit_accession == "UO:0000010"


def test_scan_user_params_roundtrip():
    spec = _base(
        scans=[
            SpectrlScan(
                params=[SpectrlCvParam(accession="MS:1000016", value=10.0, unit_accession="UO:0000031")],
                user_params=[SpectrlUserParam(name="[Thermo]Mono M/Z", value="445.12", type="xsd:string")],
            )
        ]
    )
    d = decode_token(encode_spectrum(spec))
    assert d.scans[0].user_params[0].name == "[Thermo]Mono M/Z"
    assert d.scans[0].user_params[0].value == "445.12"


def test_user_params_survive_canonical_sort():
    # m/z out of order forces a canonical re-sort; user params are spectrum-level
    # and must survive the InlineSpectrum rebuild.
    spec = InlineSpectrum(
        default_array_length=3,
        mz=np.array([300.0, 100.0, 200.0]),
        intensity=np.array([3.0, 1.0, 2.0]),
        user_params=[SpectrlUserParam(name="keep me", value="yes")],
    )
    d = decode_token(encode_spectrum(spec))
    assert np.allclose(d.mz, [100, 200, 300])
    assert d.user_params[0].name == "keep me"


def test_no_user_params_is_empty():
    assert decode_token(encode_spectrum(_base())).user_params == []


def _with_vendor_params():
    return _base(
        user_params=[SpectrlUserParam(name="filter string", value="ITMS + c NSI", type="xsd:string")],
        scans=[
            SpectrlScan(
                params=[SpectrlCvParam(accession="MS:1000016", value=10.0, unit_accession="UO:0000031")],
                user_params=[SpectrlUserParam(name="[Thermo]Mono M/Z", value="445.12", type="xsd:string")],
            )
        ],
    )


def test_drop_user_params_matches_a_spectrum_that_never_had_them():
    """drop_user_params MUST yield the same token as omitting them at the source."""
    without = _base(
        scans=[SpectrlScan(params=[SpectrlCvParam(accession="MS:1000016", value=10.0, unit_accession="UO:0000031")])]
    )
    assert encode_spectrum(_with_vendor_params(), drop_user_params=True) == encode_spectrum(without)


def test_drop_user_params_keeps_cv_params_and_peaks():
    d = decode_token(encode_spectrum(_with_vendor_params(), drop_user_params=True))
    assert d.user_params == []
    assert d.scans[0].user_params == []
    assert d.scans[0].params[0].accession == "MS:1000016"
    assert np.allclose(d.mz, [100.0, 200.0])


def test_drop_user_params_is_inert_when_there_are_none():
    assert encode_spectrum(_base(), drop_user_params=True) == encode_spectrum(_base())


def test_drop_user_params_does_not_mutate_the_input():
    spec = _with_vendor_params()
    encode_spectrum(spec, drop_user_params=True)
    assert spec.user_params and spec.scans[0].user_params
