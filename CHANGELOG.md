# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **token format version** (the `spectrl.v1` magic prefix) is versioned
independently of the library version. See [SPECIFICATION.md](SPECIFICATION.md).

## [Unreleased]

## [1.1.0] - 2026-09-04

### Added

- Python and TypeScript encoding quality reports with array error metrics,
  byte counts, codec information, and explicit user-param omission counts.
- Explicit share-budget candidate selection including complete fragment URL
  overhead, retained peak counts, and omission reports.
- Two-column text, CSV and TSV import/export in both APIs, the CLI, and demo.
- Python mzML conversion reports with structured omission paths and strict checks.
- CLI report, fit, and convert-mzml commands, plus typed custom-array JSON.
- Browser regression tests, numerical boundary regressions, shared malformed
  stream vectors, and mutations that reach CBOR and Numpress parsing.
- Python 3.14 and Node 24 CI coverage, dependency update configuration, and
  scheduled dependency audits.

### Fixed

- Guard Numpress numeric ranges before native calls. Automatic selection falls
  back to lossless encoding outside the supported domain. Explicit unsafe
  codecs fail instead of overflowing or terminating Python.
- Render token metadata and custom-array labels as literal text in the demo.
- Preserve custom arrays named after JavaScript special object properties.
- Reject incomplete and trailing zlib data and truncated Numpress framing.
- Honor and validate fixed-point options on automatically selected codecs.
- Preserve custom-array dtypes through JSON and reject invalid array names,
  shapes, numeric dtypes, and int32 JSON values.
- Replace existing URL fragments when wrapping tokens, share structural
  validation with inspection, and report CLI errors without tracebacks.
- Build npm distributions before packing and resolve locked CI dependencies.
- Preserve imported spectra when changing demo encoding mode and load zstd
  support on demand.

## [1.0.0] - 2026-08-17

### Added
- Optional per-array unit accessions, preserved during mzML import and token
  round-trips, plus generated array, compression, and common-unit enums.
- Resolved encoding inspection and round-trippable CLI spectrum JSON.
- Per-array encoding controls in Python and TypeScript for core and auxiliary
  arrays, including codec selection and Numpress fixed-point overrides.
- Official PSI-MS zstd codecs: raw zstd (`MS:1003780`), byte-shuffled zstd
  (`MS:1003781`), and all three Numpress + zstd combinations
  (`MS:1003783` through `MS:1003785`). JavaScript loads these through the
  optional `@spectrl-ms/spectrl/zstd` entry point with explicit `installZstd()`
  setup to avoid tree-shaking side effects and burdening default bundles.

### Changed
- Python normalizes list-valued arrays at the API boundary. Both languages now
  reject invalid fixed points, reserved custom-array names, and semantically
  incompatible lossy codecs. Full compression accessions are accepted. An
  explicit expert option permits lossy custom arrays without weakening guards
  for known array types.
- Ion-mobility arrays are now preserved by their individual PSI-MS accessions
  in `extra_arrays` / `extraArrays`; spectra may carry multiple distinct
  mobility arrays without last-one-wins routing through a singular field.
  Generated `ArrayAccession` enums provide readable keys, and core accessions
  are accepted as aliases in per-array encoding configuration.
- Numpress linear and slof array descriptors now always carry their actual
  fixed point, including canonical defaults. Decoders reject a missing value or
  a value that disagrees with the fixed point embedded in the Numpress stream.
- Known PSI-MS auxiliary arrays now receive conservative semantic defaults.
  Coordinate arrays use Numpress linear, positive magnitude arrays use Numpress
  slof, and integer index arrays use Numpress pic. Unknown arrays remain
  lossless raw + zlib.

- **The token prefix is now `spectrl.v1`.** The stable `spectrl` identifier and
  explicit `v1` format version are separate dot-delimited parts. Tokens are
  `spectrl.v1.<payload>.<checksum>`. The required CRC-32/ISO-HDLC checksum is
  eight lowercase hexadecimal characters and covers the complete text before
  it. This supersedes the short-lived
  `spectrl2` identifier before broader adoption.

