"""Optional names preserve array identity and survive re-encoding."""

import cbor2
import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum, spectrum_from_dict, spectrum_to_dict
from spectrl.cbor_format import frame_payload, read_token_document
from spectrl.introspection import inspect_token
from spectrl.model import InlineSpectrum
from spectrl.peaks import top_n


def test_names_survive_sorting_selection_json_and_reencoding():
    names = {"mz": "Measured m/z", "intensity": "Signal", "MS:1000517": "Signal", "score": "score"}
    spec = InlineSpectrum(
        2,
        mz=[200, 100],
        intensity=[10, 20],
        extra_arrays={"MS:1000517": np.array([2.0, 3.0]), "score": np.array([0.8, 0.9])},
        array_names=names,
    )
    token = encode_spectrum(spec, lossless=True)
    decoded = decode_token(token)
    assert decoded.array_names == names
    np.testing.assert_array_equal(decoded.mz, [100, 200])
    np.testing.assert_array_equal(decoded.extra_arrays["MS:1000517"], [3, 2])
    assert [a["name"] for a in inspect_token(token)] == list(names.values())
    restored = spectrum_from_dict(spectrum_to_dict(decoded))
    assert decode_token(encode_spectrum(restored, lossless=True)).array_names == names
    selected = decode_token(encode_spectrum(top_n(restored, 1), lossless=True))
    assert selected.array_names == names
    np.testing.assert_array_equal(selected.mz, [100])


@pytest.mark.parametrize("name", [None, "", 42, [], {}])
def test_invalid_names_rejected_on_input_and_wire(name):
    with pytest.raises(ValueError, match="array name"):
        encode_spectrum(InlineSpectrum(1, mz=[100], array_names={"mz": name}))
    doc, _ = read_token_document(encode_spectrum(InlineSpectrum(1, mz=[100]), lossless=True))
    doc[6][0][4] = name
    with pytest.raises(ValueError, match="array name"):
        decode_token(frame_payload(cbor2.dumps(doc, canonical=True)))


@pytest.mark.parametrize("tail", [1000514, 1000517])
def test_names_do_not_allow_duplicate_standard_arrays(tail):
    doc, _ = read_token_document(encode_spectrum(InlineSpectrum(1, mz=[100]), lossless=True))
    original = doc[6][0]
    original[1] = tail
    original[4] = "First"
    doc[6].append({**original, 4: "Second"})
    with pytest.raises(ValueError, match="duplicate array"):
        decode_token(frame_payload(cbor2.dumps(doc, canonical=True)))


def test_names_cannot_relabel_custom_identity_or_name_absent_arrays():
    with pytest.raises(ValueError, match="must match"):
        encode_spectrum(InlineSpectrum(1, extra_arrays={"score": np.array([1.0])}, array_names={"score": "other"}))
    with pytest.raises(ValueError, match="absent"):
        encode_spectrum(InlineSpectrum(1, mz=[100], array_names={"intensity": "Signal"}))


def test_standard_names_do_not_use_custom_name_restrictions():
    spec = InlineSpectrum(1, mz=[100], array_names={"mz": "mz"})
    assert decode_token(encode_spectrum(spec)).array_names == {"mz": "mz"}
