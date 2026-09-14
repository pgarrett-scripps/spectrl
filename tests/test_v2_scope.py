"""Version boundaries must never silently reinterpret identification data."""

import json
from pathlib import Path

import cbor2
import numpy as np
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, spectrum_from_dict
from spectrl.cbor_format import token_checksum
from spectrl.legacy import decode_v1_token
from spectrl.token import b64url_encode

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("value", [None, "PEPTIDE", 0, {}, []])
def test_reserved_identification_key_rejected(value):
    body = "spectrl.v2." + b64url_encode(cbor2.dumps({0: 0, 7: value}))
    with pytest.raises(ValueError, match="reserved"):
        decode_token(body + "." + token_checksum(body))


def test_identification_inputs_are_not_silently_discarded():
    with pytest.raises(TypeError):
        InlineSpectrum(default_array_length=0, interp="PEPTIDE")
    with pytest.raises(ValueError, match="identification"):
        spectrum_from_dict({"default_array_length": 0, "interp": "PEPTIDE"})
    decoded = decode_token(encode_spectrum(InlineSpectrum(default_array_length=0)))
    assert decoded.format_version == 2
    assert not hasattr(decoded, "interp")
    with pytest.raises(ValueError):
        decode_v1_token(encode_spectrum(InlineSpectrum(default_array_length=0)))


@pytest.mark.parametrize("filename", ["vectors.json", "reverse-vectors.json"])
def test_archived_v1_tokens_require_explicit_legacy_decoder(filename):
    vectors = json.loads((ROOT / "test-vectors/v1" / filename).read_text())["vectors"]
    for vector in vectors:
        with pytest.raises(ValueError):
            decode_token(vector["token"])
        legacy = decode_v1_token(vector["token"])
        expected = vector["decoded"]
        assert legacy.interpretation == expected["interp"]
        assert legacy.spectrum.format_version == 1
        assert not hasattr(legacy.spectrum, "interp")
        migrated = decode_token(encode_spectrum(legacy.spectrum, lossless=True))
        assert migrated.format_version == 2
        assert migrated.params == legacy.spectrum.params
        assert migrated.precursors == legacy.spectrum.precursors
        assert migrated.user_params == legacy.spectrum.user_params
        for name in ("mz", "intensity", "charge"):
            actual = getattr(legacy.spectrum, name)
            if expected[name] is None:
                assert actual is None
            else:
                np.testing.assert_allclose(actual, expected[name], rtol=1e-6, atol=1e-6)
                np.testing.assert_array_equal(getattr(migrated, name), actual)
        corrupted = vector["token"][:-1] + ("0" if vector["token"][-1] != "0" else "1")
        with pytest.raises(ValueError, match="checksum"):
            decode_v1_token(corrupted)
