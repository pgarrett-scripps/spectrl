"""V3 pipeline dispatch, native representations, context, and extension boundaries."""

import dataclasses
import json
import uuid

import cbor2
import numpy as np
import pytest

from spectrl import (
    Encoding,
    InlineSpectrum,
    decode_token,
    encode_spectrum,
    register_encoding,
    spectrum_from_dict,
    spectrum_to_dict,
)
from spectrl.cbor_format import read_token_document, token_checksum
from spectrl.context import register_extension
from spectrl.introspection import inspect_token
from spectrl.model import SpectrlCvParam, SpectrlScan, SpectrlScanWindow, SpectrlUserParam
from spectrl.peaks import top_n
from spectrl.pipeline import ENCODINGS
from spectrl.token import b64url_encode


def frame(doc):
    body = "spectrl.v3.r." + b64url_encode(cbor2.dumps(doc, canonical=True))
    return body + "." + token_checksum(body)


@pytest.mark.parametrize("dtype", ["float32", "float64", "int32"])
@pytest.mark.parametrize(
    "codec",
    ["raw", "byte-shuffle", "modular-delta-shuffle"],
)
def test_native_representations(dtype, codec):
    a = np.array([0, 0, 1, 1, 2, 65536], dtype=dtype)
    if dtype.startswith("float"):
        a[0] = -0.0
    s = InlineSpectrum(len(a), mz=a, intensity=a.copy(), extra_arrays={"custom": a.copy()})
    d = decode_token(
        encode_spectrum(s, lossless=True, array_encodings=dict.fromkeys(["mz", "intensity", "custom"], codec))
    )
    for b in (d.mz, d.intensity, d.extra_arrays["custom"]):
        assert b.dtype == a.dtype
        assert b.tobytes() == a.tobytes()
    restored = spectrum_from_dict(json.loads(json.dumps(spectrum_to_dict(d))))
    assert restored.mz.dtype == a.dtype
    assert restored.mz.tobytes() == a.tobytes()


def test_custom_operations_inspection_and_explicit_registration():
    eid = "test:encoding-" + uuid.uuid4().hex
    raw = ENCODINGS[0, 1]
    register_encoding(eid, Encoding(raw.encode, raw.decode, raw.validate))
    s = InlineSpectrum(2, mz=np.array([1, 2], dtype="float32"))
    token = encode_spectrum(s, lossless=True, array_encodings={"mz": {"encoding": eid}})
    assert decode_token(token).mz.tobytes() == s.mz.tobytes()
    doc, _ = read_token_document(token)
    doc[6][0][2] = ["unknown:encoding", 2, {"mode": "x"}]
    unknown = frame(doc)
    assert inspect_token(unknown)[0]["available"] is False
    with pytest.raises(ValueError, match="unsupported operation"):
        decode_token(unknown)
    with pytest.raises(ValueError, match="already registered"):
        register_encoding(eid, raw)


def test_context_repeated_params_and_nested_users():
    params = [SpectrlCvParam("MS:1000511", "2"), SpectrlCvParam("MS:1000511", "3")]
    user = [SpectrlUserParam("note", "window")]
    s = InlineSpectrum(
        2,
        mz=np.array([1, 2], dtype="float32"),
        params=params,
        scans=[SpectrlScan(windows=[SpectrlScanWindow(params=params, user_params=user)])],
        source={"name": "run.raw", "external_ids": ["example:run"]},
        acquisition={"instrument": {"id": "IC1", "components": [{"kind": "analyzer", "order": 1, "params": params}]}},
        processing=[
            {
                "operation": "example:centroid",
                "revision": 1,
                "parameters": {"method": "x"},
                "software": {"name": "example", "version": "1"},
            }
        ],
        array_params={"mz": params},
        array_user_params={"mz": user},
    )
    d = decode_token(encode_spectrum(s, lossless=True))
    assert d.params == params
    assert d.scans == s.scans
    assert d.source == s.source
    assert d.acquisition == s.acquisition
    assert d.processing == s.processing
    assert d.array_params == s.array_params
    assert spectrum_to_dict(spectrum_from_dict(spectrum_to_dict(d))) == spectrum_to_dict(d)
    stripped = decode_token(encode_spectrum(s, lossless=True, drop_user_params=True))
    assert stripped.scans[0].windows[0].user_params == []
    assert stripped.array_user_params == {}
    assert stripped.processing[-1]["parameters"]["userParamsRemoved"] == 2


