# V3 simplification validation

> Historical checkpoint. The final clean core is documented in
> [clean-core-decision.md](clean-core-decision.md).


Completed 2026-09-18. The decision and exploratory alternatives are recorded in
[simplification-decision.md](simplification-decision.md). This report describes
the final implementation, rather than the earlier development candidate pool.

## Implementation

Both Python and TypeScript implement four required numeric encodings: raw typed
words, byte shuffle, modular first differences plus shuffle, and quantized words.
The quantized encoding supports linear or log1p mapping, a scale, a word width,
and optional first differences. The writer verifies reconstructed error bounds.
Unsupported automatic choices fall back to exact encoding. Native integer and
auxiliary arrays remain exact in both default profiles.

Zlib level 6 compresses the complete CBOR document by default. Ordinary output
omits individual array compression. Raw payloads are also required reader
capabilities. Zstandard level 3 and Brotli quality 5 are optional capabilities.
Explicit auto evaluates available backends. Historical Numpress, dictionary,
and individual array compression declarations retain their identifiers and
remain compatibility options. Standard arrays permit optional names, while
nonstandard arrays require names.

## Software checks

- Python: 567 tests passed.
- TypeScript: all 22 test files passed.
- Ruff checks and formatting checks passed for the Python source and tests.
- TypeScript type checking and package build passed.
- Decoder mutation checks processed 2,000 cases per language.
- Browser checks passed all eight tests, including the Brotli WASM path and
  on-demand viewer backend loading.
- Clean wheel and npm package installs passed public API smoke checks.
- Shared vectors exercise all four payload modes and invalid payloads.
- Bounded Brotli decoding includes a regression for pending decompressor output.
- Registry and token examples were regenerated.
- The library sync manifest verifies 139 identical files across the main and
  paper repositories. It records SHA-256 digests in `library-sync-final.json`.

Local execution logs are retained under `/tmp/spectrl-v3-tests-final.log`,
`/tmp/spectrl-v3-js-tests-final.log`, `/tmp/spectrl-browser-final.log`, and
`/tmp/spectrl-clean-install-final.log`.

## Corpus and interoperability

The selected benchmark contains 237 spectra from 42 input datasets. Default and
lossless profiles passed 474 token exchanges in each language direction. The
five payload choices across both profiles passed another 2,370 exchanges in
each direction. Checks compare reconstructed arrays and modeled metadata.

Full fidelity evaluation covered 4,045 spectra and 3,922,699 peaks. The maximum
m/z absolute error was 4.9999999873762135e-6. Maximum intensity error normalized
to the spectrum's base peak was 0.014448639652708296 percent. Lossless arrays
matched normalized source values and native types exactly. Integer and
auxiliary arrays also remained exact in lossy mode.

Of positive source intensity samples, 2.4268036868090417 percent rounded to zero.
No array elements were removed. Log1p quantization has a nonzero absolute error
bound near zero, rather than a strict relative error guarantee. Numerical
fidelity and high spectral similarity do not establish downstream analytical
equivalence or preservation of every weak signal.

## Complete token size

Totals include the complete token text across the same 237 selected spectra.
`final-profile-results.json` records these values and the final paper report's
source hash. `summarize_final_profiles.py` regenerates the comparison.

| Profile | Previous default | Final zlib | Final Brotli | Zlib change |
| --- | ---: | ---: | ---: | ---: |
| Lossy | 5,177,997 | 5,119,808 | 4,899,102 | -1.12% |
| Lossless | 6,815,155 | 7,187,545 | 6,898,695 | +5.46% |

Brotli saves 4.31% for lossy and 4.02% for lossless relative to final zlib.
Zstandard is larger at the measured preset. These results characterize this
selection and do not establish a universal compressor ranking. The simpler
fixed lossless policy accepts a modest size cost to remove the default search
across encoding candidates.

## Paper

The paper now describes the final profiles and uses one common raw-array
representation for the matched CBOR versus mzML container comparison. Its
eight supporting sections retain fidelity, metadata coverage, similarity,
payload compression, and runtime evidence. Historical development reports and
removed figures are archived outside the active publication pipeline.

The generated assets, `just paper`, `just docx`, `just verify`, and
`just check-stats-deep` passed. Deep checking independently re-derived 78 values
from 81 declarations, with three hand-entered values and no errors. Verification
retains nonfatal warnings about unused declarations and style or reference
details. It is not a warning-free build.

| Text | Words | Mean words per sentence | FK grade | Reading ease | Fog |
| --- | ---: | ---: | ---: | ---: | ---: |
| Abstract | 181 | | | | |
| Main | 1,288 | 12.5 | 11.2 | 37 | 14.9 |
| Supporting Information | 1,984 | 11.9 | 12.4 | 28 | 17.3 |
| Main plus Supporting Information | 3,272 | 12.2 | 11.9 | 31 | 16.4 |

Counts exclude references, floats, captions, math, and block code. The abstract
has its own count and is excluded from the total.

The final PDF has 23 pages. The Word export has 31 rendered pages, 11 native
equations, six tables, and ten images. Render review checked page layout,
equations, tables, figures, and the separate table-of-contents graphic. The Word
exporter now preserves explicit page breaks and the manuscript title style.

Artifacts are `spectrl-paper/paper/paper.pdf` and
`spectrl-paper/paper/paper.docx`. Analysis reports retain input and implementation
hashes. The preserved baseline archive and baseline hash manifest distinguish
the previous implementation from the final publication measurements.