## [0.4.1] - 2026-08-15

### Changed
- `mzmlpy` is no longer a required runtime dependency. Core encoding and
  decoding use spectrl's generated CV registry directly. The `from_mzmlpy`
  bridge remains available through the optional `mzml` extra.

## [0.4.0] - 2026-08-15

### Changed (breaking)
- **The format identifier is now `spectrl2`.** The changes below are not wire
  compatible with the `spectrl1` tokens emitted by released versions, so the
  new identifier provides the clean version break required by the specification.
- **The integrity hash moved out of the CBOR document to a third token part**:
  a token is now `spectrl2.<payload>[.<hash>]`, where the hash is truncated
  SHA-256 over the ASCII text of the first two parts. Verification is a
  substring hash, no CBOR parsing, no byte-surgery, so any tool with
  `sha256` can verify a token. Header key 9 is gone, and so is the strip-key
  machinery in both implementations.
- **The format version is carried only in the magic.** Header key 0
  (`format_version`) is gone. The payload is pure spectrum data. Applications
  persisting spectra should store the full token string, which is
  self-describing and verifiable, rather than bare payload bytes.
- **Header keys renumbered 0–8** (no gaps): `defaultArrayLength`→0, `id`→1,
  `params`→2, `scanList`→3, `precursorList`→4, `productList`→5,
  `binaryDataArrayList`→6, `interp`→7, `userParamList`→8. Part of the same
  pre-freeze reset as the entries below. Earlier development tokens are not
  compatibility artifacts.
- **Array descriptors (header key 7) are now integer-keyed**, matching the header
  itself: `type`→0, `array`→1, `comp`→2, `fp`→3, `name`→4, `d`→5. The names were
  a fixed vocabulary spelled out in full on every array of every token and cost
  more bytes than the values they labelled: 19 of each descriptor's 44 bytes were
  key names. Median MS2 descriptors drop from 89 to 59 bytes, about 4% of a
  typical token. This is part of the new `spectrl2` layout. The specification
  is frozen at this layout. Every
  subsequent breaking wire change will increment the format version.
  Conformance vectors were regenerated in both implementations.

- Removed the precursor reference field and all external-identifier positioning.
  A spectrl token is solely a self-contained spectrum. The old development-only
  precursor reference is no longer emitted or represented by either public model.
- **The numpress fixed point `fp` is now a whole number carried as a CBOR
  integer, and is omitted when it equals the codec's canonical default** (linear
  100000, slof 3600). Absent therefore means that default. A clamped slof fp is
  floored, which is the safe rounding direction: the clamp keeps
  `log(max + 1) * fp` under the uint16 ceiling, so a smaller fp only moves
  further inside it. `fp` cost 9 bytes as a float64 and was the same constant in
  nearly every token. The clamp fired in 0 of 1,120 MS2 spectra of the benchmark
  run. The value is also carried inside the numpress stream itself, so nothing
  is lost.

### Added
- **`encode_spectrum(..., drop_user_params=True)`** (Python) and
  **`encodeSpectrum(spec, { dropUserParams: true })`** (JS) omit free-text user
  params at both spectrum and scan level. On the BSA benchmark run, vendor trailers
  (instrument filter string, Thermo trailer values, preset scan configuration)
  are a median 218 bytes per MS2 token, 35% of its non-peak payload, and largely
  restate CV params the token already carries. The result is a conforming token
  (SPECIFICATION.md §11). The omitted values are not recoverable from it, so
  producers round-tripping mzML faithfully should leave the flag off.
- Strict raw-CBOR validation now rejects duplicate keys at any depth, trailing
  bytes, indefinite lengths, excessive nesting/items, invalid peak counts, and
  oversized payloads before semantic decoding.