def test_extension_boundaries_and_array_changes():
    ext = {"test:optional": {"revision": 1, "required": False, "data": {"value": [1, 2]}}}
    s = InlineSpectrum(2, mz=[1, 2], intensity=[3, 4], extensions=ext)
    d = decode_token(encode_spectrum(s, lossless=True))
    assert d.extensions == ext
    with pytest.raises(ValueError, match="extensions"):
        top_n(s, 1)
    with pytest.raises(ValueError, match="extensions"):
        encode_spectrum(dataclasses.replace(s, mz=np.array([2.0, 1.0])))
    required = {"test:required": {"revision": 1, "required": True, "data": 4}}
    t = encode_spectrum(dataclasses.replace(s, extensions=required), lossless=True)
    assert read_token_document(t)[1].extensions == required
    with pytest.raises(ValueError, match="unsupported required"):
        decode_token(t)
    register_extension("test:required", lambda data: None)
    assert decode_token(t).extensions == required


def test_trimming_scopes_source_summaries_and_lossy_history_survives_reencoding():
    s = InlineSpectrum(3, mz=[1, 2, 3], intensity=[1, 2, 3], params=[SpectrlCvParam("MS:1000285", 6)])
    selected = top_n(s, 1)
    assert selected.params == []
    assert selected.processing[-1]["source_params"] == s.params
    d = decode_token(encode_spectrum(s))
    assert d.array_processing["mz"][-1]["operation"] == "spectrl:lossy-encoding"
    again = decode_token(encode_spectrum(d, lossless=True))
    assert again.array_processing == d.array_processing


@pytest.mark.parametrize(
    "key,value", [(2, ["unknown:x", 0]), (3, [1, 1, {"invalid": 0}]), (7, 1), (11, {"bad": {}}), (8, [[1000523, None]])]
)
def test_descriptor_contract_rejection(key, value):
    doc, _ = read_token_document(encode_spectrum(InlineSpectrum(1, mz=[1]), lossless=True))
    doc[6][0][key] = value
    with pytest.raises(ValueError):
        decode_token(frame(doc))


def test_mzml_resolves_run_context_and_native_intensity():
    from mzmlpy import Mzml

    from spectrl import from_mzmlpy

    with Mzml("tests/data/example.mzML") as run:
        s = from_mzmlpy(run.spectra[0], run=run)
        assert s.acquisition["instrument"]["components"]
        assert s.source["name"]
        assert s.processing
        assert s.scans and s.params
        d = decode_token(encode_spectrum(s, lossless=True))
        assert d.scans == s.scans
        assert d.params == s.params
        assert d.intensity.dtype == s.intensity.dtype
        assert d.intensity.tobytes() == s.intensity.tobytes()


def test_json_preserves_opaque_bytes_and_map_keys():
    import json

    payload = {0: b"\x00\xff", "nested": {"$spectrl": "bytes", "hex": "literal"}}
    spec = InlineSpectrum(1, mz=[1], extensions={"test:opaque": {"revision": 1, "required": False, "data": payload}})
    restored = spectrum_from_dict(json.loads(json.dumps(spectrum_to_dict(spec))))
    assert restored.extensions == spec.extensions
    assert decode_token(encode_spectrum(restored, lossless=True)).extensions == spec.extensions


