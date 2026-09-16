"""Application budgets reject work before array decompression."""

import dataclasses

import numpy as np
import pytest

from spectrl import DecodeLimits, InlineSpectrum, SpectrlDecodeError, decode_token, encode_spectrum
from spectrl.cbor_format import read_token_document


@pytest.fixture
def token():
    return encode_spectrum(
        InlineSpectrum(
            2,
            mz=[100, 200],
            intensity=[1, 2],
            extra_arrays={"score": np.array([1, 2], np.float32), "index": np.array([0, 1], np.int32)},
        ),
        lossless=True,
    )


def test_exact_budgets_include_all_arrays_and_preserve_dtypes(token):
    limits = DecodeLimits(max_token_bytes=len(token), max_peaks=2, max_arrays=4, max_decoded_bytes=48)
    decoded = decode_token(token, limits=limits)
    assert decoded.extra_arrays["score"].dtype == np.float32
    assert decoded.extra_arrays["index"].dtype == np.int32
    for field in dataclasses.fields(limits):
        too_small = dataclasses.replace(limits, **{field.name: getattr(limits, field.name) - 1})
        with pytest.raises(SpectrlDecodeError, match=field.name):
            decode_token(token, limits=too_small)


def test_aggregate_budget_is_checked_before_any_codec(token, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("a codec was called before checking all descriptors")

    monkeypatch.setattr("spectrl.cbor_format.get_codec", forbidden)
    monkeypatch.setattr("spectrl.cbor_format._validate_numpress_fp", forbidden)
    with pytest.raises(SpectrlDecodeError, match="max_decoded_bytes"):
        decode_token(token, limits=DecodeLimits(max_decoded_bytes=47))


def test_token_limit_precedes_cbor_parsing(token, monkeypatch):
    monkeypatch.setattr("spectrl.cbor_format.b64url_decode", lambda _: pytest.fail("decoded oversized token"))
    with pytest.raises(SpectrlDecodeError, match="max_token_bytes"):
        decode_token(token, limits=DecodeLimits(max_token_bytes=0))


def test_peak_and_array_limits_apply_to_metadata_only_and_empty_arrays():
    token = encode_spectrum(InlineSpectrum(100))
    with pytest.raises(SpectrlDecodeError, match="max_peaks"):
        decode_token(token, limits=DecodeLimits(max_peaks=99))
    empty = encode_spectrum(InlineSpectrum(0, extra_arrays={f"a{i}": np.array([]) for i in range(65)}))
    assert len(decode_token(empty).extra_arrays) == 65
    with pytest.raises(SpectrlDecodeError, match="max_arrays"):
        decode_token(empty, limits=DecodeLimits())
    assert len(decode_token(empty, limits=DecodeLimits(max_arrays=65, max_decoded_bytes=0)).extra_arrays) == 65
    no_arrays = encode_spectrum(InlineSpectrum(0))
    assert decode_token(no_arrays, limits=DecodeLimits(max_peaks=0, max_arrays=0, max_decoded_bytes=0))


def test_numpress_is_budgeted_as_decoded_float64():
    token = encode_spectrum(InlineSpectrum(2, mz=[100, 200], intensity=[1, 2]))
    assert decode_token(token, limits=DecodeLimits(max_decoded_bytes=32))
    with pytest.raises(SpectrlDecodeError, match="max_decoded_bytes"):
        decode_token(token, limits=DecodeLimits(max_decoded_bytes=31))


@pytest.mark.parametrize("value", [-1, True, 1.5, float("nan"), float("inf"), "10", 2**53, None])
@pytest.mark.parametrize("field", [f.name for f in dataclasses.fields(DecodeLimits)])
def test_invalid_configuration(field, value):
    with pytest.raises(ValueError, match=field):
        DecodeLimits(**{field: value})


def test_limits_do_not_replace_wire_validation(token):
    from spectrl.cbor_format import _canonical, token_checksum
    from spectrl.token import b64url_encode

    doc, _ = read_token_document(token)
    doc[0] = 4_000_001
    body = "spectrl.v2." + b64url_encode(_canonical(doc))
    with pytest.raises(SpectrlDecodeError, match="invalid declared array length"):
        decode_token(body + "." + token_checksum(body), limits=DecodeLimits(max_peaks=10_000_000))
