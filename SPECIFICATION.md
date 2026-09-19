# spectrl v3

A spectrl token carries one mass spectrum, its parallel numeric arrays, and the
metadata needed to interpret that spectrum. It can be embedded in a URL,
a document, or a message. It is not a container for an entire acquisition run.
This specification defines version 3. Implementations reject other versions.

## 1. Framing and corruption detection

```text
spectrl.v3.<mode>.<payload>.<checksum>
```

There are exactly five dot-separated parts. Payload compression is `r` for raw
CBOR, `z` for one RFC 1950 zlib stream, or `b` for
one Brotli stream. All use unpadded RFC 4648 base64url. Readers must support `r`
and `z`. Brotli is optional and fails explicitly when unavailable.
Unknown identifiers are errors. Readers never infer compression from bytes.

Writers default to `z`. The fixed presets are zlib level 6 and Brotli quality 5. Levels affect writing, not inverse semantics. Explicit
`auto` is a writer option that selects the smallest complete token among
available encodings, with tie order `z`, `r`, `b`. The token always records
the selected compression, never `auto`. Both encoded and expanded payloads must
fit the size limit. Oversized alternatives are excluded from auto selection.

The checksum is CRC-32/ISO-HDLC of the ASCII bytes
`spectrl.v3.<mode>.<payload>`, rendered as eight lowercase hexadecimal characters,
including leading zeroes. Validate it before decompressing or parsing the payload.
It detects accidental corruption of the complete token, including its mode,
metadata, and codec declarations. It is neither a spectrum identifier nor
authentication. It covers the encoded representation, so it works with lossless
and lossy arrays. There is no additional hash identifier.

Both the base64url-decoded payload and the expanded CBOR document are limited to
16 MiB. Enforce the expanded limit during decompression, before allocating the
complete output. Zlib streams must use DEFLATE without a preset dictionary.
Reject truncated streams, invalid checksums, concatenated streams, and trailing
data. Brotli decoding is bounded
incrementally. Concatenated streams and trailing data are rejected for all
compressors. Gzip and bare DEFLATE are not valid `z` payloads. Inspection applies
the same checks and expands the outer payload without decoding numeric arrays.

Writers emit definite-length CBOR with map keys sorted by encoded length then
byte order. Readers reject duplicate map keys, trailing data, unsupported tags,
non-finite numbers, and integers outside the JavaScript safe integer range.
Byte strings carry blobs. Text strings use UTF-8. Readers need not require
minimal floating-point widths. Equivalent spectra need not produce identical
tokens across compressors or implementations.

Map keys are integers or text, including inside extension data. Booleans, null,
and finite floating-point values are supported as values, not as map keys.
Undefined and other CBOR simple values are unsupported. All CBOR tags are
unsupported. Text must be valid UTF-8. These restrictions apply recursively,
including to unknown optional extensions and custom operation parameters.

## 2. Header

The CBOR root is an integer-keyed map. Unknown structural keys are errors.
Except for key 0, fields are optional. Empty optional collections should be omitted.
An absent array list means the token contains metadata only.

| Key | Meaning | Value |
| --- | --- | --- |
| 0 | Number of elements per array | Nonnegative integer |
| 1 | Spectrum ID | Text |
| 2 | Spectrum CV parameters | Ordered parameter pairs |
| 3 | Scan list | Map with optional `c` combination accession tail and `s` scan list |
| 4 | Precursors | List of precursor maps |
| 5 | Products | List of product maps |
| 6 | Numeric arrays | List of array descriptors |
| 7 | Spectrum user parameters | List of user parameter maps |
| 8 | Source | Source record |
| 9 | Acquisition | Acquisition record |
| 10 | Processing | Ordered processing records |
| 11 | Extensions | Namespaced extension map |

