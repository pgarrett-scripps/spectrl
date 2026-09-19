# Clean core validation

This is the earlier core and precision-policy checkpoint. For the current
release counts, CBOR hardening, regenerated manuscript checks, and remaining
publication actions, see [the final release review](../../docs/v3-release-review.md).

The main and paper library copies use the same four numeric encodings. The
synchronization manifest is `library-sync-clean-core.json`. Earlier validation
reports describe earlier development snapshots.

Completed checks:

- Python: 495 tests pass, with 84.01% coverage against the 80% required threshold.
- JavaScript: all 22 test files pass, along with type checking and package build.
- Browser: all eight checks pass, including lazy Zstandard and Brotli loading,
  exact default policy, resource limits, metadata rendering, and peak selection.
- Installed distributions: fresh wheel and npm tarball workflow smoke tests pass.
- Decoder mutation checks: 2,000 cases per language across framing, CBOR, arrays,
  and outer compression.
- Real mzML bridge: 29 spectra across two source files pass.
- Analysis invariants: all 15 tests pass, including exact bits, quantization,
  information-matched XML, and metadata rejection.
- Final profile matrix: 2,370 exchanges pass in each language direction across
  237 spectra, both fidelity profiles, and all five payload choices.
- Registry generation, release version consistency, lint, formatting, and
  whitespace checks pass.

The final zlib totals are 4,907,430 characters for lossy and 7,187,540 for lossless.
The prior baseline totals are 5,177,997 and 6,815,155. The new lossy profile is
5.23% smaller, while the fixed exact profile is 5.46% larger. The complete-document
core selection experiment recovers 0.425% relative to the fixed exact profile.
These corpus measurements do not establish universal compression rankings.

`final-profile-results.json` links the complete-token totals to the regenerated
paper report. `core-selection-results.json` records each adaptive experiment row.

The full-file audit covers 4,045 spectra and 3,922,699 peaks.
It preserves exact bits in lossless mode. Every default m/z reconstruction
passes the pointwise 0.1 ppm bound. The measured maximum is 0.099997993 ppm. Maximum intensity error normalized to the spectrum base peak is
0.01445%. Of positive input intensities, 2.4268% round to zero. These weak-peak
effects are reported explicitly rather than described as scientifically lossless.

## Default m/z precision update

Default floating m/z now uses nearest rounding on a logarithmic grid calibrated
to a maximum pointwise error of 0.1 ppm. The existing decoder representation is
unchanged. Intensity keeps log1p scale 3600. Zeros remain exact, and unsupported
quantization uses the exact profile. Explicit linear grids remain available.

The new default passed the 495 Python tests, all 22 TypeScript test files, all
eight browser checks, and all 15 analysis invariant tests. The profile matrix
and complete-file fidelity audit were rerun with the new default. Timing, tables,
figures, and manuscript statistics were regenerated. Installed-distribution and
mutation checks listed above were completed at the preceding core-cleanup
checkpoint. Those checks were not repeated for this precision-policy update.

The final paper verification passed, including artifact freshness. Independent
statistics validation reproduced all 79 generated values. Visual review covered
all 24 PDF pages and all 31 rendered Word pages with no clipping or overlaps.
