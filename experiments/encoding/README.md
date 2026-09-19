# Encoding exploration

This experiment compares potential lossless and lossy defaults. The benchmark itself does not change the library, token format, or paper results.

The recorded results predate the adaptive lossless implementation. Reruns pin
raw zlib as the lossless baseline to preserve the original comparison. Timing
can change as the library implementation evolves.

Read [findings and recommendations](FINDINGS.md) first.

The expanded [PSI codec sweep](PSI_SWEEP.md) covers all 17 standalone PSI array
compression modes, including dictionary-encoded Zstandard. It reports array
families separately and documents coordinate-grid encoding as requiring an
external model. It supersedes claims about the best PSI-only lossless payload
selector based on the initial three-codec experiment.

The [matched delta comparison](DELTA_COMPARISON.md) evaluates the historical
floating-point predictor from PSI-MS issue #377 against modular bit-pattern
delta using identical arrays and compressor settings.

The implemented adaptive lossless default was separately checked against the
recorded exhaustive selector on all 127 sampled spectra. It preserved every
array bit and decoded metadata, with no size regressions against raw zlib.
See [production validation results](adaptive-validation.json). Reproduce with:

```bash
PYTHONPATH=src .venv/bin/python experiments/encoding/validate_adaptive.py \
  --manifest ../spectrl-paper/paper/analysis/data/corpus.json
```

## Reproduce

From the repository root, run a small benchmark on the bundled BSA file:

```bash
PYTHONPATH=src .venv/bin/python experiments/encoding/benchmark.py \
  --per-group 3 --repeats 3
.venv/bin/python experiments/encoding/report.py
```

For the paper corpus used in the recorded run:

```bash
PYTHONPATH=src .venv/bin/python experiments/encoding/benchmark.py \
  --manifest ../spectrl-paper/paper/analysis/data/corpus.json \
  --per-group 3 --repeats 3 \
  --rows /tmp/spectrl-encoding-rows.json
.venv/bin/python experiments/encoding/report.py --plot \
  --rows /tmp/spectrl-encoding-rows.json
```

The benchmark requires the project's Python dependencies and `mzmlpy`. Brotli and LZ4 are optional. Install `brotli==1.2.0` and `lz4==4.4.5` in the benchmark environment to include them. Plotting additionally requires matplotlib. The recorded run loaded Brotli and LZ4 from `/tmp/spectrl-encoding-deps` using `PYTHONPATH=src:/tmp/spectrl-encoding-deps`. No runtime dependency was added to spectrl.

Use `--paths file1.mzML file2.mzML` to try other files. Use `--compressors zlib-6 zstd-3` for a faster transform comparison. The existing API token comparison always uses its actual default compression levels.

## Method

Select up to three spectra at evenly spaced peak-count quantiles within each dataset, MS level, and representation group. Include the smallest and largest spectrum in groups with at least two selected spectra. Every selected spectrum keeps all peaks and metadata. Sort peaks with the library's canonical ordering. Resolve referenceable parameter groups during mzML import. Verify input hashes against the corpus manifest and record exact selected spectrum IDs.

Compare these reversible transforms on the same little-endian numeric bytes used by the current lossless encoder:

- Raw bytes and byte shuffling.
- First and second modular differences of unsigned IEEE-754 bit patterns, with optional byte shuffling.
- XOR of adjacent bit patterns, with optional byte shuffling.

These deltas operate on integer bit patterns. Ordinary floating-point subtraction and cumulative summation are not generally bit-exact. Every experimental lossless round trip is checked with byte equality. Additional checks cover random bit patterns, empty arrays, single values, signed zero, infinities, NaNs, and subnormal values. Special values test the transform itself, not spectrl's accepted input domain.

Compressors include uncompressed payloads, zlib levels 1/6/9, gzip level 6, Zstandard levels 1/3/9/19, bzip2 level 9, XZ preset 3, Brotli quality 5, and LZ4's default framed mode. Each array is an independent stream. No dictionary or cross-spectrum compression is used.

Lossy experiments retain the current Numpress transform and fixed point while swapping compressors. They also compare float32 conversion with raw, shuffled, and delta-shuffled layouts. Complete token experiments test m/z Numpress fixed points of 10,000 and 1,000,000 against the current 100,000. Intensity keeps the current SLOF precision in those token experiments. Reconstruction error is measured against the source arrays. Float32 can be exact for arrays originally stored as float32, but is not assumed lossless for general float64 inputs.

The complete token comparison uses the public encoder and decoder, including all metadata, CBOR descriptors, base64url expansion, and checksum. `adaptive` tries current defaults, their Zstandard equivalents, raw Zstandard, and byte-shuffled Zstandard, independently choosing the smallest serialized array descriptor and payload. This is an exhaustive size selector over those candidates, not a learned heuristic. It retains the current Numpress precision or selects a lossless representation. Its encode timing includes the candidate search and final re-encoding. Static policy timing excludes preparation of the explicit options.

Every timed operation is warmed once, then measured three times. The per-input median is used. Lossless array timing starts from canonical raw bytes and includes the transform or inverse transform and compressor context construction. Float32 timing includes numeric narrowing. Full token timing includes public encoder or decoder validation. I/O and mzML import are excluded. Timings are exploratory measurements on one machine and one Python backend, not browser performance estimates.

## Read the outputs

- `results.json` records provenance, environment, aggregate results, dataset breakdowns, individual token measurements, and token error metrics.
- `measurements.md` lists the measured size and timing comparisons.
- `token-savings.png` compares complete token savings.
- `array-errors.json` records reconstruction error summaries when `report.py --rows` is used.
- The optional `--rows` file includes every array pipeline measurement and its reconstruction errors. It is intentionally outside the repository in the recorded run.

Total savings are weighted by bytes. Median savings give each spectrum or array equal weight. Large profile spectra can dominate byte totals, so both measures matter. Experimental array payload sizes omit descriptor and token overhead. Numpress rows include only arrays where the current default is linear or SLOF, while float32 rows include core m/z and intensity arrays. Check sample counts and per-array breakdowns before comparing these subsets.

## Compatibility

The current format already defines raw Zstandard, byte-shuffled Zstandard, and Numpress followed by Zstandard. Python includes Zstandard as a dependency. JavaScript requires `installZstd()` from `@spectrl-ms/spectrl/zstd`. The implemented adaptive lossless default selects the smallest of raw zlib, raw Zstandard, and byte-shuffled Zstandard. JavaScript keeps raw zlib when its optional Zstandard backend is unavailable. Cross-language vectors and browser tests cover this behavior. Browser performance measurements remain future work.

Custom delta/XOR pipelines and the other compressors do not have codec definitions in the current spectrl format. The experiment does not assign them existing accessions or emit misleading tokens. Float32 narrowing of core arrays is also an experiment here, rather than a new public option.

The [delta codec proposal](../../docs/delta-codec-proposal.md) specifies the
bit-preserving delta, byte-shuffle, and zlib pipeline, with Python and JavaScript
reference implementations and shared vectors. It remains outside the token registry.

The upstream [MS-Numpress implementation](https://github.com/ms-numpress/ms-numpress) describes the existing fixed-point linear predictor and logged-intensity transform. The [Zstandard project](https://facebook.github.io/zstd/) describes its compression-level tradeoffs and trained dictionary mode. A trained Zstandard dictionary would need a distribution mechanism. That is different from PSI `MS:1003782`, whose value dictionary is embedded in each compressed array. The latter is self-contained and is now covered by the PSI sweep.
