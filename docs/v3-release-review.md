# v3 release and manuscript review

Reviewed on 2026-09-18 against the uncommitted v3.0.0 working trees in the
spectrl and spectrl-paper repositories. This is the final local hardening
checkpoint, not a record of a published release or a completed remote CI run.

Zstandard has since been removed as requested. The final intensity decision is
to retain the current log1p quantizer at scale 3600. Minimum-based alternatives
remain unsupported development experiments and are excluded from the paper
and Supporting Information. See the
[decision and measurements](../experiments/v3/intensity-minimum-decision.md).

The current implemented design is suitable to freeze. No remaining local test or manuscript
gate failure was found. Release preparation is recorded in [the branch handoff](v3-release-preparation.md).
Publication still requires green CI, immutable archival references, and journal
submission packaging.

## Changes made during this pass

- Hardened raw CBOR validation in Python and TypeScript before library decoding.
  Both reject tags, unsafe integers, invalid UTF-8, nonfinite metadata numbers,
  unsupported simple values, and map keys other than integers or text. This
  closes a Python boolean/integer key collision and prevents silent conversions
  from changing document meaning across implementations. The specification now
  states the recursive CBOR restrictions explicitly, including extension data.
- Added 14 shared malformed CBOR fixtures, tested through decoding and inspection.
- Corrected citation and archive descriptions that still described Numpress,
  adaptive pipelines, or per-array compression.
- Expanded the release gate to enforce coverage, JavaScript mutation checks,
  and browser checks in addition to the existing build and installed-package
  checks.
- Excluded historical experiments from the Python source distribution. The
  package archives also omit the removed Zstandard backend.
- Synchronized 167 library, documentation, configuration, and fixture files
  between the two repositories. The recorded hashes are in
  [the synchronization manifest](../experiments/v3/library-sync-clean-core.json).
- Regenerated the paper assets and timing measurements, rebuilt PDF and Word,
  and reran the complete manuscript preflight.
- Added a reproducible same-wrapper container comparison to the paper analysis.

## Verification completed

| Area | Result |
| --- | --- |
| Full local release gate | `just release-check` passed |
| Python 3.14 | 521 tests passed, 84.22% coverage |
| Python 3.12 and 3.13 | 515 tests passed on each, six optional Brotli tests skipped on each |
| TypeScript and Node 24 | All 23 test files passed, type checking and build passed |
| Browser | Seven checks passed, including optional payload backends |
| Decoder mutations | 2,000 inputs per implementation |
| Installed distributions | Clean wheel and npm tarball smoke tests passed |
| mzML bridge | 29 spectra from two input files passed |
| Analysis invariants | 15 tests passed |
| Profile exchange matrix | 1,896 exchanges per direction across 237 spectra |
| Manuscript | Full preflight passed, all 82 computed statistics independently reproduced |
| Bibliography | All 29 DOI records checked against Crossref or DataCite |
| Dependency advisories | No known vulnerabilities reported for audited Python dependencies, JavaScript dependencies, or the demo |
| Synchronization | All 167 recorded files match their hashes and both repository copies |

The profile matrix and complete-file fidelity audit were regenerated after
removing Zstandard. The release gate also reran shared conformance fixtures,
mutation checks, and installed-package checks.

The isolated Python 3.12 and 3.13 environments did not install the optional
Brotli extra. Its tests passed in the full Python 3.14 run. Local testing does
not replace the configured Windows, macOS, and Node 22 CI jobs. Dependency
advisory checks are a point-in-time check, not a security proof.

The rebuilt combined manuscript has 23 PDF pages and 29 Word pages. Seven PDF
pages and six Word pages changed after the payload update and added sensitivity
paragraph. Every changed page was inspected, and all remaining pages were
pixel-identical to the previously reviewed renderings. No clipping or overlap
was found. The spectral-angle figure remains removed and its table remains.
Later figure references resolve to the new numbering.

The abstract contains 181 words, main text 1,291 words, and Supporting
Information 2,054 words under the repository word-count rules. Main-text
Flesch-Kincaid grade is 11.2 and Supporting Information grade is 12.2.

## Design and scientific assessment

