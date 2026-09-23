"""Regressions for numeric boundaries, malformed streams and API fidelity."""

import json
import zlib

import cbor2
import numpy as np
import pytest

from spectrl import (
    InlineSpectrum,
    SpectrlDecodeError,
    decode_token,
    encode_spectrum,
    encoding_plan,
    extract_token,
    inspect_token,
    spectrum_from_dict,
    spectrum_to_dict,
    to_fragment,
)
from spectrl.cbor_format import read_token_payload, token_checksum
from spectrl.header import DESC_DATA
from spectrl.token import b64url_encode


def token_for(doc):
    body = "spectrl.v3.r." + b64url_encode(cbor2.dumps(doc, canonical=True))
    return body + "." + token_checksum(body)


@pytest.mark.parametrize("values", [[50000.0], [0, 1, 50000], [1e300]])
def test_large_mz_values_respect_default_ppm_bound(values):
    spec = InlineSpectrum(len(values), mz=values)
    recovered = decode_token(encode_spectrum(spec)).mz
    source = np.asarray(values, dtype=np.float64)
    assert np.all(np.abs(recovered - source) <= source * 1e-7)
    # The default keeps the ppm grid only when it is smaller than exact delta.
    assert encoding_plan(spec)[0]["encoding"][0] in (2, 3)


@pytest.mark.parametrize("values", [[4294967296.0], [1.5]])
def test_pic_domain_guard_and_exact_fallback(values):
    np.testing.assert_array_equal(decode_token(encode_spectrum(InlineSpectrum(1, charge=values))).charge, values)


@pytest.mark.parametrize("dtype", ["int32", "float32", "float64"])
@pytest.mark.parametrize("values", [[], [1, 2]])
def test_json_restores_custom_dtypes(dtype, values):
    source = InlineSpectrum(len(values), extra_arrays={"score": np.array(values, dtype=dtype)})
    restored = spectrum_from_dict(json.loads(json.dumps(spectrum_to_dict(source))))
    decoded = decode_token(encode_spectrum(restored, lossless=True))
    assert decoded.extra_arrays["score"].dtype == np.dtype(dtype)
    np.testing.assert_array_equal(decoded.extra_arrays["score"], source.extra_arrays["score"])


@pytest.mark.parametrize("values", [[1.5], [2**31], [-(2**31) - 1]])
def test_json_rejects_invalid_int32(values):
    with pytest.raises(ValueError, match="int32"):
        spectrum_from_dict({"extra_arrays": {"a": values}, "extra_array_dtypes": {"a": "int32"}})


def test_json_plain_integer_lists_remain_usable():
    spec = spectrum_from_dict({"mz": [1], "extra_arrays": {"score": [1]}})
    assert decode_token(encode_spectrum(spec)).extra_arrays["score"][0] == 1


@pytest.mark.parametrize("change", [lambda b: b[:-4], lambda b: b + b"junk", lambda b: b + zlib.compress(b"")])
def test_incomplete_or_trailing_zlib_rejected(change):
    token = encode_spectrum(InlineSpectrum(2, mz=[1, 2]), lossless=True)
    doc = cbor2.loads(read_token_payload(token))
    doc[6][0][DESC_DATA] = change(doc[6][0][DESC_DATA])
    with pytest.raises(SpectrlDecodeError):
        decode_token(token_for(doc))


def test_fragment_replaces_existing_fragment():
    token = encode_spectrum(InlineSpectrum(0))
    assert extract_token(to_fragment(token, "https://example.org/?x=1#old")) == token


@pytest.mark.parametrize("values", [np.array([[1.0]]), np.array([1 + 2j]), np.array(["1"]), np.array([True])])
def test_invalid_extra_dtype_or_shape_rejected(values):
    with pytest.raises(ValueError):
        encode_spectrum(InlineSpectrum(1, extra_arrays={"a": values}), lossless=True)


def test_empty_custom_name_rejected():
    with pytest.raises(ValueError, match="empty"):
        encode_spectrum(InlineSpectrum(0, extra_arrays={"": np.array([])}))


@pytest.mark.parametrize("doc", [[], {0: -1}, {0: 0, 6: [{}]}])
def test_inspector_uses_structural_validation(doc):
    with pytest.raises(SpectrlDecodeError):
        inspect_token(token_for(doc))