- Python and TypeScript consume a shared negative-conformance corpus and run
  deterministic decoder mutation smoke tests in CI.
- Array descriptors now receive exact schema validation, including supported
  data types/codecs, unique semantic identities, non-standard names, finite
  decoded values, and agreement between declared and embedded Numpress fixed
  points.
- `from_mzmlpy(..., strict=True)` rejects unresolved referenceable parameter
  groups. The bridge now preserves auxiliary binary arrays instead of silently
  dropping them.
- CI enforces Python coverage, tests an installed wheel in a clean environment,
  and rejects formatting and whitespace errors.

### Changed
- Duplicate CV accessions are rejected during encoding instead of warning and
  silently retaining only the last value.
- Wire constants and security limits are centralized in generated internal
  modules (`src/spectrl/_format.py` and `js/src/format.ts`). The registry
  generator derives both from `schema/registry.json`. Compatibility re-exports
  preserve existing internal import paths, and tests reject stale generated
  files.

### Fixed
- Non-ASCII token mutations now raise the documented `SpectrlDecodeError`
  instead of leaking `UnicodeEncodeError`.
- Updated the demo and TypeScript development lockfiles to patched `esbuild`
  releases, clearing their npm audit findings.

### Documentation
- Expanded the public README with status badges, project layout, development
  installation, validation commands, scope limitations, and release citation
  guidance.
- Added a release checklist plus structured bug, feature, and pull-request
  templates for the public repository.

## [0.3.0] - 2026-08-12

Existing `spectrl1` tokens remain fully decodable. The changes below are
producer-side behavior, decode hardening, and packaging. Both implementations
(Python + JS) change in lockstep, with new shared conformance vectors.

### Fixed
- **Negative values no longer corrupt silently in lossy mode.** Negative
  intensities (baseline-subtracted data) previously decoded orders of magnitude
  wrong through the slof codec, in both implementations, with the content
  hash still verifying. Negative intensity and ion-mobility arrays now fall
  back to the lossless zlib codec (mirroring the existing charge fallback),
  and all numpress encoders raise a catchable error on negative input.
  Negative m/z is rejected at encode time.
- **The JS implementation ports the 0.2.1 negative-charge fix.** JS previously
  PIC-encoded charge arrays unconditionally, so `[1, -1, 2]` decoded as
  `[1, 4294967295, 2]`. New `negative_charge_sentinel` /
  `negative_intensity_fallback` vectors pin the fallback in both directions.
- **Descriptor `fp` now records the fixed point the blob actually uses.** The
  slof fp is clamped for large intensities (> ~8e7). Previously the descriptor
  recorded the unclamped default.
- **SPECIFICATION.md §7.2 had the numpress pic/slof codec IDs swapped**
  (`MS:1002747` ↔ `MS:1002748`). The implementations, registry, and all emitted
  tokens were correct. Only the spec table was wrong.
- Non-7-digit accession tails no longer crash (`NCIT:C25330`) or corrupt on
  round-trip (`MOD:00046` units): such accessions are carried as full strings.
- `top_n(spec, 0)` returned all peaks. It now returns an empty spectrum, and
  negative `n` raises.
- `to_query` no longer drops existing query parameters on the base URL.
- numpy integer scalars (e.g. `np.int64` `default_array_length`) no longer
  break CBOR encoding.
- int64/uint32 extra arrays raise a clear error instead of silently downcasting
  to float64.

### Added
- **`SpectrlDecodeError`** (a `ValueError` subclass with `SpectrlError` as its base):
  every malformed, corrupted, or unsupported token now raises this single
  documented type. Previously raw `KeyError`/`EOFError`/`zlib.error`/numpy
  errors could leak. JS mirrors with `SpectrlDecodeError extends SpectrlError`.
- **Decompression bounding**: array blobs are decompressed with a cap derived
  from the declared array length (plus a hard ceiling), so a small adversarial
  token can no longer expand to hundreds of MB. Specified in §12. Adversarial
  decode test suites added to both implementations.
