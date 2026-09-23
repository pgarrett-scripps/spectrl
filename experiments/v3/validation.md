# V3 local completion record

Completed locally on 2026-09-17. Nothing was pushed, published, or submitted.
Existing manuscript and corpus work was preserved. Initial checkout snapshots
and diffs are retained in `/tmp/spectrl-v3-start/`.

## Implementation

Python and TypeScript implement the v3 specification, native numeric widths,
independent versioned encoding and compression registries, namespaced custom
operations, adaptive lossless selection, modular delta plus byte shuffle,
dictionary encoding, and exact PSI aliases. Metadata includes selected source,
acquisition, software, processing, nested parameters, and extensions. Unknown
operations can be inspected without running them. Required unknown extensions
and unavailable codecs prevent full decoding. Decoders enforce resource limits.

The required trailing CRC32 covers the preceding ASCII token text. There is no
hash identifier and no v2 reader. CLI, JSON interchange, mzML conversion, demo,
documentation, package metadata, and local service examples use v3.

## Validation

| Check | Result |
| --- | --- |
| Python unit tests | 499 passed |
| Python coverage | 84.26%, above the 80% gate |
| JavaScript test files | 18 passed |
| Decoder mutation checks | 2,000 in each language |
| Browser integration checks | 6 passed |
| Shared pipeline vectors | 36 additional cross-language cases |
| Corpus interoperability | 426 tokens in each direction, 852 checks |
| Full mzML fidelity | 4,021 spectra, 3,867,421 peaks |
| Information-matched mzML re-import | All 213 selected spectra passed |
| Local wheel, npm package, and demo builds | Passed |
| Clean local wheel install and package smoke checks | Passed |
| Registry, version consistency, lint, and formatting | Passed |
| Manuscript `just verify` | Passed, with advisory warnings |
| Manuscript deep statistics check | 89 entries, 86 re-derived, 3 hand-entered, no errors |

Lossless fidelity checks compare normalized native array bytes and supported
metadata. Stable sorting can change source array order. Default lossy encoding
retains the documented Numpress behavior, including rounding some small positive
profile intensities to zero. Real charge-array performance is not claimed.

## Measured compression

The selected corpus contains 213 spectra and 429 numeric arrays, including 162
float32 and 267 float64 arrays. Adding the two modular-delta candidates to the
tested adaptive PSI lossless pool, including dictionary encoding, reduced total
token bytes by 24.6%. Payload savings were 44.3% for m/z and 0.5% for intensity.
Dictionary support separately reduced total token bytes by 4.4% relative to the
same adaptive policy without dictionary. These are corpus results, not universal
guarantees. Only three real additional mobility arrays were available.

The controlled container comparison fixes raw arrays plus zlib and preserves the
same supported context in both formats. spectrl was smaller than equivalently
framed gzip mzML for 188 of 213 spectra. Median savings were 6.8% across the corpus
and 12.1% for centroid DDA MS2. Uncompressed context made 25 tokens larger.

Reports with source and input hashes are in the paper checkout under
`paper/analysis/reports/`. `library-sync.json` records identical synchronized
implementation files in the two checkouts. Analysis instructions are in
`paper/analysis/README.md`.

## Manuscript

The Technical Note format and four main figures are retained. A new compression
figure and supplementary pipeline, subgroup, and metadata-overhead tables report
the final v3 implementation. The matched mzML baseline includes selected context.
The detailed spectral-similarity figure is in Supporting Information.

Local outputs are `~/Repos/spectrl-paper/paper/paper.pdf` and
`~/Repos/spectrl-paper/paper/paper.docx`. Both include the Supporting
Information. Figures and tables are generated from scripts. The Word export
contains native editable equations. Rendered documents were visually checked.

Final reported prose counts are 212 abstract words, 1,565 main-text words, and
1,725 Supporting Information words. Flesch-Kincaid grade is 13.5 for the main text
and 12.7 for Supporting Information. Advisory manuscript checks include unused
registered assets or statistics and editorial repetition. They do not prevent
the consistency gate from passing.
