"""Shared raw and compressed framing vectors, including bounded failure cases."""

import gzip
import json
import zlib
from pathlib import Path

import cbor2
import brotli

from spectrl._format import MAX_TOKEN_BYTES
from spectrl.cbor_format import token_checksum
from spectrl.token import MAGIC, b64url_encode


def frame(mode, payload):
    body = f"{MAGIC}.{mode}.{b64url_encode(payload)}"
    return f"{body}.{token_checksum(body)}"


def main():
    valid = []
    for name, doc in (("minimal", {0: 0}), ("metadata", {0: 0, 1: "scan-context-" * 100})):
        raw = cbor2.dumps(doc, canonical=True)
        for mode, payload in (("r", raw), ("z", zlib.compress(raw, 6)),
                              ("b", brotli.compress(raw, quality=5))):
            valid.append({"name": f"{name}-{mode}", "token": frame(mode, payload), "cbor_hex": raw.hex()})
    raw = cbor2.dumps({0: 0}, canonical=True)
    packed = zlib.compress(raw, 9)
    dictionary_encoder = zlib.compressobj(zdict=b"context")
    dictionary = dictionary_encoder.compress(raw) + dictionary_encoder.flush()
    invalid = [
        {"name": name, "token": frame(mode, payload), "error": error}
        for name, mode, payload, error in (
            ("unknown-mode", "x", raw, "unsupported payload mode"),
            ("removed-zstandard-mode", "s", raw, "unsupported payload mode"),
            ("truncated", "z", packed[:-1], "compressed CBOR"),
            ("trailing", "z", packed + b"x", "compressed CBOR"),
            ("concatenated", "z", packed + packed, "compressed CBOR"),
            ("gzip-is-not-zlib", "z", gzip.compress(raw, mtime=0), "compressed CBOR"),
            ("raw-deflate-is-not-zlib", "z", packed[2:-4], "compressed CBOR"),
            ("dictionary", "z", dictionary, "compressed CBOR"),
            ("bad-adler", "z", packed[:-1] + bytes([packed[-1] ^ 1]), "compressed CBOR"),
            ("expansion-limit", "z", zlib.compress(b"\0" * (MAX_TOKEN_BYTES + 1), 9), "compressed CBOR"),
            ("invalid-cbor", "z", zlib.compress(b"\xff", 9), "CBOR"),
        )
    ]
    for mode, payload in (("b", brotli.compress(raw, quality=5)),):
        for label, blob in (("truncated", payload[:-1]), ("trailing", payload + b"x"), ("concatenated", payload + payload)):
            invalid.append({"name": f"{mode}-{label}", "token": frame(mode, blob), "error": "compressed CBOR"})
    old_body = f"{MAGIC}.{b64url_encode(raw)}"
    invalid.append(
        {"name": "old-four-part-framing", "token": f"{old_body}.{token_checksum(old_body)}", "error": "exactly five"}
    )
    original = frame("z", packed)
    invalid.append(
        {"name": "mode-covered-by-checksum", "token": original.replace(".z.", ".r."), "error": "checksum mismatch"}
    )
    path = Path(__file__).resolve().parents[1] / "test-vectors/outer-payload.json"
    path.write_text(json.dumps({"valid": valid, "invalid": invalid}, indent=2) + "\n")
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
