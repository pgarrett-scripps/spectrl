# V3 simplification and paper plan

> Historical design notes. The final clean core supersedes the compatibility
> proposals below. See [SPECIFICATION.md](../SPECIFICATION.md) for the
> format as shipped.


Implementation plan from the September 18 discussion and supplied chat.
The selected design is now implemented. See
the encoding decision for the
measured tradeoffs and final validation record. The earlier implementation plan and validation record remain a
record of the previous local milestone, not evidence for this proposed design.

**1. Settle the product shape now**

The product remains a self-contained, URL-safe representation of one spectrum.
The paper should establish fidelity, interoperability, practical size, and basic
runtime. It should not read as a search for the best general compression method.

- Expose two fidelity profiles: lossless and lossy. Retain lossy as the default
  while its final numeric policy is evaluated.
- Default to zlib-compressed CBOR. Do not automatically switch a default call to
  raw CBOR merely because the token is shorter.
- Define outer payload encodings `r` for raw, `z` for zlib, `s` for Zstandard,
  and `b` for Brotli. Require readers to support `r` and `z`. Make `s` and `b`
  optional capabilities with explicit errors when unavailable.
- Offer explicit `auto` outer compression as a writer option. Compare complete
  token lengths across available supported encodings and write the actual
  winning encoding in the token. Define a stable tie order with `z` first.
  An explicitly requested unavailable compressor must fail rather than fall back.
- Use one documented setting per compressor. Proposed spectrl presets are
  zlib level 6, Zstandard level 3, and Brotli quality 5. Describe these as spectrl
  presets, not universally identical library defaults. Record library versions.
- Keep base64url and the corruption checksum.
- Preserve the current scientific metadata scope, numeric widths, stable peak
  ordering, custom arrays, extensions, and processing history. Keep optional
  names on standard arrays, which have already been implemented locally.

Use the term payload compression consistently. Fidelity and payload compression
are independent API choices. No new default behavior should silently remove
peaks or metadata.

**2. Distinguish established results from hypotheses**

The current wire format already uses spectrl operation identifiers. PSI codec
accessions are API aliases, not a requirement to implement every PSI pipeline.
Scientific PSI terms for array identity and metadata serve a different purpose
and should remain.

S9 added experimental quantizers to an existing candidate pool. At the middle
budget, selected m/z payloads shrank about 2.7%, intensity payloads about 17.1%,
and complete tokens about 7.6%. This supports testing a replacement, but does
not show that removing Numpress would retain those gains.

S9 used absolute m/z error and intensity error relative to each spectrum's base
peak. It did not establish a per-value relative-error method or a ppm policy.
Base-peak-relative bounds permit weak positive intensities to become zero.

Numpress linear rounds to a fixed grid and encodes prediction residuals. It does
not optimize each value's permitted rounding error to minimize final token size.
Logarithmic SLOF rounding is not automatically equivalent to a strict per-value
relative-error guarantee, particularly close to zero.

Existing compressor results used already encoded and compressed array blobs.
They cannot establish the best compressor for a new document containing
transformed but uncompressed arrays. All production claims need fresh results.

**3. Run one bounded design experiment before changing the wire contract**

First preserve local changes, the selected corpus, reports, and generated assets
as a reproducible baseline. Record hashes for the current working source, not
just the Git commit, because both checkouts contain uncommitted work.

Use the current pinned corpus and retain metadata, native widths, ordering, and
peak counts. Do not substitute the older corpus counts in historical notes.
Report aggregate token size and per-spectrum distributions, broken down by
centroid/profile, MS level, native dtype, and array role. Sparse auxiliary-array
coverage cannot support general rankings.

Conduct the experiment in this order, rather than an exhaustive cross-product:

| Comparison | Hold fixed | Decision it answers |
| --- | --- | --- |
| Per-array plus outer compression versus outer compression alone | Numeric transforms, metadata, zlib preset, fidelity | Can we remove per-array byte compression? |
| Current adaptive exact policy versus a small fixed policy | Final outer compression and native-bit fidelity | Can the lossless default stop searching many pipelines? |
| Numpress versus simple quantized representations | Explicit measured error budget, outer zlib, metadata | Can a small replacement support the lossy default? |
| Raw, zlib, Zstandard, Brotli, and auto | The selected final array policies | What do the transport options cost and save? |

