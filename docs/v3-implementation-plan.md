# V3 implementation and paper plan

> Historical design notes. The final clean core supersedes the compatibility
> proposals below. See [SPECIFICATION.md](../SPECIFICATION.md) for the
> format as shipped.


Historical design record. The current defaults and supported core are defined in
[SPECIFICATION.md](../SPECIFICATION.md).

Status: completed locally on 2026-09-17. All eight steps below are implemented
and validated. The [validation record](../experiments/v3/validation.md) records
the final checks, benchmark findings, and manuscript outputs.
Everything remains local. No pushes, issues, pull requests, releases, package
publication, or manuscript submission are part of this work.

The [scope decision](v3-design.md) defines the product. V3 is the only supported
wire format. There is no v2 reader, writer, migration layer, or compatibility gate.
The paper presents spectrl using v3 as its initial described format.

## 1. Preserve the working state and establish the source of truth

The implementation lives in `~/Repos/spectrl`. The paper lives in a separate
checkout at `~/Repos/spectrl-paper/paper`, whose analysis currently imports
the library from its own repository root. Its JavaScript analysis also uses that
checkout's `js` build. Existing manuscript and corpus work includes staged and
unstaged changes and must survive this update.

- Record local diffs and the relevant untracked-file inventory before modifying
  implementation or manuscript files. Preserve current corpus selection and assets
  as a comparison baseline without deleting or resetting changes.
- Develop the authoritative Python and TypeScript implementation in `spectrl`.
- After implementation validation, synchronize a reviewed allowlist of library,
  schema, vector, test, build, and package files into `spectrl-paper`. Preserve its
  `paper` directory and independently edited files. Inspect collisions individually.
- Record source hashes and verify that both paper runtimes use the same validated
  v3 code. Do not let an old installed package or stale `js/dist` drive the results.

Deliverable: reproducible local inputs and one identified implementation revision
for every later benchmark and manuscript asset.

## 2. Specify the wire contract before implementing it

Update `SPECIFICATION.md` and the machine-readable registry together. They must
define enough detail for two independent implementations to agree.

- Keep URL-safe CBOR framing and the corruption checksum, with `spectrl.v3` magic.
- Assign compact structural keys, built-in encoding/compressor IDs, and exact
  meanings of revision and parameter fields. Namespaced custom IDs use the same
  contracts without requiring PSI allocation.
- Specify raw, shuffle, dictionary, modular delta plus shuffle, and Numpress byte
  layouts, including endianness, dtype eligibility, empty arrays, numeric domains,
  fixed-point handling, and inverse operations. Specify compressor framing.
- Define a PSI alias table only for exact matching pipelines, plus a mandatory
  raw and none/zlib decoding baseline for portable v3 exchange.
- Finalize parameter records, including repeated accessions, strings, units, nested
  user parameters, and separation of codec fields from scientific array metadata.
- Define source, acquisition, and processing records, their inheritance at scan
  and array scope, and the distinction between source and current-array summaries.
- Specify exact/lossy declarations and descriptive peak-selection records. Unknown
  history is not equivalent to an unprocessed acquisition.
- Define extension preservation, required-feature handling, and invalidation after
  array mutation. Bound token, metadata, array, and intermediate decoded sizes.
- Keep existing stable m/z sorting, numeric widths, and finite-value validation.
  Do not introduce a built-in hash ID.

Deliverable: concrete specification, registry, and hand-reviewed small examples.
Provisional examples must be replaced by the actual encoding before release.

## 3. Implement the Python reference and shared vectors

Update `model.py`, `header.py`, `cbor_format.py`, `token.py`, `serialization.py`,
`peaks.py`, `introspection.py`, and the codec modules as one consistent v3 API.

- Preserve native float32, float64, and int32 through input, JSON, encoding, and
  decoded output. Declare actual reconstructed types for lossy encodings.
- Introduce encoding and compressor registries with parameter validation, explicit
  registration, revision dispatch, and bounded decode contracts.
