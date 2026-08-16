"""Deterministic decoder mutation smoke test for CI and local hardening."""

from __future__ import annotations

import random

import numpy as np

from spectrl import SpectrlDecodeError, encode_spectrum
from spectrl.cbor_format import decode_cbor
from spectrl.model import InlineSpectrum


def main() -> None:
    seed = encode_spectrum(
        InlineSpectrum(
            default_array_length=3,
            mz=np.array([100.0, 200.0, 300.0]),
            intensity=np.array([10.0, 20.0, 30.0]),
        )
    )
    rng = random.Random(0x5EC7)
    for _ in range(2_000):
        mutated = bytearray(seed.encode())
        for _ in range(rng.randint(1, 8)):
            if mutated and rng.random() < 0.15:
                del mutated[rng.randrange(len(mutated))]
            elif mutated:
                i = rng.randrange(len(mutated))
                mutated[i] ^= 1 << rng.randrange(8)
        try:
            decode_cbor(mutated.decode("ascii", errors="replace"))
        except SpectrlDecodeError:
            pass
    print("Python decoder mutation smoke test passed (2,000 cases)")


if __name__ == "__main__":
    main()
