"""Generate encoding 4 (rounded floating-point words) vectors with plain integer arithmetic.

Words, byte shuffle, reconstruction, the CBOR document and the token framing are
all computed here from Python integers, ``struct``, ``cbor2``, ``base64`` and
``zlib.crc32``, independent of the spectrl writer. Each decode vector pins the
shuffled blob, the IEEE 754 bits a reader must reconstruct, and a raw-mode token
carrying that blob as the intensity array. The rejection cases are written to
``negative-vectors.json`` (entries whose name starts with ``rounded_``).
"""

import base64
import json
import struct
import zlib
from pathlib import Path

import cbor2

ROOT = Path(__file__).resolve().parents[1]
F32, F64, I32 = 1000521, 1000523, 1000519
MZ_ARRAY, INTENSITY_ARRAY = 1000514, 1000515
FORMATS = {F32: ("<f", "<I", 23, 4), F64: ("<d", "<Q", 52, 8)}


def _float(bits, ufmt="<Q", fmt="<d"):
    return struct.unpack(fmt, struct.pack(ufmt, bits))[0]


def word(value, tail, bits):
    fmt, ufmt, mantissa, _ = FORMATS[tail]
    u = struct.unpack(ufmt, struct.pack(fmt, value))[0]
    d = mantissa - bits
    return u if d == 0 else (u + (1 << (d - 1))) >> d


def shuffle(raw, width):
    n = len(raw) // width
    return bytes(raw[i * width + b] for b in range(width) for i in range(n))


def token(intensity_type, encoding, blob, count, fidelity=1):
    """Raw-mode token: exact float64 m/z 100, 101, ... and the given intensity array."""
    mz = b"".join(struct.pack("<d", 100.0 + i) for i in range(count))
    doc = {
        0: count,
        6: [
            {0: F64, 1: MZ_ARRAY, 2: [0, 1], 5: mz, 7: 0},
            {0: intensity_type, 1: INTENSITY_ARRAY, 2: encoding, 5: blob, 7: fidelity},
        ],
    }
    payload = cbor2.dumps(doc, canonical=True)
    body = "spectrl.v3.r." + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return body, payload, f"{body}.{zlib.crc32(body.encode()):08x}"


def case(name, tail, bits, width, values):
    fmt, _, mantissa, size = FORMATS[tail]
    d = mantissa - bits
    words = [word(v, tail, bits) for v in values]
    assert all(w < 1 << (8 * width) for w in words), name
    blob = shuffle(b"".join(w.to_bytes(width, "little") for w in words), width)
    params = {"bits": bits, "width": width}
    return {
        "name": name,
        "type": tail,
        "parameters": params,
        "count": len(values),
        "source_hex": b"".join(struct.pack(fmt, v) for v in values).hex(),
        "blob_hex": blob.hex(),
        "decoded_hex": b"".join((w << d).to_bytes(size, "little") for w in words).hex(),
        "token": token(tail, [4, 1, params], blob, len(values))[2],
    }


def decode_cases():
    below_two = _float(0x3FFFFFFFFFFFFFFF)
    f32_below_two = _float(0x3FFFFFFF, "<I", "<f")
    sub64 = _float(0x000FFFFFFFFFFFFF)
    sub32 = _float(0x007FFFFF, "<I", "<f")
    return [
        case("f64-bits0-width2", F64, 0, 2, [1.0, 1.5, 3.0, -0.75, 0.0, -0.0]),
        case("f64-bits12-width4", F64, 12, 4, [1.0, 123.456, 1e-3, 2.0**-1022, 7.25]),
        case("f64-bits30-width8-negative", F64, 30, 8, [-1.0, -123.456, 1e300, -0.0]),
        case("f64-bits52-width8-exact", F64, 52, 8, [3.141592653589793, -2.718281828459045, 5e-324]),
        case("f64-carry-into-exponent", F64, 12, 4, [below_two, -below_two, 1 + 2.0**-13]),
        case("f64-subnormals", F64, 12, 4, [sub64, 5e-324, 2.0**-1070, -sub64]),
        case("f64-zeros-width1", F64, 30, 1, [0.0, 0.0]),
        case("f32-bits0-width1", F32, 0, 1, [0.0, 1.0, 2.0**-60]),
        case("f32-bits0-width2-negative", F32, 0, 2, [-1.0, 1.0e38, -0.0]),
        case("f32-bits12-width4", F32, 12, 4, [1.5, 1234.5677, 1e-30]),
        case("f32-bits23-width4-exact", F32, 23, 4, [3.1415927410125732, -2.7182817459106445, 1e-45]),
        case("f32-carry-and-subnormals", F32, 12, 4, [f32_below_two, sub32, 1e-45, -sub32]),
    ]


def negative_cases():
    cases = [
        ("rounded_word_too_large_for_shift", F64, {"bits": 12, "width": 4}, (1 << 24).to_bytes(4, "little"),
         "rounded word exceeds the declared type"),
        ("rounded_width_exceeds_type", F32, {"bits": 12, "width": 8}, bytes(8), "rounded word width exceeds"),
        ("rounded_bits_exceed_type", F32, {"bits": 24, "width": 4}, bytes(4), "rounded mantissa bits exceed"),
        ("rounded_wrong_byte_count", F64, {"bits": 12, "width": 4}, bytes(5), "rounded byte count"),
        ("rounded_nonfinite_reconstruction", F32, {"bits": 0, "width": 2}, bytes([0xFF, 0x00]),
         "rounded reconstruction is not finite"),
        ("rounded_on_int32", I32, {"bits": 12, "width": 4}, bytes(4), "dtype|float32 or float64"),
    ]
    return [
        {"name": name, "cbor_hex": token(tail, [4, 1, params], blob, 1)[1].hex(), "error": error}
        for name, tail, params, blob, error in cases
    ]


def main():
    path = ROOT / "test-vectors" / "rounded-float.json"
    doc = {
        "format": "spectrl-v3-rounded-float",
        "description": "Encoding 4 decode vectors computed with integer arithmetic. decoded_hex holds the "
        "little-endian IEEE 754 values a reader must reconstruct from blob_hex; token carries the "
        "same blob as a raw-mode intensity array.",
        "vectors": decode_cases(),
    }
    path.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"Wrote {path}")
    negative = ROOT / "test-vectors" / "negative-vectors.json"
    existing = json.loads(negative.read_text())
    existing["vectors"] = [v for v in existing["vectors"] if not v["name"].startswith("rounded_")]
    existing["vectors"] += negative_cases()
    negative.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"Wrote {negative}")


if __name__ == "__main__":
    main()
