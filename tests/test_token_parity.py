"""Canonical writer regression vectors shared with JavaScript."""

import copy
import json
import math
from pathlib import Path

import cbor2
import numpy as np
import pytest

from spectrl import InlineSpectrum, decode_token, encode_spectrum, spectrum_from_dict
from spectrl.cbor_format import _canonical
from spectrl.model import SpectrlUserParam

ROOT = Path(__file__).resolve().parents[1]
INPUTS = json.loads((ROOT / "test-vectors/token-parity-inputs.json").read_text(encoding="utf-8"))
TOKENS = json.loads((ROOT / "test-vectors/token-parity.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", INPUTS, ids=lambda case: case["name"])
@pytest.mark.parametrize("lossless", [True, False])
def test_complete_raw_token_matches_shared_vector(case, lossless):
    spec = spectrum_from_dict(copy.deepcopy(case["spec"]))
    token = encode_spectrum(spec, lossless=lossless, compression="raw")
    assert token == TOKENS[case["name"]]["lossless" if lossless else "lossy"]


@pytest.mark.parametrize("value", [0.0, -0.0, 2.0, -2.0, float(2**32), float(2**53 - 1), -float(2**53 - 1)])
def test_whole_metadata_numbers_have_one_integer_representation(value):
    spec = InlineSpectrum(0, user_params=[SpectrlUserParam("number", value)])
    integer = InlineSpectrum(0, user_params=[SpectrlUserParam("number", int(value))])
    assert encode_spectrum(spec) == encode_spectrum(integer)
    actual = decode_token(encode_spectrum(spec)).user_params[0].value
    assert type(actual) is int and actual == value


def test_normalization_is_recursive_without_mutating_or_changing_binary_arrays():
    payload = {0: [2.0, {"zero": -0.0, "flag": True, "text": "2.0", "fraction": 1.5}], 1: b"\xfb"}
    decoded = cbor2.loads(_canonical(payload))
    assert type(decoded[0][0]) is int
    assert type(decoded[0][1]["zero"]) is int
    assert decoded[0][1]["flag"] is True
    assert decoded[0][1]["text"] == "2.0"
    assert decoded[0][1]["fraction"] == 1.5
    assert decoded[1] == b"\xfb"
    assert type(payload[0][0]) is float
    assert math.copysign(1, payload[0][1]["zero"]) == -1
    spectrum = InlineSpectrum(2, mz=np.array([0.0, -0.0]), intensity=np.array([-0.0, 0.0]))
    result = decode_token(encode_spectrum(spectrum, lossless=True))
    assert result.mz.tobytes() == spectrum.mz.tobytes()
    assert result.intensity.tobytes() == spectrum.intensity.tobytes()


def test_large_float_stays_float_and_fractional_precision_is_preserved():
    for value in [1e20, 1.5, 0.1, math.ulp(0.0)]:
        decoded = cbor2.loads(_canonical({0: value}))[0]
        assert type(decoded) is float and decoded == value