- Promote the tested modular-delta implementation and the experimental dictionary
  implementation into supported codecs after validating their contracts.
- Add adaptive selection by complete serialized cost, including descriptors and
  parameters. Retain explicit overrides and a portable candidate restriction.
- Preserve source/acquisition/processing metadata and extension payloads through
  ordinary forwarding. Provide useful inspection without executing unavailable codecs.
- Replace legacy vectors with v3 vectors and targeted malformed-input cases. Include
  independent hand-calculated transforms and a toy custom codec round trip.

Deliverable: working Python v3 with meaningful codec, schema, and fidelity tests.

## 4. Implement TypeScript and prove interoperability

Port the same contracts to `js/src`, keeping registration explicit and Zstandard
initialization compatible with browser and Node use. Update typed-array APIs,
JSON interchange, metadata, inspection, extensions, and codec errors.

Validate Python-produced tokens in JavaScript and JavaScript-produced tokens in
Python. Different compressed bytes are acceptable when both implementations
recover the declared values and metadata. Tie-breaking rules are deterministic
within a given candidate result set.

Cover empty arrays, dtype boundaries, negative intensities, signed zero, small and
large arrays, malformed/truncated streams, dictionary boundaries, unknown revisions,
unavailable custom codecs, and decode-budget enforcement. Reject v2 magic clearly.

Deliverable: passing bidirectional vectors, unit tests, type checking, fuzz checks,
and package builds in both languages.

## 5. Finish mzML conversion and end-user workflows

- Extend the bridge to accept run context and resolve defaults plus explicit
  spectrum, scan, and array overrides. Include selected instrument components and
  software/version details for known processing steps. Report unresolved context.
- Preserve precursor source references, nested parameters, and referenced user
  parameters. Do not recursively import precursor spectra or complete run inventories.
- Update `top_n`, `fit_to_budget`, and transcoding to retain known processing facts,
  record selection and omissions, and handle source-derived summaries correctly.
  All new fields count toward budget checks.
- Update quality reports, CLI, JSON, demo metadata display, URL helpers, examples,
  registry generation, and documentation. Viewer exports use recovered values.
- Make unknown-codec messages actionable. A custom implementation is installed by
  the application, never fetched or executed from token content.
- Set package metadata to 3.0.0 and update lockfiles, citation metadata, build checks,
  demo tokens, and service examples. Retain historical project records as history,
  while active instructions describe only v3.

Deliverable: a complete browser and command-line round trip using local v3 builds,
with real mzML input and no silent metadata or peak loss.

## 6. Rebuild the benchmark on the final implementation

Use the existing pinned corpus and representative selection. Recompute source
models with native dtypes and the new conversion rules. Extend fidelity checks to
every supported metadata field, and keep full-corpus validation separate from the
representative size/timing sample. Synthetic edge cases establish correctness,
not performance on real instrument populations.

Separate three comparisons:

| Question | Controlled comparison |
| --- | --- |
| Which array encodings help? | Identical arrays and dtype across raw zlib, raw Zstandard, shuffled Zstandard, dictionary, modular delta, and adaptive selection |
| How compact is the container? | Identical metadata and PSI-supported codec payloads in spectrl and an information-matched mzML representation |
| What does a user gain overall? | Complete v3 tokens under documented lossless and lossy policies, with actual descriptor, context, history, checksum, and transport overhead |

The current `_mzml_baseline.py` writes a PSI compression accession for every
reused token blob. It cannot represent the custom delta pipeline as standard
mzML. Rewrite that comparison so a common supported pipeline is explicitly pinned.
If context needs document-level definitions, include those records in a minimal
single-spectrum mzML document and validate the references. Restrict the matched
comparison to information representable on both sides and disclose the scope.
Do not assign a fake PSI term or silently omit context to make a baseline work.

