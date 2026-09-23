"""Conversion between tokens and mzML, MGF and MS2 files."""

import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum, from_mzmlpy
from spectrl.formats import (
    FORMATS,
    format_for_path,
    read_file,
    read_mgf,
    read_ms2,
    read_mzml,
    write,
    write_mgf,
    write_ms2,
    write_mzml,
)
from spectrl.model import InlineSpectrum, SpectrlCvParam, SpectrlPrecursor, SpectrlScan, SpectrlSelectedIon

EXAMPLE = "tests/data/example.mzML"


def _decoded(index=1, lossless=True):
    from mzmlpy import Mzml

    with Mzml(EXAMPLE) as run:
        spec = from_mzmlpy(run.spectra[index], run=run)
    return decode_token(encode_spectrum(spec, lossless=lossless))


def _ms2_spectrum():
    return InlineSpectrum(
        default_array_length=3,
        mz=np.array([100.5, 200.25, 300.125]),
        intensity=np.array([10.0, 20.0, 30.0]),
        id="scan=42",
        params=[SpectrlCvParam("MS:1000511", 2)],
        scans=[SpectrlScan(params=[SpectrlCvParam("MS:1000016", 5.5, "UO:0000031")])],
        precursors=[
            SpectrlPrecursor(
                selected_ions=[
                    SpectrlSelectedIon(params=[SpectrlCvParam("MS:1000744", 445.25), SpectrlCvParam("MS:1000041", 2)])
                ]
            )
        ],
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("run.mzML", "mzml"), ("x.MGF", "mgf"), ("a.ms2", "ms2"), ("b.mzml.gz", "mzml")],
)
def test_format_is_inferred_from_the_suffix(name, expected):
    assert format_for_path(name) == expected


def test_an_unknown_suffix_names_the_formats_it_knows():
    with pytest.raises(ValueError, match=r"known suffixes: \.mgf, \.ms2, \.mzml"):
        format_for_path("spectrum.txt")


def test_mzml_round_trip_preserves_arrays_and_parameters():
    decoded = _decoded()
    result = write_mzml(decoded)
    assert result.format == "mzml"
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "one.mzML"
        path.write_text(result.text, encoding="utf-8", newline="\n")
        back = decode_token(encode_spectrum(read_mzml(path, index=0)[0], lossless=True))
    assert np.array_equal(back.mz, decoded.mz)
    assert np.array_equal(back.intensity, decoded.intensity)
    assert back.params == decoded.params
    assert back.scans == decoded.scans
    # cv_versions restores the mzML cvList entries it was read from.
    assert back.cv_versions == decoded.cv_versions


def test_mzml_writer_accepts_what_the_benchmark_writer_refused():
    """The analysis writer required an id and rejected extensions outright."""
    spectrum = InlineSpectrum(
        default_array_length=1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        extensions={"example:note": {"revision": 1, "required": False, "data": {"a": 1}}},
    )
    result = write_mzml(decode_token(encode_spectrum(spectrum, lossless=True)))
    assert "<spectrum" in result.text
    assert any(i["code"] == "synthesized_id" for i in result.issues)
    assert any(i["code"] == "extensions_dropped" for i in result.issues)
    assert "extensions" in " ".join(result.omitted)


def test_mzml_keeps_the_lossy_processing_record():
    """The benchmark writer stripped it to keep its size comparison matched.

    It is the only statement that the arrays were quantized, so an
    interoperability writer has to carry it.
    """
    decoded = _decoded(lossless=False)
    assert any(record.get("operation") for record in decoded.processing) or any(
        record.get("operation") for records in decoded.array_processing.values() for record in records
    )
    text = write_mzml(decoded).text
    assert "spectrl:operation" in text or "spectrl:lossy" in text


def test_colliding_identifiers_become_unique_xml_ids():
    """mzML ids are xs:ID and must be unique document-wide; a token's are not."""
    spectrum = InlineSpectrum(
        default_array_length=1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        id="scan=1",
        source={"id": "SHARED", "name": "run.raw"},
        acquisition={"instrument": {"id": "IC1", "software": {"id": "SHARED", "version": "1"}}},
    )
    result = write_mzml(decode_token(encode_spectrum(spectrum, lossless=True)))
    import xml.etree.ElementTree as ET

    root = ET.fromstring(result.text)
    ids = [node.get("id") for node in root.iter() if node.get("id")]
    assert len(ids) == len(set(ids)), ids
    assert any(i["code"] == "id_deduplicated" for i in result.issues)


