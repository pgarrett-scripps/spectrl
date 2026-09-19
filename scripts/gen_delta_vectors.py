"""Generate proposed delta-codec vectors using independent integer arithmetic."""

import json
import zlib
from pathlib import Path


def vectors():
    cases = [
        ("empty32", 4, []),
        ("empty64", 8, []),
        ("singleton", 8, [0x4059000000000000]),
        ("wrap32", 4, [0, 0xFFFFFFFF, 0, 0x7FFFFFFF, 0x80000000]),
        ("wrap64", 8, [0, 0xFFFFFFFFFFFFFFFF, 0, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000]),
        ("float32_bits", 4, [0, 0x80000000, 1, 0x7F800000, 0xFF800000, 0x7FC01234, 0x3F800000]),
        (
            "float64_bits",
            8,
            [0, 0x8000000000000000, 1, 0x7FF0000000000000, 0xFFF0000000000000, 0x7FF8000000001234, 0x3FF0000000000000],
        ),
        ("mz64", 8, [0x4059000000000000, 0x4059066666666666, 0x40590CCCCCCCCCCD]),
    ]
    out = []
    for name, width, words in cases:
        raw = b"".join(word.to_bytes(width, "little") for word in words)
        previous = 0
        differences = []
        for word in words:
            differences.append(((word - previous) % (1 << (8 * width))).to_bytes(width, "little"))
            previous = word
        shuffled = bytes(difference[b] for b in range(width) for difference in differences)
        out.append(
            {
                "name": name,
                "item_size": width,
                "raw_hex": raw.hex(),
                "shuffled_hex": shuffled.hex(),
                "zlib_hex": zlib.compress(shuffled, 6).hex(),
            }
        )
    return out


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "test-vectors" / "delta-proposal.json"
    destination.write_text(
        json.dumps({"status": "proposal, not spectrl.v3 tokens", "vectors": vectors()}, indent=2) + "\n"
    )