- **Consumer-side validation**: tokens are rejected when the header version
  disagrees with the magic (spec §9), when a decoded array's length disagrees
  with `defaultArrayLength`, or when base64url contains non-alphabet
  characters (previously discarded silently).
- **Encode-side validation**: all peak arrays must match
  `default_array_length` (mismatches previously crashed with raw errors or
  silently dropped the tail). Duplicate CV accessions warn on collapse.
- `tokenBreakdown()` (JS): per-array compressed-size introspection, now used by
  the demo's size chart (which previously showed a vestigial single bar).
- `SECURITY.md`, `py.typed` marker, and an IANA-considerations section plus
  consumer rules (unknown/duplicate keys, empty spectra, canonical numpress
  scale factors) in SPECIFICATION.md (draft bumped to 0.2).

### Changed
- **`pynumpress` is now an optional extra** (`pip install spectrl[speed]`).
  pynumpress ships no wheels for Python ≥ 3.12, so it forced a C build on every
  install. The bundled byte-identical pure-Python backend is the default.
- The JS encoder emits canonically ordered CBOR maps (RFC 8949 §4.2), matching
  the Python producer. Decoded param order may differ from insertion order.
- The sdist no longer bundles multi-MB test data, the demo, or the JS package
  (5.7 MB → ~80 KB).
- npm publishing is disabled in CI until the package name is settled (the
  unscoped name `spectrl` is taken and an organization scope had not yet been
  created).
- CI adds macOS and Windows test legs. Vector/registry sync tests no longer
  rewrite committed files during the run.

## [0.2.2] - 2026-07-10

### Added
- **Pure-Python MS-Numpress fallback.** The lossy codecs (linear/slof/pic) now
  run without the `pynumpress` C extension when it is unavailable, via a
  dependency-free port (`spectrl.codecs._numpress_py`). The import of
  `pynumpress` is now lazy, so `import spectrl` no longer requires it. The C
  extension is used when present and the pure-Python path takes over
  transparently otherwise. This lets spectrl (and lossy `spectrl1` token
  encoding/decoding) run in **Pyodide / the browser**, where `pynumpress` has no
  wheel. The fallback is byte-for-byte identical to `pynumpress`, so tokens and
  their SHA-256 content hashes are unchanged and interoperate across backends.
  Set `SPECTRL_NUMPRESS_BACKEND=python` (or `pynumpress`) to pin one.
  `spectrl.codecs.numpress.active_backend()` reports the resolved backend.

## [0.2.1] - 2026-06-28

### Fixed
- **Charge arrays with negative values no longer abort the process.** MS-Numpress
  PIC encodes only non-negative integers, and `pynumpress` raised an uncatchable
  native C++ `terminate` on negative input. Lossy encoding now falls back to
  lossless zlib for the charge array whenever it contains a negative value (e.g.
  unassigned/singleton sentinels emitted by deconvolution tools), and
  `encode_numpic_zlib` raises a catchable `ValueError` instead of aborting if it
  is ever handed negatives directly. Charge stays in the standard charge array
  slot and round-trips exactly.

## [0.2.0] - 2026-06-28

### Added
- **Free-text user params** (`user_params` / `userParams`): mzML `userParam`s (no
  CV accession) at the spectrum level (header key 10) and per scan (scan map key 2),
  each carrying name + optional value / XSD type / unit. Omit-when-empty, so tokens
  that use none are byte-identical to before. `from_mzmlpy` reads them from the
  spectrum and scan XML. Mirrored in Python + JS with bidirectional conformance
  vectors. Specified in `SPECIFICATION.md` §6.7.
