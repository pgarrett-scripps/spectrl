"""Acceptance criterion 7: No accession is hardcoded; all resolve via CV binding."""

from mzmlpy.constants import (
    BinaryDataArrayAccession,
    BinaryDataTypeAccession,
    ScanPolarity,
)

from spectrl import ArrayAccession
from spectrl.cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    ION_MOBILITY_ARRAY_TAILS,
    TYPE_FLOAT64,
    accession_tail,
    decode_tail,
    decode_unit_tail,
    encode_unit,
)


def test_all_cv_constants_resolve():
    """Every spectrl cv constant equals the tail of its source StrEnum value."""
    assert ARRAY_MZ == accession_tail(BinaryDataArrayAccession.MZ)
    assert ARRAY_INTENSITY == accession_tail(BinaryDataArrayAccession.INTENSITY)
    assert ARRAY_CHARGE == accession_tail(BinaryDataArrayAccession.CHARGE)
    assert TYPE_FLOAT64 == accession_tail(BinaryDataTypeAccession.FLOAT_64)


def test_generated_array_accessions_match_wire_constants():
    assert ArrayAccession.MZ == "MS:1000514"
    assert ArrayAccession.INTENSITY == "MS:1000515"
    assert ArrayAccession.CHARGE == "MS:1000516"
    assert set(ION_MOBILITY_ARRAY_TAILS.values()) == {
        accession_tail(accession) for accession in ArrayAccession if "ION_MOBILITY" in accession.name
    }


def test_tail_roundtrip():
    """accession_tail + decode_tail roundtrips for MS: ontology."""
    for acc in BinaryDataArrayAccession:
        tail = accession_tail(str(acc))
        reconstructed = decode_tail(tail)
        assert reconstructed == str(acc), f"{acc}: {reconstructed} != {acc}"


def test_unit_tail_roundtrip():
    """UO: unit accessions roundtrip through encode_unit/decode_unit_tail."""
    uo_accession = "UO:0000031"
    encoded = encode_unit(uo_accession)
    assert isinstance(encoded, int)
    decoded = decode_unit_tail(encoded)
    assert decoded == uo_accession


def test_non_uo_unit_tail_uses_list():
    """Non-UO unit accessions use the [ontology, tail] list form."""
    ms_accession = "MS:1000045"
    encoded = encode_unit(ms_accession)
    assert isinstance(encoded, list)
    assert encoded[0] == "MS"
    decoded = decode_unit_tail(encoded)
    assert decoded == ms_accession


def test_polarity_flags_are_accessions():
    """Polarity constants are proper StrEnum accessions."""
    assert ScanPolarity.POSITIVE.startswith("MS:")
    assert ScanPolarity.NEGATIVE.startswith("MS:")
    assert accession_tail(ScanPolarity.POSITIVE) > 0
    assert accession_tail(ScanPolarity.NEGATIVE) > 0
