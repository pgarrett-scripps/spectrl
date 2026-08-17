"""Acceptance criterion 7: No accession is hardcoded; all resolve via CV binding."""

from mzmlpy.constants import (
    BinaryDataArrayAccession,
    BinaryDataTypeAccession,
    CompressionTypeAccessions,
    ScanPolarity,
)

from spectrl import ArrayAccession
from spectrl.cv import (
    ARRAY_CHARGE,
    ARRAY_INTENSITY,
    ARRAY_MZ,
    COMP_BYTE_SHUFFLED_ZSTD,
    COMP_NUMLIN_ZLIB,
    COMP_NUMLIN_ZSTD,
    COMP_NUMPIC_ZLIB,
    COMP_NUMPIC_ZSTD,
    COMP_NUMSLOF_ZLIB,
    COMP_NUMSLOF_ZSTD,
    COMP_ZLIB,
    COMP_ZSTD,
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
    assert COMP_NUMLIN_ZLIB == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZLIB)
    assert COMP_NUMSLOF_ZLIB == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZLIB)
    assert COMP_NUMPIC_ZLIB == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZLIB)
    assert COMP_ZLIB == accession_tail(CompressionTypeAccessions.ZLIB_COMPRESSION)
    assert COMP_ZSTD == accession_tail(CompressionTypeAccessions.ZSTD_COMPRESSION)
    assert COMP_BYTE_SHUFFLED_ZSTD == accession_tail(CompressionTypeAccessions.BYTE_SHUFFLED_ZSTD)
    assert COMP_NUMLIN_ZSTD == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZSTD)
    assert COMP_NUMPIC_ZSTD == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZSTD)
    assert COMP_NUMSLOF_ZSTD == accession_tail(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZSTD)


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


def test_no_hardcoded_integers_in_codecs():
    """Codec registry keys match mzmlpy enum tails, not bare integer literals."""
    from spectrl.codecs import _REGISTRY

    expected_keys = {
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZLIB),
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZLIB),
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZLIB),
        accession_tail(CompressionTypeAccessions.ZLIB_COMPRESSION),
        accession_tail(CompressionTypeAccessions.ZSTD_COMPRESSION),
        accession_tail(CompressionTypeAccessions.BYTE_SHUFFLED_ZSTD),
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_LINEAR_PREDICTION_ZSTD),
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_POSITIVE_INTEGER_ZSTD),
        accession_tail(CompressionTypeAccessions.MS_NUMPRESS_SHORT_LOGGED_FLOAT_ZSTD),
    }
    assert set(_REGISTRY.keys()) == expected_keys


def test_polarity_flags_are_accessions():
    """Polarity constants are proper StrEnum accessions."""
    assert ScanPolarity.POSITIVE.startswith("MS:")
    assert ScanPolarity.NEGATIVE.startswith("MS:")
    assert accession_tail(ScanPolarity.POSITIVE) > 0
    assert accession_tail(ScanPolarity.NEGATIVE) > 0