- **Extra (auxiliary) per-peak arrays** (`extra_arrays` / `extraArrays`): any mzML
  binary data array can now be carried, keyed by CV accession (e.g. `MS:1000517`
  signal-to-noise) or a free-text name for non-standard `MS:1000786` arrays. Data
  types float64/float32/int32 are preserved. Implemented in both the Python and
  JavaScript reference impls with bidirectional conformance vectors. Specified in
  `SPECIFICATION.md` §7.1 (new optional descriptor `name` field) and §8 (canonical
  ordering of auxiliary arrays). A consumer that does not recognise an array term
  now preserves it rather than discarding it.
- Apache-2.0 `LICENSE` and `NOTICE`.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`.
- GitHub Actions CI (Python test/lint/build + JavaScript test/typecheck/build).
- `SPECIFICATION.md`: normative token format specification (draft).
- `test-vectors/vectors.json`: language-agnostic conformance vectors generated
  from the Python reference impl (`scripts/gen_vectors.py`), with `tests/test_vectors.py`
  pinning them.
- `js/`: independent JavaScript/TypeScript implementation (`@spectrl-ms/spectrl`)
  with a faithful MS-Numpress port, CBOR container codec, and SHA-256 content hashing.
  Decodes Python-produced tokens byte-for-byte and validates against the shared
  vectors.
- `demo/`: a self-contained browser demo (built on the JS impl with esbuild)
  that encodes example spectra live, renders the shareable URL + QR, and decodes
  + plots them client-side, with encoding-size/precision/timing stats. Launch
  via `just demo`.
- **Bidirectional interop testing**: `test-vectors/reverse-vectors.json` (tokens
  encoded by JS) decoded by the Python impl, proving JS → Python in addition to
  the existing Python → JS direction. Plus expanded unit coverage on both sides
  (base64url, CBOR/`stripCborKey`, numpress size boundaries, byte-slice header
  surgery, ordering/duplicates/value-extremes/URL bindings).

### Fixed
- **Single-peak lossy spectra** failed to decode: `pynumpress` emits a 12-byte
  linear blob for a 1-element array but its decoder rejects it. The codec wrapper
  now decodes the degenerate 12-byte case directly (per the MS-Numpress reference),
  making single-peak tokens round-trip and agree with the JS implementation.

### Changed
- **The `spectrl1` token is now a single CBOR document** (RFC 8949), replacing the
  previous msgpack header + dot-separated base64 array segments. The token is
  `spectrl1.<base64url(cbor)>`: one CBOR map holding the header *and* each array's
  compressed blob inline as a byte string. The data model is unchanged. Benefits:
  CBOR is an IETF standard with a defined deterministic encoding. The payload can
  be shipped as raw bytes (no base64) for backend/body transport. The content hash
  is verified by byte-surgery on the received bytes, independent of the CBOR
  library (Python `cbor2` and JS `cbor-x` interoperate both ways). The `msgpack`
  dependency is removed (Python) and the hand-rolled `msgpack.ts` deleted (JS).
  As nothing was released, this is done in place under `spectrl1` (no `spectrl2`).
- **Non-`MS:` parameter-map keys** are now encoded as the full accession string
  (e.g. `"UO:0000031"`) rather than the previously-specified `[ontology, tail]`
  array, which could not be a msgpack-map key. Fixes a latent crash in the
  Python reference impl. Exercised by the `non_ms_ontology_param_key` vector.
  (No released token used the old form.)
- **Hash verification** now derives the "header without key 9" by byte-slicing
  the serialized header rather than re-encoding a parsed structure, so it no
  longer depends on a canonical msgpack form. The hash value is unchanged.
- Clarified that the content hash is a per-token integrity check, not a stable
  cross-implementation content identifier. Softened "deterministic" wording in
  the README and `SPECIFICATION.md` accordingly.

## [0.1.0] - 2026-06-08

### Added
- Initial implementation: `encode_spectrum`, `decode_token`, mzML bridge,
  MS-Numpress + raw codecs, ProForma interpretation, canonical hashing,
  URL/data-URI bindings, and CLI.
- `schema/registry.json`: machine-readable CV/codec/key registry.
