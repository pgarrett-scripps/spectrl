# Add lossless modular delta and byte-shuffled zlib compression

Local draft only. Publication requires explicit user approval.

## Proposed PR description

Adds a compression term for unsigned-word modular delta, followed by byte
shuffling and zlib. It preserves every input bit, avoiding the floating-point
rounding discussed in #377.

Proposed accession: `MS:1004013` (provisional), under `MS:1000572`.

The same core transform is used by
[zap](https://github.com/coolbutuseless/zap#floating-point-delta_shuffle-delta-and-byte-shuffle).
This PR includes a byte-level specification, Python reference, and eight test
vectors.

## Local review files

[Patch](psi-ms-CV.patch) · [Specification](modular-delta-shuffle-zlib.md) ·
[Validation](VALIDATION.md)
