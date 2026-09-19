# Lossless modular delta and byte-shuffled zlib compression

Status: proposed codec contract accompanying a PSI-MS term request. The term
identifier in the proposed OBO change is provisional until accepted by PSI-MS.

## Scope and existing work

This codec losslessly transforms an array's little-endian numeric bytes using
modular unsigned-word differences and byte shuffling, then compresses the result
as one zlib stream. It supports 4-byte and 8-byte words. The surrounding format
declares the numeric type and number of elements. No additional parameter or
payload header is introduced by this transform.

This method makes no algorithmic novelty claim. The
[zap serialization project](https://github.com/coolbutuseless/zap#floating-point-delta_shuffle-delta-and-byte-shuffle)
documents the same core transform for float64. This document specifies the
array byte contract, not compatibility with zap serialization.

The earlier [PSI delta discussion](https://github.com/HUPO-PSI/psi-ms-CV/issues/377#issuecomment-2869125979)
excluded a floating-point delta predictor because it was lossy. The method here
uses modular arithmetic on the original bit patterns and preserves every bit.
It differs from the mzMLb predictor associated with `MS:1003089`, the
fixed-point predictor in Numpress, and the delta-free byte-shuffled Zstandard
pipeline of `MS:1003781`. Those accessions must not label this stream.

## Forward transform

Let `w` be the declared word width in bytes, either 4 or 8, and `n` the number of
elements. Input length is exactly `n * w` bytes. Each independently encoded
array resets the predictor. Arrays need not be sorted.

1. Interpret each little-endian word as an unsigned integer `u[i]`, preserving
   its bits. This is not a numeric float-to-integer conversion.
2. For a nonempty array, set `d[0] = u[0]`.
3. For `i > 0`, compute `d[i] = (u[i] - u[i-1]) mod 2^(8*w)`.
4. Serialize each difference as `w` little-endian bytes. Shuffle them into byte
   planes with `shuffled[b*n + i] = difference_bytes[i*w + b]`. Planes run from
   the least significant byte to the most significant byte.
5. Compress the shuffled bytes as one RFC 1950 zlib stream with DEFLATE and the
   Adler-32 checksum. Any valid compression level is permitted. The reference
   uses level 6. Gzip, raw DEFLATE, preset dictionaries, concatenated streams,
   and trailing bytes are not permitted.

The first word is unchanged by the delta step, but participates in shuffling
with every other word. Empty input produces a zlib stream for zero bytes.
The transform is identity for a singleton before zlib compression.

For example, 32-bit unsigned words `[1, 3, 2]` become differences
`[1, 2, 4294967295]`. Their shuffled bytes are:

```text
01 02 ff  00 00 ff  00 00 ff  00 00 ff
```

## Inverse and validation

1. Validate the declared type and length. Compute `n * w` with checked
   arithmetic and enforce the application's allocation budget before decoding.
2. Inflate one complete zlib stream, rejecting a dictionary request, invalid
   checksum, truncation, trailing bytes, or output exceeding `n * w` bytes.
3. Require exactly `n * w` output bytes. Undo byte shuffling using the same
   width and element count to recover the difference words.
4. Set `u[0] = d[0]` when nonempty. For `i > 0`, compute
   `u[i] = (u[i-1] + d[i]) mod 2^(8*w)`.
5. Recover the original little-endian numeric bytes. Do not convert recovered
   64-bit words through a JavaScript `Number` or floating-point accumulator.

This preserves signed zeros, subnormals, infinities, and NaN payloads, without
relaxing any restrictions the containing format imposes on accepted values.
For mzML, Base64 wrapping and numeric type/array length metadata remain the
responsibility of the containing format. Unsupported readers must report the
unknown compression method instead of treating the inflated bytes as numbers.

## Executable reference

This Python 3 reference uses only the standard library. It favors clarity over
speed. `expected_bytes` is the validated element count multiplied by word width.
The caller must enforce its own maximum allocation budget before calling it.

```python
import zlib


def validate(data, width):
    if type(width) is not int or width not in (4, 8):
        raise ValueError("word width must be 4 or 8 bytes")
    if len(data) % width:
        raise ValueError("unaligned array length")


def delta_shuffle(raw, width):
    validate(raw, width)
    mask = (1 << (8 * width)) - 1
    previous = 0
    differences = bytearray()
    for offset in range(0, len(raw), width):
        word = int.from_bytes(raw[offset:offset + width], "little")
        differences.extend(((word - previous) & mask).to_bytes(width, "little"))
        previous = word
    return b"".join(differences[b::width] for b in range(width))


def delta_unshuffle(shuffled, width):
    validate(shuffled, width)
    count = len(shuffled) // width
    mask = (1 << (8 * width)) - 1
    previous = 0
    raw = bytearray()
    for i in range(count):
        word = bytes(shuffled[b * count + i] for b in range(width))
        previous = (previous + int.from_bytes(word, "little")) & mask
        raw.extend(previous.to_bytes(width, "little"))
    return bytes(raw)


def encode(raw, width):
    return zlib.compress(delta_shuffle(raw, width), level=6)


def decode(blob, width, expected_bytes):
    validate(b"", width)
    if type(expected_bytes) is not int or expected_bytes < 0:
        raise ValueError("invalid expected byte count")
    if expected_bytes % width:
        raise ValueError("unaligned expected byte count")
    inflater = zlib.decompressobj()
    shuffled = inflater.decompress(blob, expected_bytes + 1)
    if len(shuffled) != expected_bytes:
        raise ValueError("decoded length mismatch")
    if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
        raise ValueError("invalid or extra zlib stream data")
    return delta_unshuffle(shuffled, width)
```

## Conformance vectors

[Eight vectors](modular-delta-shuffle-zlib-vectors.json) provide raw bytes,
expected shuffled bytes, and example zlib streams in hexadecimal. `item_size`
is `w`. Element count is `len(raw_hex) / (2 * w)`. `shuffled_hex` must match
exactly. Encoders need not reproduce the same compressed bytes, but decoders
must recover `raw_hex` from every provided `zlib_hex`.

The vectors cover empty arrays of both widths, a singleton, modular wraparound,
floating-point special bit patterns, and the float64 m/z array
`[100.0, 100.1, 100.2]`. Expected transformed bytes were calculated with unsigned
integer arithmetic and checked with separate Python/NumPy and JavaScript
bytewise implementations. Python and JavaScript zlib encoders produced the
same example streams for these vectors.

After executing the reference above, the following checks the vector file:

```python
import json
from pathlib import Path

path = Path("docs/modular-delta-shuffle-zlib-vectors.json")
for vector in json.loads(path.read_text())["vectors"]:
    raw = bytes.fromhex(vector["raw_hex"])
    shuffled = bytes.fromhex(vector["shuffled_hex"])
    blob = bytes.fromhex(vector["zlib_hex"])
    width = vector["item_size"]
    assert delta_shuffle(raw, width) == shuffled
    assert delta_unshuffle(shuffled, width) == raw
    assert decode(blob, width, len(raw)) == raw
    assert decode(encode(raw, width), width, len(raw)) == raw
```
