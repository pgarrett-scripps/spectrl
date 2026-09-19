# PSI-MS compression mode sweep

All 17 standalone array compression terms were exercised where their numeric domains permit.
The 18th term, coordinate-grid encoding (`MS:1003826`), requires an external grid and
spacing model that these standalone arrays do not contain. It is not a drop-in compressor.

The corpus contains 257 arrays from 127 spectra in 40 datasets:
127 m/z arrays, 127 intensity arrays, and three mean inverse reduced ion-mobility arrays.
All use float64 in spectrl's canonical lossless representation. No real charge arrays
occur in this sample. Supplementary synthetic positive/signed charge checks are kept
in `psi-synthetic-charge.json` and are excluded from every corpus total below.

## Standalone lossless methods at default compressor levels

Every entry compares the same arrays with raw zlib 6. Positive percentages mean smaller
compressed payloads. Metadata, XML, token framing, and Base64 are excluded.

| Method | Total bytes | Overall savings | m/z savings | Intensity savings | Mobility savings |
| --- | ---: | ---: | ---: | ---: | ---: |
| No compression | 28,753,280 | -232.59% | -153.06% | -384.90% | -263.76% |
| zlib 6 | 8,645,158 | 0.00% | 0.00% | 0.00% | 0.00% |
| Zstandard 3 | 8,269,443 | 4.35% | 9.33% | -5.21% | 6.09% |
| Byte-shuffled Zstandard 3 | 5,415,278 | 37.36% | 47.93% | 17.73% | -177.91% |
| Dictionary-encoded Zstandard 3 | 5,468,478 | 36.75% | 47.17% | 16.80% | 29.82% |
| Experimental modular delta + shuffle + zlib 6 | 4,398,985 | 49.12% | 70.41% | 9.02% | -192.01% |
| Experimental modular delta + shuffle + Zstandard 3 | 4,512,331 | 47.81% | 68.72% | 8.43% | -192.62% |

## Per-array selection

The general lossless PSI pool is no compression, zlib, Zstandard, byte-shuffled Zstandard,
and dictionary-encoded Zstandard. Truncation with zero removed bits is equivalent to raw
zlib. Numpress and floating-point predictors are not assumed lossless just because some
arrays happen to round-trip exactly.

Default levels mean zlib 6 and Zstandard 3. The tuned pool additionally searches zlib
levels 1 and 9 and Zstandard levels 1, 9, and 19. This is a size search, not a speed recommendation.

| Policy | Total bytes | Savings versus raw zlib 6 |
| --- | ---: | ---: |
| Current spectrl PSI selector | 5,371,555 | 37.87% |
| PSI lossless selector including dictionary, default levels | 5,143,826 | 40.50% |
| Same pool plus proposed delta + shuffle + zlib 6 | 3,878,807 | 55.13% |
| Same pool plus modular delta with either compressor | 3,873,449 | 55.20% |
| PSI lossless selector, tuned levels | 4,487,179 | 48.10% |
| Tuned PSI pool plus modular delta | 3,624,419 | 58.08% |
| All tested PSI modes, with exact-byte verification per array | 4,326,676 | 49.95% |
| Verified-exact PSI pool plus modular delta | 3,865,690 | 55.28% |

The last two rows use an exhaustive selector that verifies exact recovery. It admits a normally
lossy codec only when this particular encoded array reconstructs the original bytes
exactly. Using this approach would require encoding, decoding, and checking each candidate.
It is not the production policy or evidence that those codecs are generally lossless.
A future selector could nevertheless guarantee lossless output by verifying every
candidate against the source bytes and retaining a conventional lossless fallback.

## Marginal benefit of modular delta after adding dictionary

| Comparison | Overall | m/z | Intensity | Mobility |
| --- | ---: | ---: | ---: | ---: |
| Add proposed delta + zlib 6 | 24.59% | 42.75% | 0.49% | 0.00% |
| Add delta with either default compressor | 24.70% | 42.86% | 0.59% | 0.00% |
| Add delta with tuned compressors | 19.23% | 35.73% | 0.27% | 0.00% |
| Add delta to exact-recovery selector | 10.65% | 21.17% | 0.59% | 0.00% |

## Why array types need separate results

m/z arrays are ordered and can favor prediction. Intensity arrays have different
structure and repeated values. Mobility arrays can contain a small repeated value set
in an order determined by m/z. Charge is integer-valued and has its own codec eligibility.

The table below shows codec choices for the default PSI lossless pool, including dictionary.

