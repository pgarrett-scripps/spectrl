# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and package major versions track the spectrl token format major version.

Python and JavaScript packages share a version. The current 3.x series uses
`spectrl.v3`. Historical 2.x notes below describe the earlier format. Minor and patch releases can improve the libraries without changing
the token format. Runtime support changes are called out in the release notes.
See [SPECIFICATION.md](SPECIFICATION.md).

## [3.0.0]

- Remove the pre-release Zstandard payload mode and its package dependencies.
  The supported payloads are raw CBOR, zlib, and optional Brotli.

- Set default m/z quantization to a checked maximum error of 0.1 ppm per source value.

- Default to zlib-compressed CBOR with explicit raw, Brotli, and auto payload choices.
- Add shared quantized words for linear and log1p mappings. Use fixed lossless and lossy policies, with one outer compression pass.
- Remove pre-release Numpress, dictionary, PSI codec aliases, and per-array compression. Core encoding IDs are 0 through 3.
- Allow optional labels on standard arrays while retaining accession-based identity.
- Verify the mode and payload checksum before bounded outer decompression in both full decoding and inspection.

- Introduce v3-only tokens with versioned numeric encodings and whole-document compression.
- Support custom namespaced encodings and required or optional extensions.
- Add lossless modular delta plus byte shuffle.
- Preserve native float32, float64, and int32 arrays, repeated CV terms, and nested user parameters.
- Carry selected-spectrum source, instrument, software, and processing context.
- Record peak selection, metadata omission, and known lossy encoding history.
- Retain the trailing CRC32 corruption checksum. No hash ID is added.

## Pre-v3 development notes

### Changed

- Automatic lossless encoding selects the smallest supported codec per array
  from zlib, zstd, and byte-shuffled zstd, preserving explicit overrides and
  preferring zlib on ties. JavaScript includes the zstd candidates after
  `installZstd()` and uses zlib alone before installation. Lossy defaults are
  unchanged. Adaptive lossless tokens may require a zstd-capable consumer.
- Python zstd decoding requires a complete single frame and rejects trailing
  data while checking the declared output size before allocation.
- Header keys are consecutive integers from 0 through 7. Spectrum-level
  free-text parameters use key 7. Decoders reject all other header keys.
- This revision retains the `spectrl.v2` prefix and requires matching updated
  encoders and decoders when exchanging spectrum-level free-text parameters.

### Added

- A draft byte contract, unregistered reference implementations, and shared
  vectors for lossless modular delta, byte shuffle, and zlib compression.
  See [the codec proposal](docs/delta-codec-proposal.md). No new PSI-MS accession
  is assigned, and the proposed codec is not emitted in spectrl tokens.

## [2.1.0] - 2026-09-15

### Added

- Optional Python and JavaScript decoder budgets for complete token bytes,
  declared peaks, array count, and aggregate decoded array bytes. Array budgets
  are checked before decompression.
- Runnable Python producer and Node consumer examples with explicit precision,
  HTTP response limits, decoder budgets, and error handling.
- Service integration guidance covering concurrency, workers, and zstd setup.

### Changed

- Require Node 22+ for the JavaScript package, matching the tested Node 22 and
  24 runtime range. Zstd remains an installed dependency with explicit setup.
- Correct npm availability documentation and expand the JavaScript API guide.
- Keep calls without decoder budgets compatible with the existing format limits.

## [2.0.0] - 2026-09-14

### Added

- The `spectrl.v2` format for measured spectra and acquisition context.
- Python and TypeScript reference implementations and shared conformance vectors.
