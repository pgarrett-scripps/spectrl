# Clean v3 numeric core

The pre-release format has no deployed compatibility requirement. This decision
supersedes the compatibility provisions in earlier design notes.

The required numeric encodings are raw words (0), byte shuffle (1), modular delta
plus shuffle (2), and quantized words (3). The quantized representation supports
linear and log1p mappings, an explicit scale and word width, and optional modular
differences. Callers can register a namespaced custom numeric encoding with a
revision and parameter map. Unknown encodings can be inspected but not decoded.

Remove Numpress, dictionary encoding, PSI codec aliases, per-array compression,
and custom compressor registration. Descriptor key 3 is invalid. Old development
tokens are unsupported. Scientific PSI-MS metadata remains. Numpress support in
the external mzML reader is an input-file capability, not a spectrl encoding.

Zlib-compressed CBOR remains the default. Raw CBOR supports inspection and small
payloads. Optional Brotli compresses the same whole document. Zstandard was
removed before release.
Explicit auto selects the shortest available complete token. Numeric encoding
and document compression remain independent without a general pipeline language.

The exact default remains modular delta plus shuffle for m/z, byte shuffle for
intensity, and raw words for auxiliary arrays. Lossy defaults use the shared
quantizer with a pointwise 0.1 ppm m/z bound and log1p scale 3600 for intensity.
The m/z logarithmic scale is calibrated from the smallest positive source value.
Zeros remain exact.
Bounds are checked after reconstruction. Automatic invalid choices fall back to
exact encoding. Integer and auxiliary arrays remain exact by default.

The final intensity decision retains log1p scale 3600. Minimum-based alternatives
were evaluated and not adopted. Their
[development record](intensity-minimum-decision.md) remains in the repository,
outside the supported format, paper, and Supporting Information.

## Why keep fixed lossless defaults

The reproducible `core_selection_study.py` compares the final core encodings on
237 selected spectra. `core-selection-results.json` records each spectrum.

| Lossless selection policy | Complete zlib token characters |
| --- | ---: |
| Fixed default | 7,187,540 |
| Best independently compressed descriptor per array | 7,157,055 |
| One coordinate pass minimizing the complete compressed document | 7,156,979 |

The full-document search saves 0.425% in aggregate and needs repeated trial
compression. It is a greedy single pass, not an exhaustive optimum. Its gain over
the cheaper descriptor estimate is just 76 characters across the selection.
Do not add automatic selection to the default for this result. Explicit encoding
choices retain flexibility for applications with different data.

The earlier 5.46% increase compared fixed exact output against a broader adaptive
pool that included dictionary encoding and per-array compressors. Removing those
choices does not itself recover that difference. Restricting adaptation to the
small core recovers less than half a percent in this selection. Exact output still
preserves native numeric bits. The size change is a representation tradeoff,
not a loss of fidelity.

`final-profile-results.json` records fresh complete-token totals for all outer
compressors and both profiles. `clean-core-validation.md` records acceptance
checks. Historical experiments retain their original measurements and require
their archived source snapshots.
