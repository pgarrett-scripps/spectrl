"""The spectrum header has exactly eight supported field identifiers."""

import cbor2
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, spectrum_from_dict
from spectrl.cbor_format import read_token_payload, token_checksum
from spectrl.model import SpectrlScan, SpectrlUserParam
from spectrl.token import b64url_encode


def _token(document, version=3):
    body = f"spectrl.v{version}.r." + b64url_encode(cbor2.dumps(document, canonical=True))
    return body + "." + token_checksum(body)


@pytest.mark.parametrize("lossless", [False, True])
def test_user_parameters_use_key_seven(lossless):
    params = [SpectrlUserParam(name="elapsed", value=3.5, type="xsd:float", unit_accession="UO:0000010")]
    source = InlineSpectrum(default_array_length=0, user_params=params, scans=[SpectrlScan(user_params=params)])
    token = encode_spectrum(source, lossless=lossless)
    document = cbor2.loads(read_token_payload(token))
    assert set(document) <= set(range(12))
    assert document[7][0]["n"] == "elapsed"
    assert document[3]["s"][0][2] == document[7]
    decoded = decode_token(token)
    assert decoded.user_params == params
    assert decoded.scans[0].user_params == params
    assert decoded.format_version == 3


def test_empty_parameters_are_omitted():
    token = encode_spectrum(InlineSpectrum(default_array_length=0))
    assert 7 not in cbor2.loads(read_token_payload(token))
    assert decode_token(token).user_params == []


@pytest.mark.parametrize("key", [12, 13, 99, -1, "7"])
@pytest.mark.parametrize("include_parameters", [False, True])
def test_unsupported_header_keys_are_rejected(key, include_parameters):
    document = {0: 0, key: [{"n": "note", "v": "value"}]}
    if include_parameters:
        document[7] = [{"n": "current", "v": "value"}]
    with pytest.raises(ValueError, match="unsupported spectrl header key"):
        decode_token(_token(document))


@pytest.mark.parametrize("value", [None, "PEPTIDE", 0, {}])
def test_user_parameters_require_an_array(value):
    with pytest.raises(ValueError, match="header key 7 must be list"):
        decode_token(_token({0: 0, 7: value}))


@pytest.mark.parametrize("version", [0, 1, 2, 99])
def test_only_the_current_format_is_accepted(version):
    with pytest.raises(ValueError, match="Not a spectrl.v3 token"):
        decode_token(_token({0: 0}, version))


def test_identification_inputs_are_not_silently_discarded():
    with pytest.raises(TypeError):
        InlineSpectrum(default_array_length=0, interp="PEPTIDE")
    with pytest.raises(ValueError, match="identification"):
        spectrum_from_dict({"default_array_length": 0, "interp": "PEPTIDE"})
