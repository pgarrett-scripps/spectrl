# v3.0.0 release preparation

The original release candidates were merged into `main` in both repositories:

- [Software merge snapshot](https://github.com/pgarrett-scripps/spectrl/commit/a461435831962782016d3d62fd7970e71c883c8c)
- [Paper merge snapshot](https://github.com/pgarrett-scripps/spectrl-paper/commit/bfae40bd9c1c22bd9f7c41a6e39f95c3f6440acf)

These snapshots do not create a release. Pushes run CI. Package publication is
triggered separately by the Publish workflow, and the existing Pages deployment
runs on main. Do not dispatch Publish during branch review.

## Frozen design

Frozen as of the merge snapshots above, with one later addition: header key 12
`cv_versions`, which records the source-declared ontology version for each
accession prefix. It is optional and informational, and v3 was not yet released
when it landed. See `SPECIFICATION.md` section 2 and the changelog.

- Package version 3.0.0 and spectrl.v3 framing.
- Four core numeric encodings and PSI-MS scientific identities.
- Whole-document zlib by default, with raw and optional Brotli alternatives.
- Fixed lossless policy, pointwise 0.1 ppm default m/z bound, and log1p
  intensity quantization at scale 3600, refined from the smallest positive
  intensity only when it is below 1 (2026-09-22) so normalized spectra keep
  their small peaks. Spectra with intensities of 0 or at least 1 are unchanged.
- Other minimum-based intensity alternatives are unsupported historical
  experiments. They are absent from the paper and Supporting Information.

The specification, generated registry, implementations, and shared fixtures are
included in the branch. The paper branch contains the manuscript sources,
analysis, generated figures and tables, reports, compact fixtures, and pinned
corpus manifest. PDF and Word outputs remain local build artifacts as defined
by the paper repository. Downloaded public inputs and dependency caches remain
ignored and are reproducible from their manifests and lockfiles.

## Checks before merging

From the software repository, run `just release-check`. CI covers Python 3.12,
3.13, and 3.14 on Linux, Python 3.13 on macOS and Windows, Node 22 and 24,
package builds, installed-package checks, mutations, and browser regression
checks. Python CI installs the Brotli extra so optional tests are exercised.
The full-token parity job compares live Python and JavaScript writers on the
supported operating systems. Shared raw-token fixtures additionally pin writer
output in both test suites. See [token reproducibility](token-reproducibility.md)
for the measured agreement and portable guarantee.
Require green checks on the branch revision you intend to merge.

The shared-source manifest lives in `experiments/v3/library-sync.json`. The paper repository deliberately
has an additional `reproduce-paper` recipe, so its root justfile is not listed
as byte-identical.

From the paper repository, `just reproduce-paper` fetches pinned public inputs,
regenerates the analysis, builds PDF and Word, verifies freshness, and independently
recalculates statistics. From `paper/`, `just preflight` rebuilds both documents
and runs verification, deep statistics, and the online bibliography audit.
Follow `paper/README.md` for deliberate timing remeasurement and update the host
description if the measurement environment changes.

## When ready to release

1. Review and merge the prepared branches. Recheck CI on the final software
   commit and retain the corresponding paper commit as the analysis snapshot.
2. Run the release gate on the intended software commit. Verify all release
   metadata still agrees on 3.0.0 and use the matching `v3.0.0` tag.
3. Create the software release only when ready to publish. Confirm the PyPI and
   npm publishing environments and trusted publishing configuration are ready.
   Those external permissions are not established by local tests.
4. Archive the matching software and analysis snapshots. Add their immutable
   identifiers to the manuscript availability statement once assigned.
5. Prepare separate journal manuscript and Supporting Information uploads,
   a cover letter, and final author approval. The combined PDF and Word are
   review outputs, not a complete journal submission bundle.

No tag, package publication, GitHub release, merge, or journal submission is
part of this branch-preparation step.