All present arrays have exactly the length in key 0. Each array identity appears
at most once. Core arrays are m/z (`MS:1000514`), intensity (`MS:1000515`), and
charge (`MS:1000516`). Other PSI-MS array types retain their accessions.
Nonstandard arrays use `MS:1000786` and a nonempty name. Nonstandard array names
must not be `mz`, `intensity`, or `charge`. A nonempty free-text
name is required for nonstandard arrays and optional for standard arrays.
Standard array identity is its accession, regardless of its optional name.
Nonstandard array identity is its accession together with its name.

Numeric types are float32 (`MS:1000521`), float64 (`MS:1000523`), and int32
(`MS:1000519`). Raw numeric words are little-endian. All values must be finite.
m/z values must be nonnegative. Writers stably sort peaks by ascending m/z and
apply the same permutation to every array. Native supported widths are preserved
by lossless encoding. Plain language-level number lists default to float64.
The descriptor always declares the reconstructed type, including float64 for
quantized-word output.

## 3. Scientific parameters

A CV parameter list is an ordered list of `[accession, value]` pairs. Repeated
accessions are permitted and retained. A seven-digit MS accession is represented
by its integer tail. Other accessions retain the full text, for example
`NCIT:C25330`. A value is null, a finite number, or text. Null denotes a flag.
A value with a unit is `[value, unit]`, including `[null, unit]` when appropriate.

A seven-digit UO unit uses its integer tail. Other seven-digit numeric units use
`[ontology, tail]`. Other unit accessions use their complete string. Numeric tails
are in 0..9999999. Conversion from mzML retains lexical values as strings.
Applications may also supply numeric values directly.

```text
[[1000511, 2], [1000016, [23.41, 31]], [1000511, "repeat"]]
```

A user parameter is `{"n": name, "v": value?, "t": type?, "u": unit?}`.
Name is nonempty text. Value has the same scalar domain as a CV value. Type is
optional text, normally an XML Schema type. Units use the CV unit representation.
Unknown user parameter fields are errors.

A parameter group is `{0: CV pairs, 1: user parameters?}`. Scan windows,
isolation windows, selected ions, and activation each use a parameter group.

A scan is `{0: CV pairs, 1: scan window groups?, 2: user parameters?,
3: source?, 4: acquisition?, 5: processing?}`.
A precursor is `{0: isolation group?, 1: selected ion groups?, 2: activation group?,
3: source?, 4: acquisition?, 5: processing?}`.
A product is `{0: isolation group?}`.
The scan-list combination is a PSI-MS flag accession tail. It has no value or unit.

## 4. Array descriptors

| Key | Meaning | Required |
| --- | --- | --- |
| 0 | Reconstructed numeric type accession tail | Yes |
| 1 | Array type accession tail | Yes |
| 2 | Numeric encoding operation | Yes |
| 4 | Array name, nonempty text | For MS:1000786, optional otherwise |
| 5 | Numeric encoding bytes | Yes |
| 6 | Unit accession | No |
| 7 | Fidelity, 0 exact or 1 potentially lossy | Yes |
| 8 | Additional scientific CV pairs | No |
| 9 | Array user parameters | No |
| 10 | Array processing records | No |
| 11 | Array extensions | No |

Additional scientific parameters must not duplicate numeric type, array identity,
or codec declarations. Fidelity describes the current encoding operation relative
to its input array. It does not assert that the acquisition or upstream processing
was lossless. Readers retain a descriptive processing record for a decoded lossy
operation when preparing that spectrum for re-encoding.

An operation is `[identifier, revision]` or `[identifier, revision, parameters]`.
Identifier is a nonnegative integer for a built-in operation or a namespaced string
matching `[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+`. Revision is a positive safe
integer. Parameters are a string-keyed CBOR map. Omit an empty parameter map.
The `spectrl:` namespace is reserved. Custom implementations register an identifier
and revision for a numeric encoding. Registration must not replace an existing
implementation. Tokens never contain executable code.