For the fixed lossless policy, begin with modular delta plus byte shuffle for
m/z and raw typed words for other arrays. Include byte shuffle for intensity as
one focused alternative. Test the combined policies using complete tokens.

For lossy m/z, compare Numpress linear, absolute quantization plus first-order
delta, and the same quantization plus second-order prediction residuals. Specify
the residual representation, signed-value handling, integer width, rounding,
overflow rules, and inverse before comparing sizes. Use the existing absolute
budgets as experimental settings, not recommended scientific tolerances.

For intensity, compare the current default SLOF baseline and a tuned Numpress
baseline against uniform quantization plus byte shuffle. Evaluate matched bounds
and report infeasible cases with exact fallback. Do not spend the entire design
effort on m/z when intensity supplied most of S9's incremental savings.

Defer a new ppm or per-value relative quantizer to a separate experiment unless
the tested simple candidates fail the product requirements. If introduced,
define treatment of zero and negative inputs, error denominators, and the
actual floating-point reconstruction guarantee in both runtimes.

Measure complete token bytes including descriptors, parameters, context, framing,
and checksum. Payload-only savings are diagnostics. Independent smallest-array
choices need not produce the smallest outer-compressed document.

Deliver one decision report with a recommended fixed lossless policy, a
recommended fixed lossy policy, and the measured cost of eliminating per-array
compression. Prefer fewer algorithms when the size tradeoff is acceptable.
Do not introduce more candidates merely to chase a smaller aggregate number.
If a simple replacement does not hold up, retain Numpress and simplify its API.

**4. Freeze the wire design after that decision**

The preferred architecture to test is:

```text
numeric arrays
    -> optional precision reduction
    -> reversible numeric representation
    -> CBOR with metadata
    -> one outer compressor
    -> base64url and checksum
```

This is a conceptual separation, not a requirement to expose a freely
combinable quantizer, predictor, packer, and compressor registry. A small set of
versioned array encoding identifiers can define the supported combinations and
their parameters. Avoid recreating the same complexity under new names.

If outer-only compression wins, remove per-array general-purpose compression
from the proposed core representation. If removing it costs too much size or
breaks required cases, retain it behind fixed profiles rather than a large
user-facing matrix. Give the data a chance to choose either outcome.

Resolve these details together in the specification and registry:

- Encoding byte layouts, reconstructed dtype, fidelity semantics, names,
  parameters, and exact fallback behavior.
- Whether a fidelity field is retained for inspection of unknown encodings.
  Do not remove it as redundant without replacing that capability.
- Mandatory support for every transform emitted by the default lossless and
  lossy profiles. Raw and zlib support alone is not enough to decode a Numpress
  or delta-based default token.
- Frame identifiers, compressor framing, missing capabilities, checksums,
  malformed streams, and resource limits.
- The current 16 MiB expanded-CBOR cap. Uncompressed array blobs may make
  previously representable spectra exceed it. Measure this before selecting
  outer-only compression or changing the limit.
- Compatibility with existing v3 artifacts. Never reuse an operation ID with a
  different meaning. Verify publication and downstream use before treating old
  v3 layouts as disposable development artifacts. Otherwise preserve readers
  or use an appropriate wire-version change.

Keep PSI codec mappings in an interoperability adapter. Keep scientific terms
and custom-array identity rules in the core model. Do not redesign metadata
inheritance, units, provenance, and extensions in the same iteration.

**5. Implement and synchronize once**

Develop in `~/Repos/spectrl`. Update Python and TypeScript together,
including the CLI, inspection, budget helpers, browser demo, schema generator,
documentation, and shared vectors.

Verify both directions between implementations for all supported payload
compressors and default profiles. Cover empty arrays, signed zero, integer
limits, malformed and oversized streams, missing optional compressors, custom
array names, optional standard-array names, and unchanged array identities.
Verify numeric fidelity and metadata preservation after sorting and re-encoding.
Check auto selection using actual complete tokens and the documented candidate
set. Verify browser use independently of Node support for optional compressors.

