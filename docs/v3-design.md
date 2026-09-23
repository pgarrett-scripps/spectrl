# spectrl v3: scope grounded in the project

> Historical design notes. The final clean core supersedes the compatibility
> proposals below. See [SPECIFICATION.md](../SPECIFICATION.md) for the
> format as shipped.


Historical design record. The current defaults and supported core are defined in
[SPECIFICATION.md](../SPECIFICATION.md).

This is the recommended v3 scope after reviewing the README, service integrations,
browser workflow, conversion code, data model, paper, and existing benchmark inputs.
It supersedes the earlier exploratory scope lists. This is a design decision,
not an implemented format. GitHub publication remains on hold.

## Product boundary

Spectrl carries one spectrum between people and programs without requiring its
original file or a server. A recipient must be able to recover its arrays,
interpret the measurement, and see known changes made for sharing. Context is
selected according to its relevance to that spectrum, regardless of where mzML
stores the information.

The concrete workflows are a spectrum in a document or issue, a browser viewer,
a notebook export, and an application or service handoff. A bare peak list must
remain a valid input. Optional metadata means the information may be unavailable.
When supplied, standard metadata needs defined semantics and preservation in both
implementations. Optional does not mean unspecified or unimplemented.

## What the review found

The metadata audit reused the 127-spectrum,
40-dataset selection from the codec benchmark and verifies its input file hashes.
It inventories metadata presence, not full mzML reconstruction fidelity.

- All 127 selected spectra have resolvable instrument and processing references.
- 113 have instrument component descriptions through their selected configurations.
- 38 have precursor spectrum references that the v2 model does not carry.
- 15 have user parameters in modeled nested locations that v2 omits.
- 104 of 257 source arrays are declared float32. The current core-array model
  promotes numeric input to float64.
- `fit_to_budget` reports removed peaks to the calling application, but does not
  record that selection explicitly inside the token. `top_n` retains source
  spectrum parameters, including any summaries that may describe the full input.

A synthetic v2 probe confirmed both core
float32 promotion and retention of a source TIC of 6 after keeping one peak whose
intensity is 3. The latter needs a defined source-versus-current scope, not an
assumption that every inherited summary describes the reduced arrays.

The audit script defined the exact counting
rules. Relevant implementation evidence is in [the mzML bridge](../src/spectrl/mzml.py),
[models](../src/spectrl/model.py), [sharing workflows](../src/spectrl/workflows.py),
and [parameter serialization](../src/spectrl/header.py).

## Included in v3

### 1. Extensible encoding and compression

Separate the typed-array encoding from byte compression. Each has a stable
identifier, wire revision, and validated parameters. Built-ins use compact
spectrl IDs. Custom operations use namespaced identifiers and locally registered
implementations. Codec data and dictionaries needed for decoding are embedded.

PSI-MS compression accessions remain aliases for exact matching pipelines.
Scientific array identities, metadata, and units retain PSI-MS and UO semantics.
Unassigned PSI accessions are not used. Codec registry additions do not require
another format version.

Initial encodings are raw, byte shuffle, dictionary, modular delta plus byte
shuffle, and existing Numpress methods. Compressors are none, zlib, and Zstandard.
Adaptive lossless selection operates independently per array. Fix the default
candidate pool only after measuring complete token size and runtime. Default
lossy behavior retains existing Numpress policies during this change.

### 2. Faithful arrays and measurement metadata

Preserve float32, float64, and int32 in the Python and JavaScript core and auxiliary
array APIs, JSON interchange, and tokens. Keep stable ascending m/z ordering and
apply the same permutation to every parallel array. Exact codec fidelity is
relative to those normalized input arrays, not to an unavailable raw acquisition.
Lossy modes declare their actual reconstructed dtype and never imply preservation
of a source dtype that their selected encoding does not retain.

Keep all existing spectrum, scan, precursor, product, and auxiliary-array support.
That includes MS level, polarity, centroid/profile state, retention time, scan
windows, precursor m/z and charge, isolation windows, activation and energy,
scalar and per-peak mobility, and units. Known fields need not be supplied for
manually constructed spectra.

Close the existing metadata gaps: preserve user parameters at modeled nested
locations, preserve reference-group CV and user parameters when resolving them,
allow repeated CV accessions through an unambiguous representation, and retain
non-encoding array parameters. Preserve parameter strings and units without
blind numeric coercion that changes their meaning. Encoding descriptors remain
separate from scientific metadata so conflicting codec declarations are rejected.

### 3. Optional source and acquisition context for this spectrum

Support native spectrum IDs with optional source identity, an existing external
identifier such as a supplied USI, and a source checksum when supplied. Preserve
precursor source references. These are provenance and never required to decode
embedded arrays. Do not invent a source identity or a new spectrum hash.

Include an optional acquisition snapshot: instrument model and the relevant
ordered source, analyzer, and detector components, with their CV and user
parameters. Respect a selected scan's actual instrument configuration. An inherited
spectrum context and explicit scan overrides can represent combined scans.

