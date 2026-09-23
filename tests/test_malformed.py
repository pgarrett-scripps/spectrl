"""Adversarial decode: every malformed token must raise SpectrlDecodeError.

Tokens arrive from untrusted URLs, so decode_token must never leak raw
KeyError/EOFError/zlib.error/numpy errors, expand without bound, or accept a
token whose declared version or array lengths are inconsistent.
"""

import zlib

import cbor2
import numpy as np
import pytest

from spectrl import SpectrlDecodeError, decode_token, encode_spectrum
from spectrl.cbor_format import read_token_payload, token_checksum
from spectrl.header import DESC_DATA
from spectrl.model import InlineSpectrum
from spectrl.token import b64url_encode


def _token() -> str:
    return encode_spectrum(
        InlineSpectrum(
            default_array_length=3,
            mz=np.array([100.0, 200.0, 300.0]),
            intensity=np.array([1e4, 2e4, 3e4]),
        )
    )


def _payload(token: str) -> dict:
    return cbor2.loads(read_token_payload(token))


def _retoken(doc: dict) -> str:
    """Re-wrap a tampered document with a valid checksum so decode reaches it."""
    body = "spectrl.v3.r." + b64url_encode(cbor2.dumps(doc, canonical=True))
    return f"{body}.{token_checksum(body)}"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "notatoken",
        "spectrl.v3",
        "unsupported.AAAA",  # unsupported format identifier
        "spectrl.v3.",
        "spectrl.v3.!!!!",  # non-alphabet chars
        "spectrl.v3.abc�.def",  # non-ASCII mutation must not leak UnicodeEncodeError
        "spectrl.v3.A",  # impossible base64 length
        "spectrl.v3.AAAA",  # valid base64, not CBOR-map payload
    ],
)
def test_garbage_tokens_raise_decode_error(bad: str):
    with pytest.raises(SpectrlDecodeError):
        decode_token(bad)


def test_truncated_token_raises_decode_error():
    token = _token()
    with pytest.raises(SpectrlDecodeError):
        decode_token(token[: len(token) // 2])


def test_decode_error_is_a_value_error():
    assert issubclass(SpectrlDecodeError, ValueError)


def test_non_string_token_raises_decode_error():
    with pytest.raises(SpectrlDecodeError, match="string"):
        decode_token(b"spectrl.v3.AAAA")  # type: ignore[arg-type]


def test_missing_length_key_raises_decode_error():
    doc = _payload(_token())
    del doc[0]
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


@pytest.mark.parametrize("bad_length", [-1, 1.5, True, "3"])
def test_invalid_declared_length_rejected(bad_length):
    doc = _payload(_token())
    doc[0] = bad_length
    doc[6] = []
    with pytest.raises(SpectrlDecodeError, match="array length"):
        decode_token(_retoken(doc))


def test_trailing_cbor_bytes_rejected():
    raw = read_token_payload(_retoken({0: 0, 6: []})) + b"\xff"
    with pytest.raises(SpectrlDecodeError, match="trailing"):
        body = "spectrl.v3.r." + b64url_encode(raw)
        decode_token(f"{body}.{token_checksum(body)}")


def test_duplicate_cbor_map_key_rejected():
    # {0: 0, 0: 0, 6: []}; ordinary CBOR decoders collapse the duplicate.
    raw = bytes.fromhex("a3000000000680")
    with pytest.raises(SpectrlDecodeError, match="duplicate"):
        body = "spectrl.v3.r." + b64url_encode(raw)
        decode_token(f"{body}.{token_checksum(body)}")


def test_duplicate_semantic_array_rejected():
    doc = _payload(_token())
    doc[6].append(dict(doc[6][0]))
    with pytest.raises(SpectrlDecodeError, match="duplicate array"):
        decode_token(_retoken(doc))


def test_unknown_array_data_type_rejected():
    doc = _payload(_token())
    doc[6][0][0] = 999999
    with pytest.raises(SpectrlDecodeError, match="data type"):
        decode_token(_retoken(doc))


def test_quantized_descriptor_rejects_unknown_parameter():
    option = {"mz": [3, 1, {"scale": 1000, "width": 4}]}
    doc = _payload(encode_spectrum(InlineSpectrum(3, mz=[100, 200, 300]), array_encodings=option))
    doc[6][0][2][2]["fp"] = 100001
    with pytest.raises(SpectrlDecodeError, match="scale|width|parameter"):
        decode_token(_retoken(doc))


def test_quantized_descriptor_requires_parameters():
    doc = _payload(_token())
    doc[6][0][2] = [3, 1]
    with pytest.raises(SpectrlDecodeError, match="scale|width|parameter"):
        decode_token(_retoken(doc))


def test_unknown_codec_raises_decode_error():
    doc = _payload(_token())
    doc[6][0][3] = 999999
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_corrupt_blob_raises_decode_error():
    doc = _payload(_token())
    doc[6][0][DESC_DATA] = b"\x00\x01\x02\x03"  # not valid zlib
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_misaligned_raw_blob_raises_decode_error():
    doc = _payload(_token())
    doc[6][0].update({2: [0, 1], 3: [1, 1], 7: 0})  # zlib raw; 7 bytes is not a float64 multiple
    doc[6][0][DESC_DATA] = zlib.compress(b"\x00" * 7)
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_array_length_mismatch_raises_decode_error():
    doc = _payload(_token())
    doc[0] = 5  # header claims 5 peaks; blobs hold 3
    with pytest.raises(SpectrlDecodeError, match="count"):
        decode_token(_retoken(doc))


def test_zlib_bomb_is_bounded():
    """A blob expanding far beyond the declared array length must be rejected
    without materializing the expansion."""
    doc = _payload(_token())
    doc[6][0].update({2: [0, 1], 3: [1, 1], 7: 0})  # zlib raw
    doc[6][0][DESC_DATA] = zlib.compress(b"\x00" * (10 * 1024 * 1024), 1)  # expands ~1000x past the bound
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_tampered_checksum_raises_decode_error():
    token = _token()
    parts = token.split(".")
    doc = cbor2.loads(read_token_payload(token))
    doc[1] = "tampered-id"  # change content, keep stored checksum
    tampered = f"spectrl.v3.r.{b64url_encode(cbor2.dumps(doc, canonical=True))}.{parts[4]}"
    with pytest.raises(SpectrlDecodeError, match="checksum"):
        decode_token(tampered)


def test_extra_token_part_rejected():
    token = _token()
    with pytest.raises(SpectrlDecodeError, match="parts"):
        decode_token(token + ".AAAAAAAAAAAAAAAA")
