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
from spectrl.cbor_format import token_checksum
from spectrl.header import DESC_COMP, DESC_DATA, DESC_FP
from spectrl.model import InlineSpectrum
from spectrl.token import b64url_decode, b64url_encode


def _token() -> str:
    return encode_spectrum(
        InlineSpectrum(
            default_array_length=3,
            mz=np.array([100.0, 200.0, 300.0]),
            intensity=np.array([1e4, 2e4, 3e4]),
        )
    )


def _payload(token: str) -> dict:
    return cbor2.loads(b64url_decode(token.split(".")[2]))


def _retoken(doc: dict) -> str:
    """Re-wrap a tampered document with a valid checksum so decode reaches it."""
    body = "spectrl.v1." + b64url_encode(cbor2.dumps(doc, canonical=True))
    return f"{body}.{token_checksum(body)}"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "notatoken",
        "spectrl.v1",
        "spectrl1.AAAA",  # released legacy format has a different wire layout
        "spectrl.v1.",
        "spectrl.v1.!!!!",  # non-alphabet chars
        "spectrl.v1.abc�.def",  # non-ASCII mutation must not leak UnicodeEncodeError
        "spectrl.v1.A",  # impossible base64 length
        "spectrl.v1.AAAA",  # valid base64, not CBOR-map payload
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
        decode_token(b"spectrl.v1.AAAA")  # type: ignore[arg-type]


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
    raw = b64url_decode(_retoken({0: 0, 6: []}).split(".")[2]) + b"\xff"
    with pytest.raises(SpectrlDecodeError, match="trailing"):
        body = "spectrl.v1." + b64url_encode(raw)
        decode_token(f"{body}.{token_checksum(body)}")


def test_duplicate_cbor_map_key_rejected():
    # {0: 0, 0: 0, 6: []}; ordinary CBOR decoders collapse the duplicate.
    raw = bytes.fromhex("a3000000000680")
    with pytest.raises(SpectrlDecodeError, match="duplicate"):
        body = "spectrl.v1." + b64url_encode(raw)
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


def test_numpress_descriptor_fixed_point_must_match_stream():
    doc = _payload(_token())
    doc[6][0][3] = 100001
    with pytest.raises(SpectrlDecodeError, match="fixed point mismatch"):
        decode_token(_retoken(doc))


def test_numpress_descriptor_requires_fixed_point():
    doc = _payload(_token())
    del doc[6][0][DESC_FP]
    with pytest.raises(SpectrlDecodeError, match="require fp"):
        decode_token(_retoken(doc))


def test_unknown_codec_raises_decode_error():
    doc = _payload(_token())
    doc[6][0][DESC_COMP] = 999999
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_corrupt_blob_raises_decode_error():
    doc = _payload(_token())
    doc[6][0][DESC_DATA] = b"\x00\x01\x02\x03"  # not valid zlib
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_misaligned_raw_blob_raises_decode_error():
    doc = _payload(_token())
    doc[6][0][DESC_COMP] = 1000574  # zlib raw; 7 bytes is not a float64 multiple
    doc[6][0][DESC_DATA] = zlib.compress(b"\x00" * 7)
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_array_length_mismatch_raises_decode_error():
    doc = _payload(_token())
    doc[0] = 5  # header claims 5 peaks; blobs hold 3
    with pytest.raises(SpectrlDecodeError, match="declares"):
        decode_token(_retoken(doc))


def test_zlib_bomb_is_bounded():
    """A blob expanding far beyond the declared array length must be rejected
    without materializing the expansion."""
    doc = _payload(_token())
    doc[6][0][DESC_COMP] = 1000574  # zlib raw
    doc[6][0][DESC_DATA] = zlib.compress(b"\x00" * (10 * 1024 * 1024), 1)  # expands ~1000x past the bound
    with pytest.raises(SpectrlDecodeError):
        decode_token(_retoken(doc))


def test_tampered_checksum_raises_decode_error():
    token = _token()
    parts = token.split(".")
    doc = cbor2.loads(b64url_decode(parts[2]))
    doc[1] = "tampered-id"  # change content, keep stored checksum
    tampered = f"spectrl.v1.{b64url_encode(cbor2.dumps(doc, canonical=True))}.{parts[3]}"
    with pytest.raises(SpectrlDecodeError, match="checksum"):
        decode_token(tampered)


def test_five_part_token_rejected():
    token = _token()
    with pytest.raises(SpectrlDecodeError, match="parts"):
        decode_token(token + ".AAAAAAAAAAAAAAAA")
