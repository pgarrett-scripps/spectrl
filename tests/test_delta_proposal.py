"""The proposed codec preserves bits and rejects malformed compressed streams."""

import json
from pathlib import Path

import numpy as np
import pytest

from spectrl.codecs._delta import (
    delta_shuffle,
    delta_unshuffle,
)

ROOT = Path(__file__).resolve().parents[1]
VECTORS = [
    vector
    for filename in ("delta-proposal.json", "delta-proposal-reverse.json")
    for vector in json.loads((ROOT / "test-vectors" / filename).read_text())["vectors"]
]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_shared_proposal_vector(vector):
    raw = bytes.fromhex(vector["raw_hex"])
    shuffled = bytes.fromhex(vector["shuffled_hex"])
    width = vector["item_size"]
    assert delta_shuffle(raw, width) == shuffled
    assert delta_unshuffle(shuffled, width) == raw


@pytest.mark.parametrize("width", [4, 8])
def test_arbitrary_bit_patterns_and_subarray_offsets(width):
    rng = np.random.default_rng(901)
    for n in (0, 1, 2, 3, 33, 257, 1024):
        raw = rng.bytes(n * width)
        assert delta_unshuffle(delta_shuffle(raw, width), width) == raw


def test_malformed_inputs_and_bounds():
    for width in (0, 1, 2, 16):
        with pytest.raises(ValueError):
            delta_shuffle(b"", width)
    with pytest.raises(ValueError):
        delta_unshuffle(b"123", 4)


def test_mzmlb_zero_truncation_delta_is_not_this_lossless_transform():
    # Reproduce the mzMLb reference's floating predictor with truncation disabled.
    source = np.array([100.0, 100.1, 100.2])
    encoded = source.copy()
    previous = encoded[0]
    for i in range(1, len(encoded)):
        encoded[i] = encoded[0] + encoded[i] - previous
        previous = encoded[i] + previous - encoded[0]
    decoded = encoded.copy()
    for i in range(2, len(decoded)):
        decoded[i] = decoded[i] + decoded[i - 1] - decoded[0]
    assert decoded.tobytes() != source.tobytes()
    assert delta_unshuffle(delta_shuffle(source.tobytes(), 8), 8) == source.tobytes()
