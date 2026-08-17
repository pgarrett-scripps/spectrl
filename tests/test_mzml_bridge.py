"""Acceptance criterion 4: mzML faithfulness via from_mzmlpy bridge."""

from types import SimpleNamespace

import numpy as np
import pytest
from mzmlpy.run import Mzml

from spectrl import decode_token, encode_spectrum, from_mzmlpy
from spectrl.model import InlineSpectrum
from spectrl.mzml import _collect_arrays, _collect_extra_arrays

MZML_PATH = "tests/data/example.mzML"


@pytest.fixture(scope="module")
def mzml():
    with Mzml(MZML_PATH) as m:
        yield m


def test_from_mzmlpy_returns_inline_spectrum(mzml):
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    assert isinstance(inline, InlineSpectrum)


def test_mz_intensity_populated(mzml):
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    if inline.mz is not None:
        assert len(inline.mz) > 0
    if inline.intensity is not None:
        assert len(inline.intensity) > 0


def test_id_preserved(mzml):
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    assert inline.id == spec.id


def test_cv_params_populated(mzml):
    """Spectrum-level CV params survive the bridge."""
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    accessions = {p.accession for p in inline.params}
    # ms level should always be present in a spectrum
    assert "MS:1000511" in accessions


def test_dropped_fields_absent(mzml):
    """index, source_file_ref, data_processing_ref are not in InlineSpectrum."""
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    assert not hasattr(inline, "index")
    assert not hasattr(inline, "source_file_ref")
    assert not hasattr(inline, "data_processing_ref")
    assert not hasattr(inline, "spot_id")


def test_bridge_encode_decode_roundtrip(mzml):
    """Full mzmlpy → encode → decode pipeline preserves key metadata."""
    spec = mzml.spectra[0]
    inline = from_mzmlpy(spec)
    token = encode_spectrum(inline)
    decoded = decode_token(token)

    assert decoded.id == inline.id
    assert decoded.default_array_length == inline.default_array_length

    if inline.mz is not None and decoded.mz is not None:
        np.testing.assert_allclose(decoded.mz, inline.mz, rtol=1e-4, atol=1e-4)


def test_ms2_precursor_bridge(mzml):
    """MS2 spectra: precursor metadata survives the bridge."""
    for spec in mzml.spectra:
        if spec.ms_level == 2 and spec.has_precursors:
            inline = from_mzmlpy(spec)
            assert len(inline.precursors) >= 1
            break


def test_bridge_preserves_multiple_ion_mobility_arrays():
    arrays = [
        SimpleNamespace(
            binary_array_type=accession,
            data=np.array(values),
            cv_params=[],
        )
        for accession, values in {
            "MS:1003008": [0.8, 0.9],
            "MS:1003153": [12.1, 13.4],
        }.items()
    ]
    collected = _collect_extra_arrays(SimpleNamespace(id="scan=1", binary_arrays=arrays))
    assert set(collected) == {"MS:1003008", "MS:1003153"}


def test_bridge_preserves_binary_array_units():
    defining = SimpleNamespace(accession="MS:1003153", unit_accession="UO:0000028")
    arrays = [
        SimpleNamespace(
            binary_array_type="MS:1003153",
            data=np.array([12.1, 13.4]),
            cv_params=[defining],
        )
    ]
    values, units = _collect_arrays(SimpleNamespace(id="scan=1", binary_arrays=arrays))
    assert set(values) == {"MS:1003153"}
    assert units == {"MS:1003153": "UO:0000028"}
