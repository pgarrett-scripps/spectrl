# Local validation of the PSI-MS submission draft

No GitHub fork, branch push, PR, issue, or comment has been created for this
submission. Publishing requires explicit user approval.

## Scope

The patch targets HUPO-PSI/psi-ms-CV base revision
`1126bd88dc13ddd8ef3902c36952eddedf6e6c65`.
It changes only `psi-ms.obo` and adds two supporting documents under `docs`.
The generated `psi-ms.owl` is unchanged.

`MS:1004013` is a provisional identifier for review. It is absent from the
checked base vocabulary and the pending OBO patch excerpts inspected on
2026-09-17. It must be rechecked before submission and may be reassigned by
maintainers. The version and date must likewise be refreshed if the base moves.

## Completed checks

- Parsed the complete proposed OBO with fastobo 0.14.1.
- Checked identifier uniqueness and the new term's `MS:1000572` parent.
- Passed upstream `scripts/check_sorted.py`.
- Passed upstream `scripts/check_version_uprev.py` against a local copy of the
  exact base revision. Version increases from 4.1.261 to 4.1.262.
- Executed both Python code blocks from the proposed specification.
- Passed all eight raw/transform/zlib conformance vectors.
- Passed 14 additional random bit-pattern round trips at both word widths.
- Passed 12 malformed-stream, length, width, and budget rejection cases.
- Confirmed all eight copied vectors match both the existing Python-generated
  and JavaScript-generated spectrl vectors.
- Passed `git diff --check` in the local upstream checkout.

## Limits

GitHub CI has not run because nothing has been submitted. The containerized
`fastobo-validator` and OWL validation workflows have not been run locally.
The checks above do not claim full ontology semantic validation. An unrelated
existing subset-definition correction is pending upstream in PR #556.

The compression-size table is derived from the existing local benchmark rows.
No corpus data or internal filesystem paths are included in the proposed PR.
The PR description explicitly identifies the measurements as exploratory and
does not claim that this patch supplies the corpus needed to reproduce them.
