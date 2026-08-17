# spectrl Token Format Specification

- **Format identifier:** `spectrl.v1`
- **Specification version:** 1.0
- **Status:** Frozen, governed in this repository
- **Editor:** Patrick Garrett (pgarrett@scripps.edu), The Scripps Research
  Institute
- **License:** Apache-2.0
- **Document conventions:** structured per HUPO-PSI specification documents
  (as [mzPAF][mzpaf], [ProForma][proforma])

## Status of this document

This document provides information to the proteomics community about the
spectrl token format for passing one complete mass spectrum as a
self-contained, URL-safe string. Distribution is unlimited.

This specification is developed and governed openly in this repository. It
follows the document structure used by HUPO Proteomics Standards Initiative
(PSI) specification documents, but it has **not** been submitted to, and has
**not** been ratified by, the PSI Document Process. It is normative for the
`spectrl.v1` wire format: conforming implementations target this document and
the conformance vectors ([§11](#11-conformance)). This version is **FROZEN**:
every future breaking change increments the format identifier
([§9](#9-versioning)).

Version: 1.0

## Abstract

The HUPO Proteomics Standards Initiative (PSI) defines community standards for
data representation in proteomics, including mzML for instrument output, the
Universal Spectrum Identifier (USI) for referencing deposited spectra, and
ProForma for peptidoform notation. This document presents a specification for
**spectrl**, a compact, URL-safe token that embeds one complete mass spectrum
(its peak arrays, acquisition metadata, and precursor/product information)
such that the spectrum can be reconstructed from the string alone, with no
access to an external file, resolver, repository, or other service. The format
reuses existing PSI machinery: PSI-MS controlled-vocabulary semantics, the
MS-Numpress and zlib peak codecs, and ProForma interpretations. Further
information, two reference implementations, a machine-readable registry, and
shared test vectors are available at
<https://github.com/pgarrett-scripps/spectrl>.

## 1. Introduction

### 1.1 Description of the need

The tandem mass spectrum is a basic unit of evidence in mass spectrometry, yet
the spectrum quoted in a manuscript, review, or software discussion is usually
a static image, and the spectrum passed between programs usually travels as an
uploaded file or a stored session. The USI addresses quotation by reference:
it encodes a standardized virtual path to a spectrum in a public repository.
The remaining case is data that are offline, not yet deposited, or passing
directly between programs, where the spectrum data must be included rather
than retrieved through a resolver. Plain-text peak lists can be included but
carry limited structured metadata, do not fit naturally in a URL or caption,
and truncate silently.

A **spectrl token** covers this case: a compact, URL-safe text string that
embeds a complete mass spectrum such that the entire spectrum can be
reconstructed from the string alone. The token is the spectrum: decoding never
requires access to an external file, resolver, repository, or other service.

### 1.2 Requirements

The main requirements to be fulfilled by the token format are:

- It MUST be self-contained: the complete spectrum is recoverable from the
  token with no external lookup.
- It MUST be URL-safe without escaping, usable in a URL fragment, query
  parameter, `data:` URI, or QR code.
- It MUST preserve mzML metadata semantics by carrying PSI-MS CV accessions
  with their published meanings, introducing no bespoke field names.
- It MUST let the producer choose between compact lossy encoding and bit-exact
  lossless recovery, and the choice MUST be evident from the token.
- It MUST detect corruption and truncation, failing decode rather than
  silently altering the spectrum.
- It MUST be implementable from this document, the machine-readable registry,
  and the shared test vectors alone, independent of any single language or
  serializer.
- It MUST be safe to decode as untrusted input: declared lengths bound
  decompression, malformed documents are rejected, and decoding never executes
  embedded content ([§12](#12-security-and-privacy-considerations)).
- It MUST be versionable with a clean version break ([§9](#9-versioning)).
- It SHOULD be deterministic within an implementation: a given spectrum in
  canonical form produces a stable token and verifiable checksum. Token
  bytes are not guaranteed identical *across* implementations
  ([§8](#8-canonical-form-and-checksum)).
- It SHOULD be substantially smaller than the equivalent mzML XML for typical
  spectra.
- It MAY carry a peptidoform interpretation. Peptide identity is never
  required ([§6.6](#66-proforma-interpretation)).

### 1.3 Scope

This document specifies:

- the textual structure of a `spectrl.v1` token ([§4](#4-token-structure)).
- the binary encoding of the metadata header ([§6](#6-header)).
- the binary encoding of peak arrays ([§7](#7-peak-arrays)).
- the canonical form and checksum ([§8](#8-canonical-form-and-checksum)).
- versioning and conformance ([§9](#9-versioning), [§11](#11-conformance)).

It does not specify viewer behavior, transport, or storage beyond the URL/URI
bindings in [§10](#10-uri-bindings).

### 1.4 Terminology

- **Producer**: software that emits a spectrl token.
- **Consumer**: software that parses a spectrl token.
- **Tail**: the integer portion of a CV accession (e.g. the tail of
  `MS:1000511` is `1000511`). See [§5](#5-controlled-vocabulary-binding).

## 2. Notational conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this
document are to be interpreted as described in [RFC 2119][rfc2119] and
[RFC 8174][rfc8174] when, and only when, they appear in all capitals. In
general, MUST means required, SHOULD means recommended, and MAY means
optional.

## 3. Relationship to other specifications

### 3.1 Reused PSI machinery

A spectrl token reuses, rather than reinvents, existing PSI machinery:

- **Controlled vocabulary:** spectrum metadata is expressed as PSI-MS CV terms
  (`MS:` accessions), mirroring mzML `cvParam` semantics. Units use the Units
  of Measurement Ontology (`UO:`). No bespoke field names are introduced.
- **Peak compression:** peak arrays use the same MS-Numpress and zlib pipelines
  that mzML uses for its `binaryDataArray` elements.
- **Peptide interpretation:** carried as a [ProForma 2.0][proforma] string.

### 3.2 Normative dependencies

This specification depends normatively on: [RFC 4648][rfc4648] (base64url),
[CBOR][cbor] ([RFC 8949][cbor], including its §4.2 deterministic encoding), the
[PSI-MS controlled vocabulary][psims], MS-Numpress, and zlib
([RFC 1950][rfc1950]).

### 3.3 Related specifications

This format is designed to be complementary to, not a replacement for,
existing standards:

- **mzML** stores complete runs. Spectrl mirrors the semantics of a single
  mzML `<spectrum>` element ([§6](#6-header)) so that one spectrum can be
  carried faithfully outside its run.
- **USI** identifies a spectrum in a public repository by reference. Spectrl
  embeds the data itself for the offline, undeposited, and program-to-program
  cases. A viewer can accept both.
- **ProForma 2.0** is the notation for the optional peptidoform
  interpretation ([§6.6](#66-proforma-interpretation)).
- **mzSpecLib** and **[mzPAF][mzpaf]** address spectral libraries and fragment
  ion annotation. Spectrl carries one spectrum and does not define peak
  annotations.

### 3.4 Accompanying products

This document is accompanied by, in the same repository:

- [`schema/registry.json`](schema/registry.json): a machine-readable registry
  of every integer header key, CV accession tail, codec identifier, and
  encoding rule.
- [`test-vectors/`](test-vectors/): the language-agnostic conformance suite
  ([§11](#11-conformance)).
- reference implementations in Python (`src/`, on PyPI as `spectrl`) and
  TypeScript (`js/`).
- a browser demonstration that encodes and decodes tokens client-side.

## 4. Token structure

A token is an ASCII string of exactly four `.`-separated parts:

```abnf
token      = identifier "." version "." payload "." checksum
identifier = "spectrl"
version    = "v" 1*DIGIT    ; format version; this document specifies "v1"
payload  = b64url           ; base64url( CBOR document ), REQUIRED
checksum   = 8lowerhex       ; CRC-32/ISO-HDLC (§8), REQUIRED
lowerhex   = DIGIT / %x61-66 ; lowercase a-f
b64url   = *( ALPHA / DIGIT / "-" / "_" )   ; RFC 4648 §5, no padding
```

- The first part is the stable **format identifier**, `spectrl`.
- The second part is the **format version**, `v1`. A consumer **MUST** reject a
  version it does not support. This prefix is the format version's **only**
  carrier. The CBOR document does not repeat it.
- The third part is a single **CBOR document** ([RFC 8949][cbor]): the header
  map ([§6](#6-header)) with each peak array's compressed blob embedded inline
  ([§7](#7-peak-arrays)). There are **no** separate array segments.
- The fourth part is the required **CRC-32 checksum** over the first three
  parts ([§8](#8-canonical-form-and-checksum)), encoded as eight lowercase
  hexadecimal characters.
- The payload **MUST** be base64url-encoded ([RFC 4648 §5][rfc4648]) **without**
  padding (`=`). Consumers **SHOULD** accept padding on decode for robustness but
  producers **MUST NOT** emit it.
- The token string is the interchange unit. The bare CBOR document is an
  internal representation: it carries neither the format version nor the
  checksum, so applications that persist or transmit spectra **SHOULD**
  store the full token string rather than the decoded payload bytes.

## 5. Controlled vocabulary binding

CV accessions are encoded by their integer **tail** to save space. Tail
encoding reconstructs the accession with 7-digit zero-padding, so it is only
used when the tail is **exactly 7 decimal digits**. Any other tail (shorter,
longer, or non-numeric, e.g. `MOD:00046` or `NCIT:C25330`) is carried as the
full accession string.

- A parameter accession with ontology prefix `MS` and a 7-digit tail is used as
  a map key in the form of its bare tail integer (e.g. `MS:1000511` → `1000511`).
- Any other parameter accession (another ontology, or a non-7-digit tail) is
  used as a map key in the form of the **full accession string** (e.g.
  `"UO:0000031"`). A CBOR map key must be a scalar, so the `[ontology, tail]`
  array form is reserved for *values* (such as units) and is not used for keys.
- Unit accessions (which appear as *values*) default to the `UO` ontology: a
  bare integer is interpreted as `UO:<tail>`. A 2-element `[prefix, tail]` array
  carries any other ontology with a 7-digit tail. A plain string carries a full
  accession whose tail is not 7 digits.
- On decode, an integer key is rendered back to a zero-padded 7-digit `MS:`
  accession (`1000511` → `MS:1000511`). A string key is used verbatim.

Producers and consumers **MUST** resolve the *meaning* of accessions against
the official [PSI-MS CV][psims] and [UO][uo]. The reference implementation
currently sources its accession constants from the `mzmlpy` library. This is an
implementation detail and is **not** normative. The normative source of truth
is the PSI-MS CV.

> **Note.** spectrl introduces no new CV terms: every accession it uses is an
> existing PSI-MS or UO term with its published meaning. Should a future
> revision need a new term (e.g. a new codec), registration in the PSI-MS CV
> via the [HUPO-PSI/psi-ms-CV][psimscv] repository is the intended route, as
> for any tool that extends the vocabulary.

## 6. Header

The token payload is a single [CBOR][cbor] map with **integer keys**, encoded
deterministically (RFC 8949 §4.2). Keys mirror the mzML `<spectrum>` element.
Each peak array's compressed blob is embedded inline in its descriptor as a CBOR
**byte string** ([§7.1](#71-array-descriptors)).

| Key | Name | Type | Required | Meaning |
|----:|------|------|:--------:|---------|
| 0 | `defaultArrayLength` | int | ✔ | Number of peaks. May be `0` (an empty spectrum is valid). |
| 1 | `id` | str | | Native spectrum identifier (e.g. `scan=42`). |
| 2 | `params` | map | | Spectrum-level CV param map ([§6.1](#61-cv-param-map)). |
| 3 | `scanList` | map | | Scan list ([§6.2](#62-scan-list)). |
| 4 | `precursorList` | array | | Precursors ([§6.3](#63-precursor)). |
| 5 | `productList` | array | | Products ([§6.4](#64-product)). |
| 6 | `binaryDataArrayList` | array | | Array descriptors ([§7.1](#71-array-descriptors)). |
| 7 | `interp` | str | | ProForma 2.0 interpretation string ([§6.6](#66-proforma-interpretation)). |
| 8 | `userParamList` | array | | Spectrum-level free-text user params ([§6.5](#65-user-params)). |

All keys except 0 are OPTIONAL and **MUST** be omitted entirely when empty.
a consumer **MUST** treat a missing key as "absent" (e.g. no user params), so a
spectrum that uses none of an OPTIONAL feature is byte-identical to one produced
before that feature existed.

**Unknown and duplicate keys.** A consumer **MUST** ignore a top-level integer
key it does not recognise (this is how OPTIONAL keys are added
backward-compatibly, [§9](#9-versioning)). A consumer that re-emits a token
SHOULD preserve such keys. A CBOR map with **duplicate keys** is not
well-formed under RFC 8949 §4.2. A consumer **MUST** reject a document
containing a duplicate map key at any level.

### 6.1 CV param map

A CV param map encodes a list of CV parameters as a CBOR map of
`tail-key → value`:

- **tail-key** is the encoded accession per [§5](#5-controlled-vocabulary-binding)
  (bare int tail for `MS:`, full accession string otherwise).
- **value** is one of:
  - `null`: a value-less term (a flag, e.g. positive-scan).
  - a scalar (int / float / str): a term with a value and no unit.
  - a 2-element array `[value, unit]`: a value with a unit accession, where
    `unit` is encoded per the unit rules of [§5](#5-controlled-vocabulary-binding).

### 6.2 Scan list

Key 3 is a map:

- `"s"` → array of **scan** maps (REQUIRED if key 4 present).
- `"c"` → integer tail of a spectrum-combination CV term (OPTIONAL). Combination
  terms are value-less flags. Only the tail is carried.

Each **scan** map:

- key `0` → CV param map for the scan.
- key `1` → array of **scan window** CV param maps (OPTIONAL).
- key `2` → array of **user param** maps ([§6.5](#65-user-params)) for the scan (OPTIONAL).

### 6.3 Precursor

Each entry of key 4 is a map:

- key `0` → isolation-window CV param map (OPTIONAL).
- key `1` → array of selected-ion CV param maps (OPTIONAL).
- key `2` → activation CV param map (OPTIONAL).

### 6.4 Product

Each entry of key 5 is a map:

- key `0` → isolation-window CV param map (OPTIONAL).

### 6.5 User params

A **user param** carries an mzML `userParam`, a free-text parameter with **no**
CV accession. Producers **SHOULD** prefer a CV term ([§6.1](#61-cv-param-map))
whenever one exists. User params are for values with no controlled vocabulary
term. Each user param is a map with string keys:

- `"n"` → param name (str, REQUIRED).
- `"v"` → value (scalar int / float / str, OPTIONAL).
- `"t"` → XSD data-type annotation string (e.g. `xsd:float`, OPTIONAL).
- `"u"` → unit accession, encoded per the unit rules of [§5](#5-controlled-vocabulary-binding) (OPTIONAL).

User params appear spectrum-level (header key 8) and per-scan (scan map key 2).
Both are OPTIONAL arrays, omitted entirely when empty.

### 6.6 ProForma interpretation

Key 7 carries a peptidoform interpretation as a [ProForma 2.0][proforma]
string. Producers **SHOULD** emit valid ProForma 2.0. Consumers **MUST** treat
the string as opaque for the purposes of token decoding: an unparseable
interpretation string is not grounds for rejecting the token (the spectrum data
stands on its own).

## 7. Peak arrays

### 7.1 Array descriptors

Key 6 of the header is an array of **descriptor** maps, one per peak array.
Descriptors are **integer-keyed**, like the header itself: the field names are a
fixed vocabulary, and spelling them out on every array of every token cost more
bytes than the values they labelled.

| Key | Name | Type | Required | Meaning |
|----:|------|------|:--------:|---------|
| 0 | `type` | int | ✔ | CV tail of the binary data type: `MS:1000523` 64-bit float, `MS:1000521` 32-bit float, `MS:1000519` 32-bit integer. A consumer **MUST** reconstruct the array in the declared type. |
| 1 | `array` | int | ✔ | CV tail of the array type. Standard: `MS:1000514` m/z, `MS:1000515` intensity, `MS:1000516` charge, ion-mobility array terms. Any other binary-data-array CV term is permitted (e.g. `MS:1000517` signal-to-noise array). `MS:1000786` (non-standard data array) denotes an array whose meaning is given by key 4. |
| 2 | `comp` | int | ✔ | CV tail of the compression codec ([§7.2](#72-codecs)). |
| 3 | `fp` | int | conditional | Numpress fixed scale factor, a positive whole number. **REQUIRED** for linear and slof codecs and **MUST NOT** appear for codecs that do not use a fixed point ([§7.2](#72-codecs)). |
| 4 | `name` | str | | Free-text descriptor name. **REQUIRED** when key 1 is `MS:1000786` (non-standard data array). **MUST NOT** appear otherwise. Values **MUST** be unique among a token's non-standard arrays. |
| 5 | `d` | bytes | ✔ | The array's compressed blob, embedded inline as a CBOR byte string. |
| 6 | `unit` | int, pair, or str | | Optional CV unit accession, encoded using the same compact forms as cvParam units. |

The names above are documentation only. They never appear on the wire. A
consumer **MUST** ignore a descriptor key it does not recognise, which is how
OPTIONAL descriptor fields are added backward-compatibly ([§9](#9-versioning)).

A consumer **MUST** decode each array from its descriptor's key 5 byte string
using the decoder selected from key 2. Descriptor order is not semantically
significant. Key 1 (plus key 4 for non-standard arrays) identifies meaning.
Every decoded array **MUST** contain exactly `defaultArrayLength` (key 0)
values. A consumer **MUST** reject the token otherwise.

When key 6 is present, it identifies the unit of every value in that array. A
producer **MUST** include it when the array term permits multiple units and the
unit is known; this includes drift-time arrays that may be seconds or
milliseconds. Consumers **MUST** accept legacy descriptors that omit it.

**Additional arrays.** Beyond the dedicated m/z / intensity / charge fields, a
producer **MAY** include additional per-peak arrays: any binary-data-array CV
term by its accession, or arbitrary arrays via `MS:1000786` + `name`. Ion-
mobility arrays use their specific PSI-MS accessions in this collection, and a
spectrum MAY contain multiple different ion-mobility array terms. These are
parallel to the peak list (same `defaultArrayLength`) and are permuted with it
under the canonical m/z sort ([§8](#8-canonical-form-and-checksum)). A consumer
that does not recognise an `array` term **MUST** still preserve the decoded
values (keyed by accession or `name`) rather than discard them.

Standard binary-array identities in key 1 are PSI-MS terms and therefore use
the `MS:` namespace. Producers MUST NOT discard another ontology prefix and
encode only its numeric tail. A future seven-digit PSI-MS array accession MAY
be carried even when it is absent from a consumer's local registry.

### 7.2 Codecs

| `comp` tail | CV term | Mode | Applies to |
|------------:|---------|------|------------|
| `1002746` | MS-Numpress linear prediction + zlib | lossy | m/z, ion mobility |
| `1002748` | MS-Numpress short logged float + zlib | lossy | intensity |
| `1002747` | MS-Numpress positive integer + zlib | lossy | charge |
| `1000574` | zlib | lossless | any (raw IEEE-754) |
| `1003780` | zstd | lossless | any raw numeric array |
| `1003781` | byte-shuffled zstd | lossless | any raw numeric array |
| `1003783` | MS-Numpress linear prediction + zstd | lossy | coordinate arrays |
| `1003784` | MS-Numpress positive integer + zstd | lossy | integer arrays |
| `1003785` | MS-Numpress short logged float + zstd | lossy | positive magnitude arrays |

- In **lossy** mode (default), m/z uses numpress-linear, intensity uses
  numpress-slof, charge uses numpress-pic, each followed by zlib.
- The `fp` fixed point is a **positive whole number** no greater than
  `9007199254740991`, carried as a CBOR integer. Boolean values are not integers.
  For the linear and slof codecs (which take a scale factor), a producer
  **MUST** record the fp it actually used. The recorded value **MUST** equal the
  fixed point embedded in the Numpress stream. A consumer **MUST** reject a
  linear or slof descriptor that omits `fp` or disagrees with the stream. The pic
  codec takes no scale factor and its descriptor **MUST NOT** carry `fp`.
- The numpress transforms cannot represent **negative values** (pic and slof
  mathematically, and linear because implementations disagree on rounding negatives).
  In lossy mode a producer **MUST** fall back to the lossless `1000574` codec
  for any array containing a negative value (e.g. negative charge sentinels or
  baseline-subtracted intensities). Negative m/z values are invalid and **MUST**
  be rejected at encode time.
- A producer **MUST** reject an explicitly selected codec that is incompatible
  with the array semantics: linear is for continuous coordinates, slof for
  non-negative magnitudes, and pic for non-negative whole numbers. Unknown and
  non-standard arrays remain lossless by default because their semantics are
  not known. An expert API MAY permit an explicit lossy override for such an
  array, but it MUST require a separate opt-in and MUST still enforce the
  codec's numeric domain.
- A descriptor whose `comp` is a numpress codec **MUST** declare `type`
  `1000523` (64-bit float). The numpress transforms are defined over float64.
- In **lossless** mode, every array is raw little-endian IEEE-754 float64
  or its declared float32 or int32 representation, followed by a lossless
  compressor. `fp` is absent.
- In default lossy mode, ion-mobility and known additional coordinate arrays may use linear,
  known positive magnitude arrays may use slof, and known non-negative integer
  arrays may use pic. Unknown and non-standard auxiliary arrays remain lossless
  unless the caller explicitly opts into responsibility for a lossy codec.
- Byte shuffle groups the first byte of every value, then the second byte of
  every value, continuing through the declared type width before applying
  zstd. Decoding reverses this transform before interpreting the declared type.
- zlib remains the canonical default outer compressor. Producers may expose
  zstd as an explicit per-array choice. A decoder supporting the corresponding
  `comp` tail must accept either pipeline.

A consumer encountering a `comp` tail it does not implement **MUST** fail
cleanly rather than return wrong peaks.

## 8. Canonical form and checksum

A token is in **canonical form** when:

1. peaks are sorted by m/z ascending (stable sort), with all parallel arrays
   (intensity, charge, and all additional arrays, including ion mobility) permuted
   identically.
2. float arrays contain no `NaN` or infinite values (producers **MUST** reject
   such input).
3. empty/absent header keys are omitted (never present-but-empty).
4. numpress fixed-point scale factors are the canonical defaults, and are whole
   numbers:
   - **linear** (m/z, ion mobility): `fp = 100000`.
   - **slof** (intensity): `fp = floor(min(3600, 65535 / ln(max_intensity + 1)))`,
     i.e. the default `3600` clamped so that no encoded value overflows the codec's
     uint16 range. The clamp **MUST** round **down**: the ceiling it enforces is an
     upper bound, so a smaller fp is always safe while a larger one can overflow.
     A producer **MUST** encode the array with the same whole-number fp it records.
     Every linear and slof descriptor carries this value, including when it equals
     the default above ([§7.1](#71-array-descriptors)).
5. array descriptors are emitted in a fixed order: m/z, intensity, charge,
   then all additional arrays ([§7.1](#71-array-descriptors)) sorted ascending
   by their key (CV accession string, or `name` for non-standard arrays). This
   keeps a producer's token text reproducible.
6. the CBOR document uses definite lengths and the deterministic map-key
   ordering of RFC 8949 §4.2. Preferred (shortest-form) serialization of
   floats is RECOMMENDED but not required. The checksum is computed over
   the emitted token text ([below](#8-canonical-form-and-checksum)), so
   float-width choices do not affect interoperability.

The **checksum** is the REQUIRED fourth token part ([§4](#4-token-structure)).
It is the CRC-32/ISO-HDLC value of the ASCII text of the token's first three
parts (the string `"spectrl.v1." payload`, with no trailing `.`), encoded as
exactly eight lowercase hexadecimal characters, including leading zeroes. It
covers the identifier, version, and entire CBOR document, array blobs included.

Verification is defined over the received text, not over any decoded
structure: a consumer takes everything before the last `.` exactly as
received, computes CRC-32/ISO-HDLC, formats it as eight lowercase hexadecimal
characters, and compares. It requires no CBOR parsing and is independent of
the CBOR library a consumer uses.

Every consumer **MUST** recompute the checksum and **MUST** reject the token on
mismatch. The checksum is a **per-token integrity check**: it detects accidental
corruption of *that* token. It is not a cryptographic authentication code (see
[§12](#12-security-and-privacy-considerations)). It is also not a stable
cross-implementation content identifier. Because the compressed array blobs
(DEFLATE) are not canonical across implementations, two implementations
encoding the same spectrum MAY produce different tokens and different checksums.
A canonical content identifier defined over the *decoded* data is possible future
work and is out of scope for this version.

## 9. Versioning

- The format version is carried in the magic (`spectrl.v1`) and **only** there
  ([§4](#4-token-structure)).
- A **backward-compatible** change (new OPTIONAL header key, new codec
  registered in PSI-MS CV) keeps version `1`.
- A **breaking** change (altered framing, altered semantics of an existing key,
  removed key) **MUST** increment the version, producing `spectrl.v2`, and so on.
- The library (semver) version is independent of the format version.
- `spectrl.v1` is frozen as of the stable 1.0.0 library release. Existing
  required fields and semantics will not change within this format version.

## 10. URI bindings

A token MAY be transported as:

- **URL fragment**: `<base>#spectrl.v1.…`. This binding is RECOMMENDED because
  the fragment is not sent to the server, which avoids access-log leakage and
  most length limits.
- **URL query parameter**: `<base>?d=spectrl.v1.…`.
- **data URI**: `data:application/vnd.spectrl;v=1,spectrl.v1.…`.

> **Note.** The `application/vnd.spectrl` media type is provisional pending
> IANA vendor-tree registration. See [§13](#13-iana-considerations).

## 11. Conformance

A **conformant producer**:

- emits tokens that satisfy [§4](#4-token-structure)–[§8](#8-canonical-form-and-checksum).
- emits canonical form ([§8](#8-canonical-form-and-checksum)).
- emits unpadded base64url.
- includes the CRC-32 checksum (fourth token part).

A producer **MAY** omit any OPTIONAL key it chooses not to carry. In particular
it may omit free-text user params (key 8 and scan-map key `2`, [§6.5](#65-user-params))
while retaining every CV param: vendor trailers are frequently a large share of a
small MS2 token and commonly restate CV params the token already carries. Such a
token is conformant, and a consumer **MUST NOT** treat missing user params as an
error ([§6](#6-header)). The omitted values are not recoverable from the token,
so a producer whose goal is faithful mzML round-tripping **SHOULD** retain them.

A **conformant consumer**:

- rejects unsupported magic/version ([§4](#4-token-structure), [§9](#9-versioning)).
- requires and verifies the checksum ([§8](#8-canonical-form-and-checksum)).
- fails cleanly on unimplemented codecs ([§7.2](#72-codecs)).
- reconstructs all arrays from their `array` descriptors rather than position,
  and verifies each decoded array's length against key 0 ([§7.1](#71-array-descriptors)).
- bounds decompression while decoding ([§12](#12-security-and-privacy-considerations)).

A language-agnostic test-vector suite (token ↔ decoded spectrum pairs) is
REQUIRED for interoperability validation and is maintained in
[`test-vectors/`](test-vectors/) (forward vectors produced by the Python
reference implementation, reverse vectors by the JavaScript implementation,
and shared negative vectors that both must reject).
see [`schema/registry.json`](schema/registry.json) for the machine-readable
CV/codec/key registry.

## 12. Security and privacy considerations

- A spectrl token **embeds data**. Sharing a token shares the spectrum. Anyone
  with the token has the data. Producers handling sensitive or clinical data
  **MUST** account for this.
- Tokens placed in URL **query strings** or **paths** may be recorded in server
  access logs, proxies, and browser history. The URL **fragment** binding
  ([§10](#10-uri-bindings)) is RECOMMENDED to avoid this.
- The checksum is an **integrity** check only. It does not authenticate the
  producer and provides no protection against a deliberate adversary who
  recomputes it. Consumers requiring authenticity **MUST** use an external
  signature mechanism.
- The checksum is not canonical across implementations because compressed token
  bytes may differ ([§8](#8-canonical-form-and-checksum)). It **MUST NOT** be used as a
  content identifier or deduplication key.
- Consumers **MUST** treat token contents as untrusted input: reject malformed
  CBOR, and **bound decompression**. A conforming bound: a raw (`1000574`,
  `1003780`, or `1003781`)
  blob decompresses to exactly `defaultArrayLength × sizeof(type)` bytes, and a
  numpress blob to at most `24 + 8 × defaultArrayLength` bytes. A consumer
  **MUST** abort decompression once the output exceeds such a bound (the
  reference implementations use `64 + 16 × defaultArrayLength`, with a hard
  64 MiB ceiling), rather than decompressing fully and checking afterwards.
  They also reject payloads above 16 MiB, CBOR nesting deeper than 32 levels,
  documents with more than 100,000 items, and declared peak counts above
  4,000,000.

## 13. IANA considerations

This section drafts the vendor-tree media-type registration to be submitted as
part of standardization ([RFC 6838][rfc6838]):

- **Type name:** `application`
- **Subtype name:** `vnd.spectrl`
- **Required parameters:** none
- **Optional parameters:** `v`, the spectrl format version (currently `1`). If
  present it **MUST** match the token's magic version.
- **Encoding considerations:** the payload is an ASCII token
  (`spectrl.v1.<base64url>.<checksum>`), safe for 7-bit transports.
- **Security considerations:** see
  [§12](#12-security-and-privacy-considerations): embedded scientific data,
  untrusted-input decoding, decompression bounding.
- **Interoperability considerations:** conformance requirements and test
  vectors per [§11](#11-conformance).
- **Published specification:** this document.
- **Contact:** the editor ([§15](#15-author-information)).

## 14. Pending issues and future developments

- A **canonical content identifier** defined over the decoded data, stable
  across implementations. The checksum of
  [§8](#8-canonical-form-and-checksum) is a per-token integrity check and
  deliberately not that identifier.
- **IANA registration** of the `application/vnd.spectrl` media type
  ([§13](#13-iana-considerations)).
- **New CV terms**, should a future revision need one (e.g. a new codec):
  registration in the PSI-MS CV via [HUPO-PSI/psi-ms-CV][psimscv] is the
  intended route ([§5](#5-controlled-vocabulary-binding)).
- **Submission to the HUPO-PSI Document Process**, should the format see
  community adoption. This document already follows the PSI specification
  structure to ease that step.

## 15. Author information

- Patrick Garrett (editor), Integrated Computational and Structural Biology,
  The Scripps Research Institute, La Jolla, CA, USA.
  <pgarrett@scripps.edu>

## 16. Contributors

Contributions to this specification, the registry, the test vectors, and the
reference implementations are recorded in the repository history at
<https://github.com/pgarrett-scripps/spectrl>. Feedback and proposals are
received as issues and pull requests in the same repository.

## 17. Intellectual property statement

The spectrl project takes no position regarding the validity or scope of any
intellectual property or other rights that might be claimed to pertain to the
implementation or use of the technology described in this document. This
document, the machine-readable registry, the test vectors, and the reference
implementations are licensed under the [Apache License, Version
2.0](LICENSE), whose Section 3 grants each recipient an express patent license
from each contributor for their contributions. No permission is required to
implement this specification.

## 18. Copyright notice

Copyright 2026 Patrick Garrett and the spectrl contributors. Licensed under
the Apache License, Version 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

## 19. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | August 2026 | Frozen `spectrl.v1` specification: integer-keyed array descriptors with optional units, explicit Numpress fixed points, accession-keyed auxiliary arrays, and a required CRC-32 checksum. The format version is carried only in the prefix. |
| ≤ 0.2 | 2025–2026 | Development revisions. Tokens from these revisions are not compatibility artifacts. |

The full change history, including library releases, is maintained in
[CHANGELOG.md](CHANGELOG.md).

## 20. References

- [RFC 2119][rfc2119], [RFC 8174][rfc8174]: requirement keywords
- [RFC 4648][rfc4648]: base64url
- [RFC 1950][rfc1950]: zlib
- [RFC 6838][rfc6838]: media type specifications and registration procedures
- [PSI-MS controlled vocabulary][psims] / [HUPO-PSI/psi-ms-CV][psimscv]
- [ProForma 2.0][proforma]
- [mzPAF][mzpaf]
- [CBOR][cbor] (RFC 8949)

[rfc2119]: https://www.rfc-editor.org/rfc/rfc2119
[rfc6838]: https://www.rfc-editor.org/rfc/rfc6838
[rfc8174]: https://www.rfc-editor.org/rfc/rfc8174
[rfc4648]: https://www.rfc-editor.org/rfc/rfc4648
[rfc1950]: https://www.rfc-editor.org/rfc/rfc1950
[psims]: https://www.ebi.ac.uk/ols4/ontologies/ms
[psimscv]: https://github.com/HUPO-PSI/psi-ms-CV
[proforma]: https://www.psidev.info/proforma
[mzpaf]: https://www.psidev.info/mzPAF
[uo]: https://www.ebi.ac.uk/ols4/ontologies/uo
[cbor]: https://www.rfc-editor.org/rfc/rfc8949
