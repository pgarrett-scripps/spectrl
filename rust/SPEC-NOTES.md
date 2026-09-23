# Specification notes from the Rust implementation

This crate was written from `SPECIFICATION.md`, `schema/registry.json` and
`test-vectors/` only. The Python and TypeScript sources were not read. Each entry
below is a point where the specification text alone did not decide the
behaviour: the section, what was unclear, what this crate does, and the evidence.

Evidence, in order of preference: a shared vector; the live three-way parity
scripts (`scripts/check_token_parity.py`, `scripts/check_adversarial_parity.py`);
and, as a last resort, black-box probing of the installed Python reference
(`decode_token` on hand-built tokens, never its source). Probed entries say so.
Each is a candidate for a new vector or a sentence in the specification.

## Brotli preset and encoder (section 1)

- **Unclear:** section 1 fixes Brotli quality 5 but not the window size, and
  section 6 says compressed bytes may differ between compressor versions.
- **Resolution:** quality 5, `lgwin` 22 (the Brotli default), generic mode, one
  call over the complete CBOR document. Encoding and decoding go through the
  reference C Brotli library via the `brotlic` crate, the same library Python
  (`brotli` 1.2.0) and Node use.
- **Evidence:** live token parity. The pure-Rust `brotli` 8.0.4 encoder with the
  same parameters produced different, valid streams for 29 to 34 of 132 Brotli
  cases, identical CBOR in every case. The C library matched Python in 132 of 132.
  Without C Brotli the `b` tokens decode everywhere but are not byte-identical.
- **Suggest:** state `lgwin` 22 in section 1, and say that `b` byte identity
  holds only for writers built on the reference C encoder.

## Descriptor parameters that must not duplicate (section 4)

- **Unclear:** section 4 says additional scientific parameters "must not
  duplicate numeric type, array identity, or codec declarations", but does not
  list the accessions. The registry does not list them either.
