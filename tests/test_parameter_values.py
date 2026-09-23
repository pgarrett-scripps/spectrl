"""Native parameter types and the mzML-to-Spectrl conversion boundary."""

import xml.etree.ElementTree as ET
from types import SimpleNamespace

import cbor2
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, spectrum_from_dict, spectrum_to_dict
from spectrl.cbor_format import read_token_payload, token_checksum
from spectrl.model import SpectrlUserParam
from spectrl.mzml import _collect_user_params
from spectrl.mzml_context import params
from spectrl.mzml_values import user_param
from spectrl.token import b64url_encode


@pytest.mark.parametrize("value", [None, "", "2.5", 2, 2.5, 1e20, -(2**53 - 1), 2**53 - 1])
def test_native_value_and_json_roundtrip(value):
    source = InlineSpectrum(0, user_params=[SpectrlUserParam("example", value, unit_accession="UO:0000010")])
    decoded = decode_token(encode_spectrum(source))
    actual = decoded.user_params[0].value
    assert actual == value and type(actual) is type(value)
    json_value = spectrum_to_dict(decoded)
    assert json_value["user_params"] == [{"name": "example", "value": value, "unit_accession": "UO:0000010"}]
    assert spectrum_from_dict(json_value).user_params == source.user_params
    document = cbor2.loads(read_token_payload(encode_spectrum(source)))
    assert set(document[7][0]) <= {"n", "v", "u"}


@pytest.mark.parametrize("value", [True, False, [], {}, float("nan"), float("inf"), 2**53])
def test_invalid_user_values_fail_on_encode(value):
    with pytest.raises(ValueError):
        encode_spectrum(InlineSpectrum(0, user_params=[SpectrlUserParam("bad", value)]))


def test_removed_type_cannot_be_silently_accepted():
    with pytest.raises(TypeError):
        SpectrlUserParam("example", "2.5", type="xsd:float")
    with pytest.raises(TypeError):
        spectrum_from_dict({"user_params": [{"name": "example", "value": "2.5", "type": "xsd:float"}]})
    document = {0: 0, 7: [{"n": "example", "v": "2.5", "t": "xsd:float"}]}
    body = "spectrl.v3.r." + b64url_encode(cbor2.dumps(document, canonical=True))
    with pytest.raises(ValueError, match="unsupported user parameter field"):
        decode_token(body + "." + token_checksum(body))


@pytest.mark.parametrize(
    "declared,text,expected",
    [
        ("xsd:float", "2.5", 2.5),
        ("xsd:double", "1e20", 1e20),
        ("xs:double", " 1.25e2 ", 125.0),
        ("xsd:decimal", ".125", 0.125),
        ("xsd:integer", "+002", 2),
        ("xsd:positiveInteger", "1", 1),
        ("xsd:unsignedInt", "4294967295", 4294967295),
        ("xsd:string", "002.50", "002.50"),
        ("", "2.5", "2.5"),
        ("xsd:string", "", ""),
        ("", "", ""),
        ("xsd:date", "2026-09-19", "2026-09-19"),
    ],
)
def test_import_consumes_numeric_hint_at_both_entry_points(declared, text, expected):
    root = ET.Element("spectrum")
    ET.SubElement(root, "userParam", name="example", value=text, type=declared, unitAccession="UO:0000010")
    for imported in (params(root)[1], _collect_user_params(SimpleNamespace(element=root, ns=""))):
        actual = imported[0]
        assert actual.value == expected and type(actual.value) is type(expected)
        assert actual.unit_accession == "UO:0000010"
        assert not hasattr(actual, "type")
        assert decode_token(encode_spectrum(InlineSpectrum(0, user_params=imported))).user_params == imported


@pytest.mark.parametrize(
    "declared,text",
    [
        ("xsd:float", "NaN"),
        ("xsd:double", "INF"),
        ("xsd:double", "1e999"),
        ("xsd:double", "1e-999"),
        ("xsd:integer", "9007199254740992"),
        ("xsd:integer", "2.5"),
        ("xsd:float", "1_000"),
        ("xsd:float", ""),
        ("xsd:positiveInteger", "0"),
        ("xsd:unsignedInt", "-1"),
        ("xsd:byte", "128"),
        ("xsd:decimal", "1e2"),
        ("xsd:integer", "１２"),
    ],
)
def test_invalid_numeric_import_is_explicit(declared, text):
    element = ET.Element("userParam", name="example", value=text, type=declared)
    with pytest.raises(ValueError, match="invalid mzML user parameter 'example'"):
        user_param(element)


def test_missing_value_stays_null_and_groups_convert():
    group = ET.fromstring(
        '<referenceableParamGroup><userParam name="flag"/>'
        '<userParam name="n" value="2" type="xsd:int"/></referenceableParamGroup>'
    )
    root = ET.fromstring('<spectrum><referenceableParamGroupRef ref="g"/></spectrum>')
    assert [u.value for u in params(root, {"g": group})[1]] == [None, 2]
