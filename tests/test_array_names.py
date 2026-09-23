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


@pytest.mark.parametrize("name", ["MS:1000517", "MS:1000514", "MS:1000786", "MS:1", "UO:0000001", "NCIT:C1"])
@pytest.mark.parametrize("order", ["alone", "first", "last"])
def test_accession_shaped_custom_names_are_rejected_before_array_decoding(name, order):
    doc, _ = read_token_document(encode_spectrum(InlineSpectrum(1, mz=[11]), lossless=True))
    standard = {**doc[6][0], 1: 1000517}
    custom = {**doc[6][0], 1: 1000786, 4: name}
    doc[6] = [custom] if order == "alone" else [custom, standard] if order == "first" else [standard, custom]
    token = frame_payload(cbor2.dumps(doc, canonical=True))
    for reader in (read_token_document, inspect_token, decode_token):
        with pytest.raises(ValueError, match="non-standard array name"):
            reader(token)


@pytest.mark.parametrize(
    "name",
    [
        "__proto__",
        "constructor",
        "toString",
        "0",
        "01",
        "score: mean",
        "é",
        "🧪",
        "MS:1000517\n",
        "MS:１０００５１７",
        "MS:١٠٠٠٥١٧",
    ],
)
def test_custom_names_preserve_values_and_metadata_across_reencoding(name):
    spec = InlineSpectrum(2, mz=[2, 1], extra_arrays={name: np.array([-0.0, 7], dtype=np.float32)})
    decoded = decode_token(encode_spectrum(spec, lossless=True))
    restored = spectrum_from_dict(spectrum_to_dict(decoded))
    again = decode_token(encode_spectrum(restored, lossless=True))
    assert again.extra_arrays[name].tobytes() == decoded.extra_arrays[name].tobytes()
    assert again.array_names == decoded.array_names
