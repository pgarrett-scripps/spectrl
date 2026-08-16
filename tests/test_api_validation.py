"""Encode-side validation and API edge cases (0.3.0 fixes)."""

import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum, to_query, top_n
from spectrl.model import InlineSpectrum, SpectrlCvParam


def _spec(**kw) -> InlineSpectrum:
    base = dict(
        default_array_length=3,
        mz=np.array([100.0, 200.0, 300.0]),
        intensity=np.array([1e4, 2e4, 3e4]),
    )
    base.update(kw)
    return InlineSpectrum(**base)


# ── array-length validation ──────────────────────────────────────────────────


def test_mismatched_array_lengths_rejected():
    with pytest.raises(ValueError, match="length"):
        encode_spectrum(_spec(intensity=np.array([1e4, 2e4])))  # shorter
    with pytest.raises(ValueError, match="length"):
        encode_spectrum(_spec(intensity=np.array([1e4, 2e4, 3e4, 4e4])))  # longer


def test_wrong_default_array_length_rejected():
    with pytest.raises(ValueError, match="default_array_length"):
        encode_spectrum(_spec(default_array_length=5))


@pytest.mark.parametrize("bad_length", [-1, 1.5, True, 4_000_001])
def test_invalid_default_array_length_rejected_without_arrays(bad_length):
    with pytest.raises(ValueError, match="default_array_length"):
        encode_spectrum(InlineSpectrum(default_array_length=bad_length))


def test_mismatched_extra_array_rejected():
    with pytest.raises(ValueError, match="length"):
        encode_spectrum(_spec(extra_arrays={"snr": np.array([1.0, 2.0])}))


def test_numpy_integer_scalar_length_is_coerced():
    spec = _spec(default_array_length=np.int64(3))
    decoded = decode_token(encode_spectrum(spec))
    assert decoded.default_array_length == 3


# ── top_n ────────────────────────────────────────────────────────────────────


def test_top_n_zero_returns_empty_spectrum():
    trimmed = top_n(_spec(), 0)
    assert trimmed.default_array_length == 0
    assert len(trimmed.mz) == 0
    assert len(trimmed.intensity) == 0
    decoded = decode_token(encode_spectrum(trimmed))
    assert decoded.default_array_length == 0


def test_top_n_negative_raises():
    with pytest.raises(ValueError):
        top_n(_spec(), -1)


# ── exotic accessions ────────────────────────────────────────────────────────


def test_non_numeric_accession_tail_roundtrips_as_string_key():
    spec = _spec(params=[SpectrlCvParam(accession="NCIT:C25330", value=7)])
    decoded = decode_token(encode_spectrum(spec))
    assert decoded.params[0].accession == "NCIT:C25330"
    assert decoded.params[0].value == 7


def test_non_seven_digit_unit_roundtrips():
    spec = _spec(
        params=[SpectrlCvParam(accession="MS:1000045", value=27.0, unit_accession="MOD:00046")],
    )
    decoded = decode_token(encode_spectrum(spec))
    assert decoded.params[0].unit_accession == "MOD:00046"


def test_duplicate_accession_rejected():
    spec = _spec(
        params=[
            SpectrlCvParam(accession="MS:1000511", value=1),
            SpectrlCvParam(accession="MS:1000511", value=2),
        ]
    )
    with pytest.raises(ValueError, match="duplicate"):
        encode_spectrum(spec)


# ── dtype preservation ───────────────────────────────────────────────────────


def test_int64_extra_array_rejected_not_downcast():
    with pytest.raises(ValueError, match="dtype"):
        encode_spectrum(_spec(extra_arrays={"big": np.array([1, 2, 2**60], dtype=np.int64)}))


def test_uint16_extra_array_preserved_as_int32():
    spec = _spec(extra_arrays={"flags": np.array([1, 2, 3], dtype=np.uint16)})
    decoded = decode_token(encode_spectrum(spec))
    assert decoded.extra_arrays["flags"].dtype == np.int32
    np.testing.assert_array_equal(decoded.extra_arrays["flags"], [1, 2, 3])


# ── URL bindings ─────────────────────────────────────────────────────────────


def test_to_query_preserves_existing_params():
    token = encode_spectrum(_spec())
    url = to_query(token, "https://viewer.example.com/spectrum?keep=1&x=a+b")
    assert "keep=1" in url
    assert f"d={token}" in url


def test_to_query_replaces_same_param():
    token = encode_spectrum(_spec())
    url = to_query(token, "https://viewer.example.com/spectrum?d=old")
    assert "d=old" not in url
    assert url.count("d=") == 1
