"""Accession-keyed standard arrays and ion-mobility preservation."""

import cbor2
import numpy as np
import pytest

from spectrl import ArrayAccession, decode_token, encode_spectrum
from spectrl.cv import COMP_NUMLIN_ZLIB, COMP_ZLIB, ION_MOBILITY_ARRAY_TAILS
from spectrl.header import DESC_ARRAY, DESC_COMP
from spectrl.model import InlineSpectrum
from spectrl.token import b64url_decode


def _spec(**kwargs) -> InlineSpectrum:
    return InlineSpectrum(
        default_array_length=3,
        mz=np.array([100.0, 200.0, 300.0]),
        intensity=np.array([1000.0, 2000.0, 3000.0]),
        **kwargs,
    )


def test_every_mobility_accession_round_trips_without_collision():
    arrays = {accession: np.array([i + 0.1, i + 0.2, i + 0.3]) for i, accession in enumerate(ION_MOBILITY_ARRAY_TAILS)}
    decoded = decode_token(encode_spectrum(_spec(extra_arrays=arrays)))
    assert set(decoded.extra_arrays) == set(arrays)
    assert set(decoded.mobility_arrays) == set(arrays)
    for accession, expected in arrays.items():
        np.testing.assert_allclose(decoded.extra_arrays[accession], expected, rtol=1e-6)


def test_mobility_arrays_receive_numpress_linear_default():
    token = encode_spectrum(
        _spec(extra_arrays={ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY: np.array([0.8, 0.9, 1.0])})
    )
    doc = cbor2.loads(b64url_decode(token.split(".")[2]))
    desc = next(d for d in doc[6] if d[DESC_ARRAY] == 1003008)
    assert desc[DESC_COMP] == COMP_NUMLIN_ZLIB


def test_mobility_enum_selects_its_encoding_override():
    token = encode_spectrum(
        _spec(extra_arrays={ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY: np.array([0.8, 0.9, 1.0])}),
        array_encodings={ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY: "zlib"},
    )
    doc = cbor2.loads(b64url_decode(token.split(".")[2]))
    desc = next(d for d in doc[6] if d[DESC_ARRAY] == 1003008)
    assert desc[DESC_COMP] == COMP_ZLIB


def test_core_accession_alias_matches_friendly_encoding_key():
    spec = _spec()
    by_name = encode_spectrum(spec, array_encodings={"mz": "zlib"})
    by_accession = encode_spectrum(spec, array_encodings={ArrayAccession.MZ: "zlib"})
    assert by_accession == by_name


def test_conflicting_core_aliases_are_rejected():
    with pytest.raises(ValueError, match="conflicting aliases"):
        encode_spectrum(_spec(), array_encodings={"mz": "zlib", "MS:1000514": "numlin-zlib"})


def test_core_accession_cannot_be_duplicated_as_extra_array():
    with pytest.raises(ValueError, match="core array accession"):
        encode_spectrum(_spec(extra_arrays={"MS:1000514": np.array([1.0, 2.0, 3.0])}))


def test_non_standard_accession_requires_a_free_text_key():
    with pytest.raises(ValueError, match="free-text"):
        encode_spectrum(_spec(extra_arrays={ArrayAccession.NON_STANDARD_DATA: np.array([1.0, 2.0, 3.0])}))


def test_non_ms_accession_cannot_be_misencoded_as_psi_ms_array():
    with pytest.raises(ValueError, match="PSI-MS"):
        encode_spectrum(_spec(extra_arrays={"UO:0000031": np.array([1.0, 2.0, 3.0])}))


def test_future_psi_ms_array_accession_is_preserved():
    decoded = decode_token(
        encode_spectrum(_spec(extra_arrays={"MS:1999999": np.array([1.0, 2.0, 3.0], dtype=np.float32)}))
    )
    assert decoded.extra_arrays["MS:1999999"].dtype == np.float32