For codec results, report m/z and intensity separately, with profile/centroid and
dtype breakdowns. Show payload sizes and complete token sizes separately. Include
the tested PSI lossless pool with dictionary support as the meaningful competitor.
Use an ablation that adds modular delta to the same pool, so its marginal benefit
is isolated. Measure native-dtype effects separately from transform effects.

Report both per-spectrum distributions and aggregate bytes. Large profile spectra
must not conceal different behavior on short centroid spectra. Mobility results
remain descriptive with the present small sample. Do not make real-charge claims
from synthetic data. The exhaustive PSI experiments belong in supplementary results
with lossless and lossy methods separated by fidelity and error.

Measure encoding and decoding with warm-ups and repeated trials in Python and
JavaScript. Include candidate-search cost in adaptive encoding. Separate optional
backend initialization from steady-state runtime. Report browser measurements as
browser measurements, not inferred from Node timings. Keep nondeterministic timing
collection outside deterministic figure regeneration.

Deliverable: fresh reports with code/data hashes, runtime versions, settings,
correctness checks, and registered asset/statistic generators. Earlier exploratory
compression percentages do not become v3 paper claims without rerunning them.

## 7. Keep the paper format and revise its figure story

Keep the current Technical Note structure, visual style, and four main figures.
Present the format and measured implementation directly, without a v2 migration
narrative. The compression techniques have prior art. The contribution is their
specified, extensible integration into a portable spectrum representation and the
measured tradeoffs, not invention of modular delta or byte shuffling.

| Figure | Decision and content |
| --- | --- |
| 1. Format and decoding | Redraw the existing structure figure for v3. Show one concrete spectrum, independent encoding/compression, and optional source/acquisition/processing context. Include a small forward/inverse pipeline panel. |
| 2. Encoding tradeoffs | New main figure. Panel A compares lossless payload sizes separately for m/z and intensity. Panel B shows complete-token gains when dictionary and modular delta enter the same candidate pool. Panel C shows encoding and decoding cost for the tested policies. |
| 3. Container overhead | Keep the existing size-reduction question, regenerate with the corrected information- and codec-matched comparator. Make the controls explicit in the caption. |
| 4. Sharing limits | Keep token length versus peak count and URL/QR thresholds, regenerate from final v3 output. Report the metadata policy used and do not promise universal carrier compatibility. |

Move the current detailed reconstruction/residual and spectral-similarity figure
to the Supporting Information. Keep exactness and lossy-quality results summarized
in the main text, with references to those plots. Update the graphical abstract to
the final format. Do not add a separate main figure just for optional metadata.

Supplementary material carries the complete codec/parameter matrix, representative
token anatomy, conformance and metadata-coverage tables, expanded timings,
per-dtype and acquisition-group results, mobility limitations, and the complete
PSI sweep where relevant. Add a compact metadata-overhead comparison there.

Rewrite methods, scope, results, availability, abstract, and captions against the
validated implementation and regenerated numbers. Update examples and limitations
to cover custom-decoder availability and known sharing transformations.

## 8. Regenerate and validate locally

Follow the manuscript's `AGENTS.md` and generator contracts. Change scripts and
declarations, never generated figure or table files by hand. Register new results
through `gen_stats.py`, `stats.json`, and `assets.json`. Preserve existing author
formatting, descriptions, guards, and unrelated manuscript work.

Run appropriate library tests, coverage, fuzzing, browser checks, clean-install
smoke checks, local distribution builds, version consistency, and registry/vector
generation. Ensure release tooling does not publish anything.

After source synchronization and fresh timing reports, run the analysis and asset
pipeline, then `just paper` followed by `just verify`. Run the deeper statistic
regeneration check, rebuild Word output, and inspect rendered figures and document
layout. Report the actual word count and readability output. Verify that no stale
v2 result, old example token, or obsolete format claim remains in active prose.

Completion means validated local Python and JavaScript packages, a working demo,
the final v3 specification and vectors, reproducible reports and figures, and
rebuilt PDF and Word manuscripts. Publication is a separate future action.
