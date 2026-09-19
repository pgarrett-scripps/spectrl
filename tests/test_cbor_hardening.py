"""Reject ambiguous or unsupported CBOR before metadata or extension parsing."""

import json
from pathlib import Path

import pytest

from spectrl import SpectrlDecodeError, decode_token
from spectrl.cbor_format import frame_payload
from spectrl.introspection import inspect_token

CASES = json.loads((Path(__file__).parents[1] / "test-vectors/cbor-hardening.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
@pytest.mark.parametrize("reader", [decode_token, inspect_token])
def test_malformed_cbor_is_rejected(case, reader):
    token = frame_payload(bytes.fromhex(case["hex"]))
    with pytest.raises(SpectrlDecodeError):
        reader(token)
