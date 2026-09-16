# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and package major versions track the spectrl token format major version.

Python and JavaScript packages share a version. Releases in the 2.x series use
`spectrl.v2`. Minor and patch releases can improve the libraries without changing
the token format. Runtime support changes are called out in the release notes.
See [SPECIFICATION.md](SPECIFICATION.md).

## [Unreleased]

### Changed

- Header keys are consecutive integers from 0 through 7. Spectrum-level
  free-text parameters use key 7. Decoders reject all other header keys.
- This revision retains the `spectrl.v2` prefix and requires matching updated
  encoders and decoders when exchanging spectrum-level free-text parameters.

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