Include known processing steps relevant to the selected spectrum or array, with
parameters, software identity, and version. This covers such information as peak
picking, filtering, calibration, and conversion. Source metadata may describe
only part of the processing history. Absence means unknown, never unprocessed.

Resolve applicable run/list defaults and explicit scan/spectrum/array references
on import. Embed the selected definitions as small nested records. V3 does not
need copies of complete software, instrument, or processing inventories or a
public run-wide reference graph. Reusing inline records can be optimized later
if complete-token measurements justify it.

These semantics follow the selected-record relationships in the
[mzML schema](https://raw.githubusercontent.com/HUPO-PSI/mzML/master/schema/schema_1.1/mzML1.1.0.xsd).
This is real implementation work in scope: an importer accepting run context,
reference resolution, typed models, serialization, and reader support. Importers
report missing context and do not guess from unrelated records in the file.

### 4. Record what sharing changed

Separate per-array codec fidelity from changes to the supplied spectrum. Existing
Numpress parameters remain explicit. The encoder may supply measured error
statistics when it possesses the reference input, with the reference and metric
clearly defined. A decoder cannot measure original-data error from a token alone.

When spectrl removes peaks, record the selection method, input and retained peak
counts, and its parameters in the token. Preserve earlier known processing facts
when recompressing. Recompression cannot erase evidence of prior trimming or
known lossy conversion. A compact token may itself be exactly encoded while
representing a selected subset.

When a transform changes array-derived summaries, the produced spectrum must not
silently present stale TIC, base-peak, or range metadata as summaries of the
current arrays. Recompute only summaries whose meaning and units are defined
and derivable, or preserve them with an explicit source scope. Record explicitly
requested metadata omissions. All bookkeeping bytes count toward a share budget.

This is descriptive history, not an executable workflow or a promise that the
original acquisition can be reconstructed. Default encoding never selects peaks
or removes metadata without explicit caller instruction.

### 5. Extensibility and interoperability

Add namespaced, versioned extension containers with required/optional semantics.
Unknown optional data survives unchanged document forwarding. Unsupported required
features prevent successful full interpretation. Array mutations must explicitly
handle potentially invalidated unknown extensions, rather than blindly copying
peak-dependent content after sorting or trimming.

Expose required codec capabilities during inspection, allow metadata inspection
with opaque blobs, and fail full decoding clearly when a codec is unavailable.
Define a small mandatory decoding baseline of raw encoding and none/zlib
compression. Register optional implementations explicitly in each runtime.

Implement v3 as the only supported wire format, as requested. Remove v2 reading,
writing, compatibility branches, and migration requirements. Unsupported older
tokens fail with a clear version error. Compatible-codec selection still matters
between v3 applications with different registered implementations. Library release
versioning and wire versioning are separate.

## Excluded from v3

| Feature | Reason |
| --- | --- |
| A built-in content hash, source-array hash, or similarity ID | Current handoff workflows need no new identity protocol. Applications can compute indexes externally or define an extension. Keep the corruption checksum. |
| Whole mzML headers, full run reconstruction, acquisition schedules, or complete file inventories | The payload represents a selected spectrum. Relevant source, instrument, and software information is extracted into its context. |
| Sample preparation, study design, contacts, and repository management | These require experiment-level models. Existing generic parameters can retain simple supplied values. |
| Peptide/compound identification and fragment-assignment schemas | These have distinct interpretation and alignment rules. Applications retain ownership, with extensions available. |
| Multiple spectra, chromatograms, imaging cubes, external coordinate grids, or independently sized axes | These require a broader data model than parallel arrays for one spectrum. |
| New numeric widths, changed peak-order defaults, and non-finite value support | No demonstrated requirement from the current corpus or workflows. Preserve existing validation boundaries. |
| New lossy algorithm research and a general tolerance-search optimizer | Codec registration and parameter schemas allow later additions. Existing quality reports support informed selection now. |
| A default exhaustive exact-recovery search over normally lossy methods | It adds encode/decode cost that needs a separate performance case. The fidelity contract can accommodate verified candidates later. |
| Signing, authentication, resolver services, and embedded executable codecs | These belong to the host application or introduce dependencies outside the token contract. |

## Release acceptance

V3 is complete when Python and JavaScript share positive and malformed-input
vectors for the new descriptors, types, metadata, extensions, and fidelity rules.
Verify source context and nested-parameter
preservation on the audited corpus and purpose-built multi-scan and reference
fixtures. Verify that trimming disclosures and current-array metadata survive
sharing and transcoding. Benchmark size and time by array type, including native
float32 input, short tokens, and bounded browser decoding.

The [payload illustration](v3-payload-example.md) follows this scope. Exact CBOR
key assignments are implementation design, not additional product scope.
The [implementation and paper plan](v3-implementation-plan.md) defines the work
sequence and benchmark comparisons. The paper will describe v3 as the initial
format being presented, rather than narrating a migration from v2.