Keep the four numeric encodings and the fixed profiles. PSI-MS accessions still
identify scientific array types, numeric types, units, and controlled metadata.
The small encoding identifiers describe representation, not new scientific
identities. Custom namespaced encodings and extension records provide an escape
hatch without requiring every implementation to support every possible codec.

Keep zlib as the default whole-document compressor. There is no demonstrated
need to add gzip as a token mode or restore Numpress. Brotli reduced corpus
totals by about 4.9% for the lossy profile and 4.0% for lossless relative to zlib.
Zstandard has been removed from the format, implementations, package
dependencies, examples, and manuscript. Raw CBOR, zlib, and optional Brotli
remain. Unknown payload modes, including the removed `s` mode, are rejected.
Historical experiment records still describe their tested alternatives.

The 5.46% increase in lossless size is relative to the earlier, broader adaptive
implementation. It is a measured cost of the simpler fixed profile, not lost
data. Searching among the remaining core encodings recovered only 0.425% of
the fixed-profile total in the recorded selection experiment. This does not
justify restoring the old encoder-selection machinery before release.

The complete-file audit covers 4,045 spectra and 3,922,699 peaks. Lossless mode
preserves sorted native array bits. The observed maximum default m/z error is
0.099997993 ppm, within the pointwise 0.1 ppm target. Maximum intensity error is
0.01445% of the source base peak, but 2.4268% of positive input intensity samples
round to zero. This sample-level percentage is not the percentage of spectra
affected. It also does not measure downstream identification or quantification
effects. Keep the explicit disclosure and use lossless mode when weak signals
or exact quantitative values matter.

The container comparison holds raw arrays and modeled metadata fixed. Its
claim is about complete text transport size for this corpus. It does not test
the best achievable compressed mzML representation. The new sensitivity check
gave median savings of 23.65% against gzip-wrapped XML and 23.53% against
zlib-wrapped XML. Spectrl remained smaller for all 237 selected spectra. The
wrapper difference was 16 text characters per XML record. Thus the gzip versus
zlib wrapper choice does not explain the main observed saving.

The sensitivity script and input hashes are recorded in the paper repository:
`paper/analysis/scripts/audit_container_wrappers.py` and
`paper/analysis/reports/container-wrappers.json`. Reproduce it from
`paper/analysis` with `uv run python scripts/audit_container_wrappers.py`.
The sensitivity result is now included in the SI through three declared,
independently recalculated statistics.

The paper's strongest contribution is a defined, self-contained exchange
format with independent implementations. Keep this framing. The present
experiments do not establish a new compression algorithm, universal size
superiority, browser runtime performance, or scientific equivalence of lossy
and lossless data.

## Remaining release and submission actions

1. Review and commit the complete release changes in both repositories. Many
   required v3 files are currently untracked. Confirm that the release snapshot
   includes them, that removed legacy files remain removed, and that the shared
   source hashes still agree. Tag only after the full CI matrix is green.
2. Publish the exact tested packages and archive the matching source and analysis
   snapshot. Add immutable release or archive identifiers to the paper's data
   and software availability statement once they exist. A moving repository
   URL alone does not identify the benchmarked release.
3. Prepare the submission upload set. The current PDF and Word are combined
   review documents with SI appended. Journal of Proteome Research requests SI
   as separate files and requires a cover letter. Adjust the associated-content
   wording for the actual submission and confirm the final authorship, funding,
   disclosures, and archive references with the authors.
4. Resolve optional editorial cleanup by judgment. The preflight warnings are
   unused bibliography entries and declared analysis values, familiar unexpanded
   acronyms, and long SI tables. The tables were visually checked. One DOI audit
   reports `bat009` versus `bat009-bat009` page metadata, which does not indicate
   a wrong reference. Historical experiment reports are retained as provenance
   and are excluded from the package archive.

Do not add more figures or codecs just to expand the release. Removing the
spectral-angle plot while retaining its table is appropriate. A downstream
lossy-data study would add useful evidence for a later paper or release, but it
is not required to support the current, explicitly limited claims.

Journal submission requirements were checked against the
[official author guidelines](https://researcher-resources.acs.org/publish/author_guidelines?coden=jprobs)
on the review date. The Technical Note word and abstract limits leave room for
the current manuscript. No package publication, release tag, archive deposit,
or manuscript submission was performed during this pass.