Array bytes receive only the declared numeric encoding. Compression applies once
to the complete CBOR document. Descriptor key 3 is invalid. Earlier development
tokens and their encoding identifiers are unsupported.

An unknown encoding or revision permits metadata inspection and unchanged
forwarding of the original token, but full decoding fails explicitly.
A reader must not substitute another codec or treat unknown bytes as raw data.

## 5. Numeric encodings, revision 1

| ID | Encoding | Parameters | Fidelity |
| --- | --- | --- | --- |
| 0 | Raw little-endian words | None | Exact |
| 1 | Byte shuffle | None | Exact |
| 2 | Unsigned modular delta plus byte shuffle | None | Exact |
| 3 | Quantized unsigned words plus byte shuffle | `scale`, `width`, optional `log`, `delta` | Potentially lossy |

Encodings 0..2 support all three numeric types. Encoding 3 reconstructs float64.
All four encodings form the mandatory core. No other parameters are accepted by
these revisions. Scientific PSI-MS terms identify arrays and metadata, not codecs.

For a word width W bytes, byte shuffle concatenates byte lane 0 for all words,
then lane 1, through lane W-1. Unshuffle interleaves the lanes. Empty input produces
empty output. The byte count must be divisible by W.

For encoding 2, reinterpret each numeric word as an unsigned W-byte integer.
The first delta is the first word. Each subsequent delta is the current word minus
the preceding word modulo 2^(8W). Store deltas little-endian and byte-shuffle them.
The inverse unshuffles, then cumulatively adds unsigned words modulo 2^(8W), starting
at zero. Finally reinterpret the reconstructed bits in the declared numeric type.
There is no floating-point subtraction, quantization, or mantissa truncation.
Signed zero and every permitted finite bit pattern are preserved. This is a
composition of established compression transforms, not a claim of a novel predictor.

### Quantized words

Encoding 3 requires a finite positive numeric `scale` and integer `width` of
1, 2, 4, or 8 bytes. Optional booleans `log` and `delta` default to false.
Inputs are finite and nonnegative. Map each value x to x, or ln(1+x) when `log`
is true, multiply by scale, and round to the nearest integer with ties upward.
Each unsigned index must fit its width and be no greater than 2^53-1.

Store indices as little-endian words. When `delta` is true, first replace each
word with its difference from the preceding word modulo 2^(8*width), with zero
as the preceding word for the first index. Finally byte-shuffle the words.
Decoding reverses shuffle and modular differences, checks the index domain,
and divides each index by scale. With `log`, apply expm1 to that quotient.
Reject nonfinite reconstructed values and incorrect byte counts.

The linear rounding bound is 0.5/scale in source units. The logarithmic bound
is (x+1)*expm1(0.5/scale), so it is approximately proportional to x for larger
values but is not a strict relative bound near zero. Reference writers decode
and check these bounds against their inputs, rejecting an explicit invalid
choice and using an exact fallback for an automatic choice. Bounds refer to
numeric reconstruction, not downstream scientific performance.

## 6. Writer profiles

The default lossless profile uses modular delta plus byte shuffle for m/z,
byte shuffle for intensity, and raw native words for all other arrays. It does
not search a matrix of codecs. Integer arrays remain exact in both profiles.

The default lossy profile uses encoding 3 for floating m/z and intensity.
m/z uses `log: true` and `delta: true` with a maximum pointwise error of
0.1 ppm relative to each source value. Let `m` be the smallest positive m/z and
`r = 0.1e-6 * (1 - 1e-7)`. The writer chooses
`scale = ceil(0.5 / log1p(r * m / (m + 1)))`. The small margin accommodates
floating-point rounding. Empty and all-zero arrays use `m = 1`. Zero is exact.
The writer checks reconstructed values against the requested 0.1 ppm bound.
Unsupported scales or failed checks use exact encoding. This scale selection
uses the existing logarithmic representation without changing decoding.
Nonnegative intensity uses scale 3600
and `log: true`. The writer chooses the smallest integer width that fits the
indices. Unsupported domains or failed measured bounds use the exact profile
for that array. All auxiliary arrays remain exact by default. Explicit lossy
settings fail on invalid domains. Unknown array semantics require explicit
caller permission before applying a lossy encoding. Callers may select any core encoding explicitly, or register a namespaced custom
encoding. Outer zlib applies once to the complete CBOR document by default.