| Array | Chosen codec | Arrays |
| --- | --- | ---: |
| mz | MS:1003781 level 3 | 76 |
| mz | MS:1003780 level 3 | 42 |
| mz | MS:1000576 level 0 | 1 |
| mz | MS:1000574 level 6 | 6 |
| mz | MS:1003782 level 3 | 2 |
| intensity | MS:1003781 level 3 | 76 |
| intensity | MS:1000576 level 0 | 1 |
| intensity | MS:1003782 level 3 | 33 |
| intensity | MS:1003780 level 3 | 8 |
| intensity | MS:1000574 level 6 | 9 |
| MS:1003006 | MS:1003782 level 3 | 3 |

Separate profile and centroid summaries are also recorded in the JSON. Large profile
spectra dominate byte-weighted totals. The three mobility arrays are too few to support
broad claims about mobility instruments. The sample contains no real charge arrays or
chromatogram time arrays, so those need dedicated datasets before choosing defaults.

## All PSI terms and applicability

| Accession | Name | Status |
| --- | --- | --- |
| MS:1000574 | zlib compression | measured |
| MS:1000576 | no compression | measured |
| MS:1002312 | MS-Numpress linear prediction compression | measured |
| MS:1002313 | MS-Numpress positive integer compression | measured |
| MS:1002314 | MS-Numpress short logged float compression | measured |
| MS:1002746 | MS-Numpress linear prediction compression followed by zlib compression | measured |
| MS:1002747 | MS-Numpress positive integer compression followed by zlib compression | measured |
| MS:1002748 | MS-Numpress short logged float compression followed by zlib compression | measured |
| MS:1003088 | truncation and zlib compression | measured |
| MS:1003089 | truncation, delta prediction and zlib compression | measured |
| MS:1003090 | truncation, linear prediction and zlib compression | measured |
| MS:1003780 | zstd compression | measured |
| MS:1003781 | byte-shuffled zstd compression | measured |
| MS:1003782 | dictionary-encoded zstd compression | measured |
| MS:1003783 | MS-Numpress linear prediction compression followed by zstd compression | measured |
| MS:1003784 | MS-Numpress positive integer compression followed by zstd compression | measured |
| MS:1003785 | MS-Numpress short logged float compression followed by zstd compression | measured |
| MS:1003826 | coordinate grid encoding | Requires an external coordinate grid and spacing model, absent from these standalone arrays |

Numpress linear used fixed point 100,000. SLOF requested 3,600, clamped per array to avoid
uint16 overflow. PIC was tried only for nonnegative whole numbers within uint32 range.
Rejected domains were recorded rather than silently changing input values or precision.
Ineligible arrays by Numpress family: {'numpress-pic': 224, 'numpress-linear': 79}.

The three mzMLb codecs were tested with 0, 16, 29, and 36 low mantissa bits removed.
Their predictors use the mzMLb reference equations and floating-point arithmetic.
Numpress modes were tested without an outer compressor, with zlib 6, and with Zstandard 3.
Smaller lossy output is not an improvement at equal accuracy. Per-array maximum absolute,
relative, and peak-normalized errors and bit-change counts are recorded for every variant.

## Reproduction and reference implementations

```bash
PYTHONPATH=src .venv/bin/python experiments/encoding/psi_codec_sweep.py \
  --manifest ../spectrl-paper/paper/analysis/data/corpus.json \
  --vocabulary /path/to/psi-ms.obo
.venv/bin/python experiments/encoding/report_psi_sweep.py
```

- [Detailed mode, policy, error, timing, and provenance results](psi-sweep.json)
- [PSI-MS vocabulary](https://github.com/HUPO-PSI/psi-ms-CV/blob/master/psi-ms.obo)
- [Dictionary reference](https://github.com/mobiusklein/mzdata/blob/ebe2e9a8f3db8f11de8726aaa5a04920d00aa580/crates/mzdata-bindata/src/encodings.rs)
- [mzMLb predictor reference](https://github.com/biospi/pwiz/blob/mzMLb/pwiz/data/msdata/IO.cpp)
- [Numpress reference](https://github.com/ms-numpress/ms-numpress)

The dictionary implementation stores sorted unsigned bit patterns and byte-shuffles the
dictionary and index arrays separately. Its 16-byte header is included in every nonempty
payload. Index widths follow the maintained mzdata reference, including the 256 and 65,536
distinct-value boundaries. An independent scalar implementation checked the transformed
bytes at the boundary cases. Signed zeros, NaN payloads, and arbitrary bit patterns were checked.

This is a Python benchmark reproduction, not a conformance claim for all existing readers.
Older C++ and Python reference versions disagree at certain dictionary index-width boundaries.
Runtime figures are one-shot exploratory measurements and include Python predictor loops.
They should not be used to rank optimized production implementations or browser performance.
No new public codec or token format was enabled by this experiment.
The full per-array variant rows are written to `/tmp/spectrl-psi-sweep-rows.json` by default.
Use `--rows PATH` to save them elsewhere. The saved summary retains per-mode
aggregates, per-array winning selections, rejected domains, and input provenance.
