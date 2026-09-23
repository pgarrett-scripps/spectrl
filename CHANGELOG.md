# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and package major versions track the spectrl token format major version.

Python and JavaScript packages share a version. The current 3.x series uses
`spectrl.v3`. Historical 2.x notes below describe the earlier format. Minor and patch releases can improve the libraries without changing
the token format. Runtime support changes are called out in the release notes.
See [SPECIFICATION.md](SPECIFICATION.md).

## [3.0.0] - 2026-09-22

- Add core encoding 4, `rounded-float`: float32 or float64 values keep their
  sign, exponent and leading `bits` mantissa bits, rounded half away from zero
  on the integer bit pattern and stored as byte-shuffled words of `width` bytes.
  The relative error of a normal value is at most 2^-(bits+1). The declared
  type is kept, and readers reject words too wide for the shift and nonfinite
  results.

- Every encoding now reconstructs the array's declared type. A float32 array
  quantized with encoding 3 decodes to float32, rounded to nearest, ties to
  even, from the binary64 reconstruction. Default candidates declare the native
  type, and writer bound checks use the declared-type value. When the float32
  0.1 ppm m/z check fails, the writer keeps the exact encoding.

- Make the default lossy profile a per-array size choice. Nonnegative floating
  intensity tries, in tie order, exact byte shuffle, scale-1 words when every
  value is an integer (exact for counts), encoding 4 with 12 bits (relative
  bound 2^-13, about 0.012%) and the log1p grid; floating m/z tries exact
  modular delta, then the 0.1 ppm grid. The smallest wins and ties keep the
  earlier candidate, so a default array is never larger than its exact
  encoding. Size is the encoded array length for raw payloads and its zlib
  level 6 length otherwise, so the choice can depend on `compression`.

- Refine the default lossy intensity grid for values below 1. The fixed log1p
  scale of 3600 is nearly linear there, so normalized spectra lost every peak
  below about 1.4e-4 to zero. When the smallest positive intensity `m` is below
  1, writers now choose `max(3600, ceil(1800 * (m + 1) / m))`, which keeps every
  positive intensity within about 0.028% of itself. Spectra whose intensities
  are all 0 or at least 1 encode exactly as before, and decoding is unchanged.

- Convert between tokens and mzML, MGF and MS2 files in both packages. mzML is
  the interchange format and round-trips a token unchanged; MGF and MS2 hold a
  precursor and peaks, so every writer reports what the target could not carry
  instead of dropping it silently. `spectrl encode run.mzML --index 42` selects
  one spectrum from a run, and `spectrl decode TOKEN --output spectrum.mzML`
  writes it back. The browser demo gains a converter that reads and writes
  these files in the page, with no upload.

- Make the base64url payload canonical. Readers reject `=` padding and a final
  character whose unused bits are not zero, so a payload has exactly one valid
  token string instead of several that each pass the checksum.

- Reject a CBOR float whose value is integral and within the safe integer range,
  in any position. Writers already emitted the integer form; accepting both left
  `3` and `3.0` spelling the same document, which a reader in a language with one
  numeric type cannot distinguish after parsing.

- Validate the wire form of a unit accession wherever one appears, including CV
  and free-text parameters at spectrum, scan, precursor, array, and processing
  scope. A boolean, a pair with a missing or extra member, a non-text ontology
  prefix, a tail outside 0..9999999, and a non-accession string are now errors
  rather than being coerced into an accession the encoder could not write back.
  This checks syntax only; no ontology is resolved.

- Fix an `IndexError` escaping `decode_token` for a unit pair shorter than two
  members in array-scoped parameters. Every malformed token now terminates in
  `SpectrlDecodeError` as documented.

- Require array descriptor key 10 to be a list. An empty string, map, or byte
  string previously passed as an empty processing history.

- Reject a byte string as a processing `parameters` map in the JavaScript
  implementation, and range-check accession tails there to 0..9999999. Reject
  `null` where an extension map is required. These matched the Python reader
  already.

- Apply decoder resource budgets by default in both implementations, with
  `DecodeLimits.unlimited()` and `UNLIMITED_DECODE_LIMITS` for a trusted
  producer. The wire ceilings alone allowed a 21 kB token to reconstruct 128 MB
  of arrays. Defaults are 4 MiB of token, 1,000,000 peaks, 64 arrays, and 64 MiB
  of reconstructed arrays, roughly an order of magnitude above the largest
  spectrum in the benchmark corpus. Encoding is not subject to them.

- Add an adversarial conformance corpus: `scripts/adversarial_corpus.py` with
  158 named cases pinned in `test-vectors/adversarial-vectors.json`, plus seeded
  document mutations. `scripts/check_adversarial_parity.py` compares 120,158
  tokens across both decoders in CI and fails on any difference in acceptance,
  recovered values, or exception type.

- Record the source-declared ontology version for each accession prefix at header
  key 12, keyed as `MS` or `UO` rather than by the arbitrary `id` an mzML file
  gives a `cv` element. Versions are opaque text carried verbatim, populated on
  mzML import for the ontologies a spectrum actually cites. The entry is
  informational provenance: the accession remains the identifier, and a reader
  must not reject a token over the release it names.

- Align Python and JavaScript numeric metadata serialization, including exact
  short floats, whole-valued floats, and all safe integers. Preserve numeric
  array bits and sort additional array names by Unicode scalar values in both
  writers. Add shared complete-token vectors and a cross-language CI comparison.

- Remove separate user-parameter type annotations. Values carry their native CBOR
  type; mzML import converts declared numeric user values and rejects invalid or
  out-of-range numbers. Earlier draft v3 tokens with the `t` field are rejected.

- Preserve unsupported shared links in the viewer and show a version error instead
  of substituting the demo spectrum.
- Reject accession-shaped custom array names before decoding to prevent array
  identity collisions. Preserve unusual custom names, Unicode digits, and their
  report metadata.
- Preserve auxiliary float32 widths across byte orders, and rank int32 boundary
  values correctly during peak selection.
- Expand regression coverage for link loading, array names, endian conversion,
  integer boundaries, deterministic selection, and finite numeric bit patterns.
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
