"""Outer compression preserves metadata and enforces limits before CBOR parsing."""

import json
import zlib
from pathlib import Path

import cbor2
import pytest

from spectrl import InlineSpectrum, SpectrlDecodeError, decode_token, encode_spectrum, inspect_token
from spectrl.cbor_format import frame_payload, read_token_payload, token_checksum
from spectrl.token import MAGIC, b64url_encode

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "test-vectors/outer-payload.json").read_text())


@pytest.mark.parametrize("vector", VECTORS["valid"], ids=lambda v: v["name"])
def test_shared_payload_forms(vector):
    if vector["token"].split(".")[2] == "b":
        pytest.importorskip("brotli")
    assert read_token_payload(vector["token"]) == bytes.fromhex(vector["cbor_hex"])
    assert decode_token(vector["token"]).default_array_length == 0
    assert inspect_token(vector["token"]) == []


@pytest.mark.parametrize("vector", VECTORS["invalid"], ids=lambda v: v["name"])
def test_shared_payload_failures(vector):
    if vector["token"].split(".")[2] == "b":
        pytest.importorskip("brotli")
    for reader in (decode_token, inspect_token):
        with pytest.raises(SpectrlDecodeError, match=vector["error"]):
            reader(vector["token"])


def test_default_is_zlib_and_auto_chooses_smallest_complete_token():
    for source in (InlineSpectrum(0), InlineSpectrum(0, id="context-" * 1000)):
        token = encode_spectrum(source)
        assert token.split(".")[2] == "z"
        alternatives = [encode_spectrum(source, compression=c) for c in ("raw", "zlib")]
        import importlib.util

        if importlib.util.find_spec("brotli"):
            alternatives.append(encode_spectrum(source, compression="brotli"))
        assert len(encode_spectrum(source, compression="auto")) == min(map(len, alternatives))
        assert decode_token(token).id == source.id


def test_zlib_wins_equal_size(monkeypatch):
    raw = cbor2.dumps({0: 0})
    monkeypatch.setattr("spectrl.payload._pack", lambda value, mode: value)
    assert frame_payload(raw, "auto").startswith(f"{MAGIC}.z.")


def test_checksum_precedes_outer_decompression(monkeypatch):
    token = encode_spectrum(InlineSpectrum(0, id="context-" * 1000))
    monkeypatch.setattr("spectrl.payload.decompress_payload", lambda *args: pytest.fail("inflated corrupt token"))
    with pytest.raises(SpectrlDecodeError, match="checksum mismatch"):
        decode_token(token[:-1] + ("0" if token[-1] != "0" else "1"))


def test_exact_expanded_limit_is_accepted(monkeypatch):
    raw = cbor2.dumps({0: 0, 1: "x" * 1000})
    body = f"{MAGIC}.z.{b64url_encode(zlib.compress(raw))}"
    token = f"{body}.{token_checksum(body)}"
    monkeypatch.setattr("spectrl.cbor_format.MAX_TOKEN_BYTES", len(raw))
    assert decode_token(token).id == "x" * 1000
    monkeypatch.setattr("spectrl.cbor_format.MAX_TOKEN_BYTES", len(raw) - 1)
    with pytest.raises(SpectrlDecodeError, match="compressed CBOR"):
        decode_token(token)


def test_brotli_drains_buffered_output_for_large_payload():
    pytest.importorskip("brotli")
    from spectrl.payload import compress_payload, decompress_payload

    raw = bytes(range(256)) * 1000
    mode, packed = compress_payload(raw, "brotli", len(raw))
    assert decompress_payload(packed, mode, len(raw)) == raw
    with pytest.raises(ValueError, match="limit"):
        decompress_payload(packed, mode, 100000)


def test_missing_brotli_is_explicit_and_auto_uses_available_backends(monkeypatch):
    import spectrl.payload as payload

    def unavailable():
        raise ValueError("Brotli support is unavailable")

    monkeypatch.setattr(payload, "_brotli", unavailable)
    monkeypatch.setattr(payload.importlib.util, "find_spec", lambda name: None)
    source = InlineSpectrum(0)
    with pytest.raises(ValueError, match="Brotli support is unavailable"):
        encode_spectrum(source, compression="brotli")
    auto = encode_spectrum(source, compression="auto")
    assert len(auto) == min(len(encode_spectrum(source, compression=c)) for c in ("raw", "zlib"))


@pytest.mark.parametrize("mode", ["zstd", "s"])
def test_removed_payload_mode_rejected_by_writer(mode):
    with pytest.raises(ValueError, match="payload compression must be"):
        encode_spectrum(InlineSpectrum(0), compression=mode)
