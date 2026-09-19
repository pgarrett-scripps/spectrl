# Minimum-anchored intensity experiment

Decision recorded on 2026-09-18: retain the current intensity encoding for v3.
The default remains log1p quantization at scale 3600. Do not implement or support
the minimum bucket, minimum-anchored logarithmic grid, or minimum-normalized
log1p alternatives. Keep this experiment as repository development history only.
Do not add it to the paper or Supporting Information. The paper continues to
report the measured behavior and limitations of the implemented encoding.

Replacing every decoded zero with a positive minimum is incorrect when the
source contains genuine zeros. Once both values share the same stored code, the
decoder cannot distinguish them. Every candidate here instead reserves code 0
for actual zero and preserves the distinction during encoding.

The strongest candidate uses the smallest positive input intensity `m` as the
origin of a logarithmic grid. For each positive input `x`:

```text
q = 1 + round(scale * (ln(x) - ln(m)))
x_reconstructed = exp(ln(m) + (q - 1) / scale)
```

Code 0 reconstructs to zero. Code 1 reconstructs directly to `m`. The words are
byte shuffled and the complete document uses the existing zlib compressor.
The prototype uses scale 3600. In exact arithmetic, the relative rounding bound
is `exp(0.5 / scale) - 1`, about 0.01388985%. A production encoder would also
check the actual reconstructed values and fall back to exact encoding when
floating-point limits prevent the promised bound.

| Candidate | Positive samples becoming zero | Largest positive-value relative error | Change in complete token characters |
| --- | --- | --- | --- |
| Current log1p | 69,518 | 100% | Baseline |
| Separate minimum bucket | 0 | Approximately 100% | +0.206% |
| Minimum-anchored positive logarithmic grid | 0 | 0.01388982% | +3.098% |
| Log1p normalized by the minimum | 0 | 0.02771448% | +3.277% |

Error measurements cover 4,045 spectra, 3,922,699 samples, 2,864,591 positive
intensities, and 1,058,108 true zeros. All four candidates preserve true zeros.
Sizes cover the existing 237-spectrum selected corpus with all other data and
encodings fixed. Proposed descriptor parameters are included in the totals.
These are prototype size estimates, not tokens supported by the current
production decoder. Final parameter names and representations can alter size.

The 3.098% increase is not the cost of storing one minimum. A counterfactual
size check added the proposed metadata while retaining the old array bytes,
then substituted the new integer words. Metadata accounted for 9,090 additional
characters and changing the words accounted for another 142,941 characters.
Eighteen spectra moved from two-byte to four-byte intensity words, while 25
moved from four-byte to two-byte words and two moved from two-byte to one-byte
words. The remainder stayed at two bytes. Compression also depends on the new
word patterns. This conditional size breakdown is recorded in
[intensity-size-components.json](intensity-size-components.json). The
metadata-only intermediate is an accounting device, not a decodable candidate.

The minimum-bucket candidate stores a distinct code for tiny positive values
that the current grid would erase. It reconstructs all of those values to the
array minimum. This saves the zero/nonzero distinction, but a value much larger
than the minimum can still lose almost all its magnitude. For example, mapping
0.00001 to a minimum of 0.00000001 causes 99.9% relative error even though the
result is positive.

The positive logarithmic grid directly addresses magnitude error. It performed
better than minimum-normalized log1p on both error and total size in this corpus.
Its maximum base-peak-normalized error was 0.01388833%, compared with 0.01444864%
for the current mapping. Those numbers do not establish downstream scientific
equivalence, and the corpus does not establish universal size rankings.

The decision favors the existing, validated encoding and a smaller format.
The minimum bucket preserves zero versus positive but does not resolve large
relative errors in weak values. The positive logarithmic grid offers better
relative accuracy at a higher size cost and would require another supported
mapping and additional validation. Neither tradeoff was selected for v3.
Lossless mode remains available when exact weak intensities matter.

The scripts and measurements below are unsupported research artifacts. They
are not part of the public API, format specification, or published packages.
Their retention does not represent a planned feature.

Reproduce from the spectrl repository with the paper analysis environment:

```bash
uv run --project ../spectrl-paper/paper/analysis python experiments/v3/intensity_minimum_study.py
```

The machine-readable measurements and input hashes are in
[intensity-minimum-results.json](intensity-minimum-results.json).