def test_windows_file_uri_is_repaired():
    spectrum = InlineSpectrum(
        default_array_length=1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        source={"id": "s", "location": "file://F:/data/Exp01"},
    )
    result = write_mzml(decode_token(encode_spectrum(spectrum, lossless=True)))
    assert 'location="file:///F:/data/Exp01"' in result.text
    assert any(i["code"] == "location_uri_normalized" for i in result.issues)


@pytest.mark.parametrize("writer", [write_mgf, write_ms2])
def test_peak_list_formats_report_what_they_drop(writer):
    decoded = _decoded()
    result = writer(decoded)
    assert not result.lossless
    assert result.summary().startswith(f"Not represented by {result.format.upper()}")
    assert any("acquisition" in message for message in result.omitted)


def test_mgf_round_trips_peaks_and_precursor():
    decoded = decode_token(encode_spectrum(_ms2_spectrum(), lossless=True))
    text = write_mgf(decoded).text
    assert "PEPMASS=445.25" in text
    assert "CHARGE=2+" in text
    assert "RTINSECONDS=330.0" in text
    back = read_mgf(text)
    assert len(back) == 1
    assert np.allclose(back[0].mz, decoded.mz)
    assert np.allclose(back[0].intensity, decoded.intensity)
    ion = back[0].precursors[0].selected_ions[0].params
    assert ion[0].accession == "MS:1000744" and ion[0].value == 445.25
    assert ion[1].accession == "MS:1000041" and ion[1].value == 2


def test_ms2_round_trips_peaks_and_precursor():
    decoded = decode_token(encode_spectrum(_ms2_spectrum(), lossless=True))
    text = write_ms2(decoded).text
    assert "\nS\t42\t42\t445.25" in text
    assert "\nZ\t2\t" in text
    back = read_ms2(text)
    assert len(back) == 1
    assert np.allclose(back[0].mz, decoded.mz)
    assert back[0].precursors[0].selected_ions[0].params[0].value == 445.25


def test_mgf_without_a_precursor_is_written_and_reported():
    """An MS1 spectrum has no PEPMASS, which MGF readers generally expect."""
    spectrum = InlineSpectrum(
        default_array_length=2,
        mz=np.array([100.0, 200.0]),
        intensity=np.array([1.0, 2.0]),
        params=[SpectrlCvParam("MS:1000511", 1)],
    )
    result = write_mgf(decode_token(encode_spectrum(spectrum, lossless=True)))
    assert "PEPMASS" not in result.text
    assert "BEGIN IONS" in result.text and "END IONS" in result.text
    assert any(i["code"] == "no_precursor" for i in result.issues)


def test_reading_a_multi_spectrum_file_returns_every_spectrum():
    spectra = read_file(EXAMPLE)
    assert len(spectra) > 1
    assert read_file(EXAMPLE, index=1)[0].id == spectra[1].id
    assert read_file(EXAMPLE, spectrum_id=spectra[1].id)[0].id == spectra[1].id


def test_selecting_a_missing_spectrum_is_an_error():
    with pytest.raises(KeyError):
        read_file(EXAMPLE, spectrum_id="scan=999999")


@pytest.mark.parametrize("format", FORMATS)
def test_write_dispatches_every_declared_format(format):
    result = write(_decoded(), format)
    assert result.format == format
    assert result.text.strip()


def test_write_rejects_an_unknown_format():
    with pytest.raises(ValueError, match="unknown output format"):
        write(_decoded(), "mzxml")


@pytest.mark.parametrize("text", ["BEGIN IONS\n100 1\n", "END IONS\n"])
def test_malformed_mgf_is_rejected(text):
    with pytest.raises(ValueError):
        read_mgf(text)


def test_mgf_peak_lines_must_be_numeric():
    with pytest.raises(ValueError, match="line 3"):
        read_mgf("BEGIN IONS\nTITLE=x\nnot a peak\nEND IONS\n")


def test_scan_level_instrument_alone_sets_the_run_default():
    """defaultInstrumentConfigurationRef is required even when only a scan names an instrument."""
    import xml.etree.ElementTree as ET

    spectrum = InlineSpectrum(
        default_array_length=1,
        mz=np.array([100.0]),
        intensity=np.array([1.0]),
        scans=[SpectrlScan(acquisition={"instrument": {"id": "IC1"}})],
    )
    root = ET.fromstring(write_mzml(decode_token(encode_spectrum(spectrum, lossless=True))).text)
    run = next(node for node in root.iter() if node.tag.endswith("run"))
    assert run.get("defaultInstrumentConfigurationRef") == "IC1"
