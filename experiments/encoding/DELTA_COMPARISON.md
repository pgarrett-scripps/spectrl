# Modular delta versus the historical PSI #377 floating predictor

The modular bit-pattern predictor is strictly lossless and produced slightly
smaller aggregate payloads in this comparison. It does not win on every array.

## Comparison

The floating predictor reproduces the exact arithmetic grouping in
[mzd.cpp revision a69a89b](https://github.com/mobiusklein/mzd.cpp/blob/a69a89b2c3bb1c7346e934de1d7c18ee40775ab4/src/mzd.hpp#L98-L133),
the historical implementation associated with PSI-MS issue #377. This is not
the same arithmetic grouping and feedback scheme as the original mzMLb code.
No mantissa truncation or intentional precision reduction was applied.

Both transforms received identical canonical numeric bytes, followed by the
same byte shuffle and compressor at the same level. The 257 arrays contain
3,594,160 values across 127 spectra from 40 datasets. Input hashes and selected
spectrum IDs match the earlier benchmark exactly.

| Final compressor | Floating delta + shuffle | Modular delta + shuffle | Modular reduction |
| --- | ---: | ---: | ---: |
| zlib 6 | 4,446,781 bytes | 4,398,985 bytes | 1.07% |
| Zstandard 3 | 4,574,666 bytes | 4,512,331 bytes | 1.36% |

With zlib, modular delta was smaller on 151 of 257 arrays. With Zstandard, it
was smaller on 152. Aggregate m/z payloads were 3.97% smaller with zlib and
5.56% smaller with Zstandard. Aggregate intensity payloads were 0.79% and 1.57%
larger, respectively. The three mobility arrays were also slightly larger.

## Fidelity

Modular delta recovered every input bit. The floating predictor changed 1,029
values in four arrays: 55 m/z values across three arrays and 974 intensity
values in one array. The largest m/z error was about `2.84e-14` m/z units. The
largest intensity error was about `4.09e-17` in the stored intensity units.
Those errors are tiny in this sample, but they violate a bit-exact contract.

This result supports the modular method as a strictly lossless alternative
with a modest aggregate size improvement over the historical floating method.
It does not establish superior lossy rate-distortion performance or faster
execution. The earlier 23.60% payload reduction compared adding modular delta
to a three-codec selector without any delta method, a different baseline.

## Reproduction and limits

```bash
PYTHONPATH=src .venv/bin/python experiments/encoding/compare_delta_predictors.py \
  --manifest ../spectrl-paper/paper/analysis/data/corpus.json
```

[Detailed results](delta-comparison.json) contain per-array sizes, errors, and
input provenance. The Python reproduction compares transforms and compressor
output sizes, not the performance of the historical C++ binary. Its vectorized
encoder was checked against a literal scalar transcription at both float32
and float64 precision. The sampled arrays use the numeric representations
chosen by the existing lossless spectrl serializer.

The corpus is a selected local sample and is weighted toward large profile
arrays. These are compressed payload sizes, excluding XML, metadata, Base64,
and token framing. No claim of universal superiority is made.