@pytest.mark.parametrize("dtype,accession", [("float32", "MS:1000521"), ("int32", "MS:1000519")])
def test_mzml_declared_width_matches_binary_bytes(dtype, accession):
    import base64
    import xml.etree.ElementTree as ET

    from mzmlpy.spectra import Spectrum

    from spectrl import from_mzmlpy

    values = np.array([1, 2, 3], dtype=dtype)
    binary = base64.b64encode(values.tobytes()).decode()
    xml = f'''<spectrum id="scan=1" defaultArrayLength="3"><binaryDataArrayList count="1">
<binaryDataArray encodedLength="{len(binary)}">
<cvParam accession="MS:1000514"/>
<cvParam accession="{accession}"/>
<cvParam accession="MS:1000576"/>
<binary>{binary}</binary></binaryDataArray></binaryDataArrayList></spectrum>'''
    xml = xml.replace("<cvParam ", '<cvParam cvRef="MS" name="test" ')
    source = from_mzmlpy(Spectrum(ET.fromstring(xml)))
    assert source.mz.dtype == values.dtype
    assert source.mz.tobytes() == values.tobytes()
    decoded = decode_token(encode_spectrum(source, lossless=True))
    assert decoded.mz.dtype == values.dtype
    assert decoded.mz.tobytes() == values.tobytes()


def test_cv_versions_round_trip_and_stay_absent_when_unset():
    spec = InlineSpectrum(default_array_length=0, cv_versions={"MS": "4.1.142", "UO": "releases/2020-03-10"})
    token = encode_spectrum(spec)
    assert read_token_document(token)[0][12] == {"MS": "4.1.142", "UO": "releases/2020-03-10"}
    assert decode_token(token).cv_versions == spec.cv_versions
    bare = encode_spectrum(InlineSpectrum(default_array_length=0))
    assert 12 not in read_token_document(bare)[0]
    assert decode_token(bare).cv_versions == {}


def test_cv_versions_survive_json_round_trip():
    spec = InlineSpectrum(default_array_length=0, cv_versions={"MS": "4.1.142"})
    assert spectrum_from_dict(spectrum_to_dict(spec)).cv_versions == {"MS": "4.1.142"}


@pytest.mark.parametrize(
    "versions",
    [
        {"MS:": "4.1.142"},  # a prefix, never a whole accession
        {"PSI-MS": "4.1.142"},  # mzML's <cv> @id spelling is not a prefix
        {"": "4.1.142"},
        {"1MS": "4.1.142"},
        {"MS": ""},
        {"MS": 4.1},
    ],
)
def test_cv_versions_reject_malformed_entries(versions):
    with pytest.raises(ValueError):
        encode_spectrum(InlineSpectrum(default_array_length=0, cv_versions=versions))


def test_cv_versions_are_provenance_not_a_decode_gate():
    """An unrecognized release decodes normally; the accession is the identifier."""
    spec = InlineSpectrum(default_array_length=0, cv_versions={"MS": "99.99.99-unreleased"})
    assert decode_token(encode_spectrum(spec)).cv_versions == {"MS": "99.99.99-unreleased"}


def test_cv_versions_come_from_the_mzml_cv_list():
    from mzmlpy import Mzml

    from spectrl import from_mzmlpy

    with Mzml("tests/data/example.mzML") as run:
        spec = from_mzmlpy(run.spectra[0], run=run)
    # example.mzML declares <cv id="MS" version="2.26.0"> and a UO release.
    assert spec.cv_versions["MS"] == "2.26.0"
    assert set(spec.cv_versions) <= {"MS", "UO"}
    assert decode_token(encode_spectrum(spec)).cv_versions == spec.cv_versions


def test_cv_list_id_spellings_fold_onto_the_accession_prefix():
    from spectrl.mzml_context import cv_prefix

    assert cv_prefix("MS") == "MS"
    assert cv_prefix("PSI-MS") == "MS"
    assert cv_prefix("UNIT-ONTOLOGY") == "UO"
    assert cv_prefix("NCIT") == "NCIT"
    assert cv_prefix("not a prefix") is None
    assert cv_prefix(None) is None
