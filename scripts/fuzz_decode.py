"""Deterministic framing, CBOR and compressed-array mutations for CI."""

from __future__ import annotations

import random
import zlib

import cbor2

from spectrl import InlineSpectrum, SpectrlDecodeError, decode_token, encode_spectrum
from spectrl.cbor_format import token_checksum
from spectrl.header import DESC_DATA
from spectrl.token import b64url_decode, b64url_encode


def main() -> None:
    seed = encode_spectrum(InlineSpectrum(3, mz=[100, 200, 300], intensity=[10, 20, 30]))
    raw = b64url_decode(seed.split(".")[2])
    rng = random.Random(0x5EC7)
    counts = {"framing": 0, "cbor": 0, "array": 0}

    def mutate(value):
        value = bytearray(value)
        for _ in range(rng.randint(1, 4)):
            if not value:
                break
            index = rng.randrange(len(value))
            if rng.random() < 0.15:
                del value[index]
            else:
                value[index] ^= 1 << rng.randrange(8)
        return bytes(value)

    for trial in range(2_000):
        mode = trial % 3
        if mode == 0:
            token = mutate(seed.encode()).decode("ascii", errors="replace")
            counts["framing"] += 1
        else:
            if mode == 1:
                payload = mutate(raw)
                counts["cbor"] += 1
            else:
                doc = cbor2.loads(raw)
                descriptor = doc[6][rng.randrange(2)]
                descriptor[DESC_DATA] = zlib.compress(mutate(zlib.decompress(descriptor[DESC_DATA])))
                payload = cbor2.dumps(doc)
                counts["array"] += 1
            body = "spectrl.v1." + b64url_encode(payload)
            token = body + "." + token_checksum(body)
        try:
            decode_token(token)
        except SpectrlDecodeError:
            pass
    print(f"Python decoder mutations passed: {counts}")


if __name__ == "__main__":
    main()