Run the existing unit, type, build, decoder-fuzz, package, and browser checks.
Only after the implementation is stable, synchronize a reviewed allowlist into
`~/Repos/spectrl-paper`. Preserve independent paper changes. Rebuild
`js/dist` and record source hashes for both language runtimes. The paper analysis
imports this checkout's Python code and JavaScript build, not the main checkout.

**6. Rebuild a small set of publication experiments**

The published evaluation should answer four questions:

1. Does decoding preserve the promised arrays and modeled metadata?
2. Can Python and TypeScript exchange the final tokens?
3. How large are the actual lossless and lossy tokens, and where are they useful?
4. What are ordinary complete encode and decode times?

Retain full-input fidelity validation and the pinned representative size corpus.
For lossy output, report m/z error, intensity error, positive-to-zero frequency,
and appropriate similarity metrics. Similarity alone does not establish
identification or quantification preservation. No new downstream-performance
claim is planned.

Separate two size questions:

- A controlled container comparison uses the same metadata, native numeric
  values, and a common raw array representation in spectrl and valid mzML,
  with documented whole-document compression and equivalent transport framing.
- A practical profile comparison measures the final shipped spectrl policies.
  If its numeric encoding differs from the mzML baseline, identify that fact
  and do not describe the result as pure container overhead.

If per-array compression is removed, rebuild the matched baseline accordingly.
Do not place custom spectrl transforms in mzML with invented PSI accessions.

Use one compact payload-compression table with `r`, `z`, `s`, and `b` at the
chosen presets, for both fidelity profiles. Report auto's size benefit in a
small additional row or sentence. Time end-to-end Python and TypeScript encoding
and decoding with warmups, repeated measurements, and recorded environments.
Run timed benchmarks serially. Keep detailed codec-search timing out of the
paper unless it explains a material limitation.

**7. Rewrite the manuscript around the final product**

Keep the main narrative centered on sharing a self-contained spectrum. Explain
two fidelity profiles, the chosen default array representations, and default
zlib CBOR transport. Move registry details and optional capability rules into
the specification and a short SI format section.

Proposed SI organization:

1. Related spectrum representations.
2. Format details.
3. Complete token example.
4. Benchmark corpus, including metadata coverage and validation procedures.
5. Reconstruction fidelity.
6. mzML size comparison and relevant subgroup results.
7. Payload compression.
8. Runtime.

Move the metadata-coverage table identified by `tbl:metadata-coverage` into the
corpus section. Remove the redundant size figure discussed as Figure S6 after
matching its caption against the intended draft. Figure and table numbers have
shifted, so use stable labels rather than assuming current S6 or S3 identifies
the same object as in the chat.

Remove the current lossless-pipeline tournament and supported-PSI matrix as
standalone SI sections. Archive their analysis as development evidence. Remove
the experimental S9 study from the publication if its methods remain unused.
If a new quantizer becomes the shipped default, retain its error contract and
validation under reconstruction fidelity, with a concise selection rationale.
Replace the current outer-compressor sweep with the single-preset comparison.
Move alternative text-encoding exploration out of the publication unless it
supports a necessary claim about choosing base64url.

Update the abstract, conclusions, methods, main figures, complete example token,
transport thresholds, captions, and associated-content list from the final
results. Do not reuse old sizes, timing values, or automatic raw/zlib claims.
Keep exploratory findings available in the repository without making the paper
narrate every design choice.

**8. Acceptance and stopping point**

Implementation completion requires both runtimes, shared vectors, the browser
path, specification, registry, and actual defaults to agree.

Paper completion requires one recorded implementation snapshot, freshly derived
reports, figures, tables, and statistics, and verified matched-baseline semantics.
Change generators rather than generated `si/*.typ` or figure files. Route claims
through the existing statistics and asset declarations. Trace retained claims
before changing their sources.

Build PDF and Word outputs, inspect them, and run `just paper`, `just verify`,
and the deep statistics check as required by the manuscript workflow. Record
actual word counts and readability results. Run submission preflight only when
preparing a submission. Publication, pushes, releases, and submission are outside
this planning task.

The next actionable deliverable is the bounded design experiment in step 3.
After its decision report, implement once, regenerate results once, and rewrite
the paper against those results.