## 7. Source, acquisition, and processing context

Records use the following shared keys. Only fields allowed for the record type
are valid. Original XML IDs remain text values, not unresolved foreign keys.

| Key | Field |
| --- | --- |
| 0 / 1 | CV pairs / user parameters |
| 2 / 3 / 4 | ID / name / version |
| 5 / 6 / 7 | Location / external ID strings / spectrum reference |
| 8 / 9 | Instrument record / component records |
| 10 / 11 | Component kind / nonnegative component order |
| 12 | Software record |
| 13 / 14 / 15 | Operation name / positive revision / parameter map |
| 16 | Source-scoped CV pairs |

Source allows keys 0, 1, 2, 3, 5, 6, 7. Acquisition allows key 8. Instrument allows
0, 1, 2, 3, 9, 12. Component allows 0, 1, 10, 11, with kind `source`, `analyzer`,
or `detector`. Software allows 0, 1, 2, 3, 4. Processing allows 0, 1, 12..16.
Record text fields are strings. Components and processing are ordered lists.
External IDs are nonempty strings. Processing parameters are a string-keyed map.

Spectrum acquisition is the default for its scans. An explicit scan acquisition
replaces that default. Spectrum processing is the default for arrays. An explicit
array processing list supplies that array's processing history. Precursor source
records describe the referenced source spectrum, not the current array data.
The source spectrum ID in header key 1 and reference strings are descriptive
identifiers. They are not guaranteed globally unique and need not be resolvable.

The mzML bridge resolves referenceable parameter groups, default source and
instrument references, selected scan overrides, spectrum processing defaults,
array processing overrides, and associated software when supplied with run context.
Unrelated run inventories are excluded. Missing context and unresolved references
are reported. Strict conversion rejects warning-level omissions.

`top_n` records a `spectrl:peak-selection` revision-1 processing step with method
`highest-intensity`, `inputPeakCount`, and `outputPeakCount`. Acquisition-derived
TIC, base peak, and observed-range parameters move from current spectrum parameters
to that step's source-scoped CV pairs. They must not describe the trimmed arrays.
Removing user parameters records `spectrl:metadata-omission` revision 1 and
`userParamsRemoved`. Decoding a potentially lossy array adds an array processing
record `spectrl:lossy-encoding` revision 1 with the encoding descriptor in its
parameters when exposed through the reference decoded model.

## 8. Extensions and limits

An extension map uses namespaced string keys. Each value is
`{"revision": positive integer, "required": boolean, "data": CBOR value}`.
Unknown optional extensions are retained. Unknown required extensions permit
inspection and unchanged forwarding but cause full decoding to fail. Extensions
at spectrum or array scope may depend on array order or content. The reference
sorting and selection helpers therefore require callers to remove or update them
explicitly before changing arrays. No built-in identification schema is defined.

Hard limits are 16 MiB decoded CBOR, 64 MiB intermediate bytes per array,
4,000,000 elements per array, CBOR nesting depth 32, and 100,000 CBOR items.
The intermediate per-array cap is also at most `64 + 16*element_count` bytes.
A custom decoder receives the element count and must respect the derived
intermediate cap before allocating expanded data.
The caller's optional limits can further restrict token bytes, peaks, array count,
and aggregate reconstructed array bytes. Aggregate limits are checked before any
array is decoded. These limits also apply during inspection.

The machine-readable registry is `schema/registry.json`. Shared positive,
negative, and inverse vectors under `test-vectors/` define executable examples.