- **Resolution:** a descriptor is rejected ("array scientific parameters conflict
  with representation declarations") when a key-8 pair names the descriptor's own
  array type, any of the four binary data type terms (MS:1000519, 1000521,
  1000522, 1000523), or a binary compression term (MS:1000574, 1000576,
  1002312-1002314, 1002746-1002748, 1003780-1003785). Accession text such as
  `"MS:1000521"` is treated like its integer tail. Another array's type is allowed.
- **Evidence:** black-box probe (last resort): every MS tail in 1000000..1004199
  and 4000000..4000299 on an intensity descriptor; exactly these 19 were rejected.
- **Suggest:** list the terms in the specification or the registry and add one
  negative vector per group.

## The `spectrl:lossy-encoding` record (section 7)

- **Unclear:** section 7 says decoding a potentially lossy array "adds an array
  processing record `spectrl:lossy-encoding` revision 1 with the encoding
  descriptor in its parameters", but not the parameter key, nor what happens when
  the array has no explicit processing list.
- **Resolution:** the record is `{operation: "spectrl:lossy-encoding", revision: 1,
  parameters: {"encoding": <operation array as written>}}`, appended to the
  array's explicit processing list. When the array has none, it is appended to a
  copy of the spectrum processing list, since section 7 makes spectrum processing
  the default for arrays.
- **Evidence:** the parameter key comes from a black-box probe (last resort) of a
  decoded lossy token. The copy rule follows section 7's default rule; no vector
  checks it.
- **Suggest:** a vector whose `decoded` includes `array_processing` after a lossy
  decode, with and without spectrum processing.

## Writer bound checks (section 6)

- **Unclear:** section 6 says the writer "checks reconstructed values against
  the requested 0.1 ppm bound" and section 5 gives the logarithmic bound, but not
  the exact comparison.
- **Resolution:** m/z candidate kept only if `|x' - x| <= 0.1e-6 * x` for every
  value; logarithmic intensity only if `|x' - x| <= (x + 1) * expm1(0.5 / scale)`,
  with `x'` the decoded value (fdlibm `log1p` and `expm1`). Rounded words
  (encoding 4) have no extra check beyond finite reconstruction and width.
- **Evidence:** live token parity, 66 of 66 default-profile cases identical in
  every payload mode, plus the `profile-*` and `rounded-carry` token-parity vectors.
- **Suggest:** write the two inequalities into section 6.

## Rounding ties (section 5)

- **Unclear:** section 5 says "ties upward" for quantized indices, without
  saying how, and `floor(y + 0.5)` misrounds values just below one half.
- **Resolution:** `f = floor(y); if y - f >= 0.5 { f + 1 } else { f }`, which is
  exact in binary64 for nonnegative `y`.
- **Evidence:** the `deterministic-expm1` token-parity vector and live parity.

## Reader check order (section 8)

- **Unclear:** section 8 says aggregate budgets are "checked before any array is
  decoded" but not how they rank against header errors or required extensions,
  which decides which error a reader reports first.
- **Resolution:** token length budget, framing and checksum, outer expansion,
  CBOR, header validation, then peak, array-count and aggregate-byte budgets (also
  in inspection), then a required spectrum extension, then per array: a required
  array extension or unknown encoding, decode, finiteness, negative m/z.
- **Evidence:** `negative-vectors.json`, `adversarial-vectors.json` and the live
  adversarial parity. Neither checks the error message, only accept or reject.

## Decoded m/z on read (sections 4 and 6)

- **Unclear:** the writer sorts peaks by m/z (section 6), but the text does not
  say whether a reader rejects unsorted m/z or `-0.0`.
- **Resolution:** readers accept unsorted m/z and `-0.0`, and reject any negative
  m/z, including a negative integer-typed m/z.
- **Evidence:** black-box probe (last resort) of the same cases; negative m/z also
  appears in `negative-vectors.json`.

## Header edge cases (sections 3 and 7)

- **Unclear:** section 7 and the registry do not say whether empty optional
  records (an empty source, acquisition, instrument, processing list or
  extension map) are valid, nor the exact ontology-prefix grammar for key 12.
- **Resolution:** empty optional records are accepted. An ontology prefix
  matches `[A-Za-z][A-Za-z0-9]*`, so `ms` passes and `1MS`, `M-S`, `M_S` and the
  empty string fail. Operation identifiers follow the section 4 pattern; a
  well-formed but unknown one reads as unsupported, not malformed.
- **Evidence:** black-box probe (last resort), 60 hand-built headers; the
  rejections that `negative-vectors.json` covers agree.
- **Suggest:** one positive vector with empty optional records, and the prefix
  grammar in section 7.

## Inspection output (sections 4 and 8)

- **Unclear:** sections 4 and 8 require inspection that reports unknown
  encodings and required extensions without decoding values, but do not define
  what it returns.
- **Resolution:** `inspect_token` returns one `ArrayInfo` per descriptor: key,
  array type, name, dtype, operation, fidelity, `available` (known encoding and
  no required extension), blob byte count and unit. It applies every framing,
  header and budget check that decoding does.
- **Evidence:** the specification only. Inspection results are not compared
  across implementations.

## JSON interchange for the parity harness (no section)

- **Unclear:** the vectors carry spectra as JSON (`token-parity-inputs.json`,
  `decoded` fields) but the specification does not define that shape, including
  how bytes, `-0.0` and non-JSON CBOR values are spelt.
- **Resolution:** `spectrl::json` reads and writes the shape the vectors use,
  with `$spectrl` escape objects for values JSON cannot express. It is a harness
  format, not part of the token format.
- **Evidence:** every vector file decodes and compares; field names for records
  no vector exercises were confirmed by a black-box probe (last resort).

## Declared-type bound checks for float32 (sections 5 and 6)

- **Unclear:** the float32 growth `max(2^-24·y, 2^-150)` is stated for each
  bound, but it is not clear whether the default profile's ppm m/z check takes
  it too, or whether the intensity candidate keeps the grid bound alongside the
  new relative bound `2·expm1(0.5/3600)`.
- **Resolution:** both checks compare the value reconstructed in the declared
  type. The ppm check (`|y−x| <= x·1e-7`) takes no growth, so float32 m/z that
  the extra rounding pushes out falls back to a lossless mode. The intensity
  candidate must pass both the grown grid bound and the relative bound.
- **Evidence:** `tests/test_declared_type.py` (allowed reading) and the
  `float32-mz-ppm-fails` and `typed-arrays/lossy` entries in `token-parity.json`,
  which the Rust writer matches byte for byte.

## Null leaf fields in context records (section 7)

- **Unclear:** "Record text fields are strings" and optional fields may be
  omitted, but the specification does not say whether an explicit null in an
  optional record field is an error or an absent field.
- **Resolution:** a null in a leaf field (source 2, 3, 5, 6, 7; software 2, 3,
  4; instrument 2, 3; component 10, 11; processing 13, 14, 15) reads as absent.
  Parameter lists and nested records keep their type checks.
- **Evidence:** black-box probe (last resort): the adversarial parity run found
  102 mutations that Python and TypeScript accept and Rust rejected, every one a
  null in one of these fields. With this rule Rust agrees on all 120,158 tokens.
