# @spectrl-ms/spectrl

JavaScript / TypeScript implementation of the **spectrl.v3** inline-spectrum token
format. Encodes peak arrays and modeled spectrum metadata into a compact,
URL-safe string and back, with no backend required. Runs in the browser and in
Node.

This package is a separate implementation of the format specified in
[`SPECIFICATION.md`](https://github.com/tacular-omics/spectrl/blob/main/SPECIFICATION.md) and is validated against the shared
conformance vectors in [`test-vectors/`](https://github.com/tacular-omics/spectrl/tree/main/test-vectors).
It also produces the same complete tokens as Python for the tested inputs and
settings: all 1,788 comparisons matched, including both encoding profiles and
raw, zlib, and Brotli payloads. Matching metadata, array dtypes, and exact core
encoding settings provide portable equality with raw payloads. Compressed and
lossy results matched in the tested runtimes, without guaranteeing equality
across arbitrary compressor versions or mathematical libraries. See
[token reproducibility](../docs/token-reproducibility.md) for results and scope.

## Install

```bash
npm install @spectrl-ms/spectrl
```

Version 3.0.0 requires Node 22+ and exports ESM JavaScript and TypeScript
declarations. Browser applications can bundle the same package. Decoder budgets
are available in v3. The token format remains `spectrl.v3`.

## Usage

```ts
import { encodeSpectrum, decodeToken, toFragment, extractToken } from "@spectrl-ms/spectrl";

const token = encodeSpectrum({
  defaultArrayLength: 3,
  mz: [147.0, 175.1, 246.2],
  intensity: [1e5, 8e4, 3e4],
  id: "scan=42",
  params: [
    { accession: "MS:1000511", value: 2 }, // ms level
    { accession: "MS:1000130" },           // positive scan
    { accession: "MS:1000127" },           // centroid spectrum
  ],
});
// "spectrl.v3.z.…"

const spec = decodeToken(token);
spec.mz;        // Float64Array
spec.intensity; // Float64Array
spec.id;        // "scan=42"

// Embed in a URL fragment (never sent to the server) and extract it back:
const url = toFragment(token, "https://viewer.example.com/spectrum");
extractToken(url) === token; // true
```

### Lossless encoding

```ts
// Default is a bounded lossy profile. Use lossless for bit-exact native arrays:
const token = encodeSpectrum(spec, { lossless: true })
```

Lossless encoding uses modular delta plus byte shuffle for m/z, byte shuffle
for intensity, and raw typed words for auxiliary arrays. Default lossy encoding
keeps, per array, the smallest of the exact encoding and bounded candidates.
m/z tries a logarithmic grid calibrated to a maximum error of 0.1 ppm per source
value. Nonnegative intensity tries exact integer words for counts, floats
rounded to 12 mantissa bits (encoding 4, relative error at most 2^-13), and a
log1p grid with scale 3600, refined when the smallest positive intensity is
below 1 so none rounds to zero. Ties and unsupported domains keep the exact
encoding. Size is measured as encoded array bytes for `raw` payloads and as
zlib level 6 output otherwise, so pass the token's `compression` to
`encodingPlan`.
Integer and auxiliary arrays remain exact. Both profiles default to one zlib
compression pass over the complete CBOR document.

Payload compression is independent of fidelity:

```ts
encodeSpectrum(spec, { lossless: true, compression: "zlib" })
encodeSpectrum(spec, { compression: "auto" })
```

Choices are `raw`, `zlib` (level 6), and `brotli` (quality 5).
Initialize Brotli with `await installBrotli()` from `@spectrl-ms/spectrl/brotli`.
This uses native Node support or browser WebAssembly. Browser bundlers must
serve the Brotli WASM asset beside the generated entry module.
Explicit `auto` compares available backends, with ties preferring zlib, raw, then Brotli. The selected mode is stored in the token.
An explicit unavailable backend raises an error.

### Per-array encoding

```ts
const token = encodeSpectrum(spec, {
  lossless: true,
  arrayEncodings: {
    mz: "modular-delta-shuffle",
    intensity: "byte-shuffle",
    iso_score: "raw",
  },
})
```

The five core encodings are raw (0), byte shuffle (1), modular delta plus shuffle
(2), quantized words (3), and rounded floating-point words (4, `rounded-float`,
parameters `bits` and `width`). Compression applies once to the complete document.
Auxiliary arrays stay exact by default. Custom namespaced encodings use trusted
callbacks registered explicitly. Unknown custom array semantics require
`allowUnsafeLossyCustom: true` before applying an explicit lossy encoding.

## API

- `encodeSpectrum(spec, options?) => string`, with lossless, size, warning,
  user-param omission, per-array codec, and unsafe-custom-codec options
- `decodeToken(token, limits?) => DecodedSpectrum`, verifying the checksum and
  the token-byte, peak-count, array-count, and total decoded-byte budgets
- `DecodeLimits`, `DEFAULT_DECODE_LIMITS` (applied when `limits` is omitted), and
  `UNLIMITED_DECODE_LIMITS` (the format ceilings, for a trusted producer)
- `SpectrlDecodeError` identifies malformed, unsupported, and over-budget tokens
- `encodingPlan(spec, options?)` reports resolved codecs, fixed points, types, and units
- `tokenBreakdown(token)` reports compressed array and header sizes
- `encodingReport(spec, options?)` measures encoding error against the source
- `fitToBudget(spec, maxBytes, options?)` proposes explicitly permitted omissions
- `parsePeakList(text)`, `formatPeakList(spec, delimiter?)`, and `topN(spec, n)`
- `toFragment(token, base)`, `toQuery(token, base, param?)`, `toDataUri(token)`, `extractToken(urlOrUri)`

See the [service integration guide](https://github.com/tacular-omics/spectrl/blob/main/docs/services.md)
for runnable Python-to-Node examples, budget defaults, precision policy, and
worker guidance. Decoding is synchronous. Set ingress and concurrency limits
in the consuming service as well as per-token decoder budgets.

Brotli is an optional capability. Call `await installBrotli()` from the
`/brotli` entry point in each execution context that accepts Brotli tokens.
The same setup works in workers.

## Develop

```bash
npm install
npm test         # node:test against ../test-vectors + round-trip
npm run build    # emit dist/ (ESM + d.ts)
npm run typecheck
```

## License

Apache-2.0. See [LICENSE](https://github.com/tacular-omics/spectrl/blob/main/LICENSE).

**Quality and sharing workflows**

`encodingReport`, `fitToBudget`, `parsePeakList`, `formatPeakList`, and `topN`
are exported from the main package. The [workflow guide](https://github.com/tacular-omics/spectrl/blob/main/docs/workflows.md)
includes examples and documents zero-reference error metrics, explicit
omission permissions, complete URL budgets, and peak-list limitations.

CI covers Node 22 and 24, matching the current Node 22 package minimum.

## Token format

`formatForPath`, `readText`, `listSpectra` and `write` convert between tokens
and mzML, MGF and MS2. The writers run anywhere; reading mzML uses `DOMParser`,
so it needs a browser. Each writer returns a `ConversionResult` naming what the
target format could not represent.

The `spectrl.v3` header uses keys 0 through 12. Spectrum-level free-text
parameters use key 7, and key 12 records the source-declared ontology version
for each accession prefix. Identifications and fragment assignments belong in
the surrounding application.

## V3 operations

```ts
const token = encodeSpectrum(spectrum, {
  lossless: true,
  arrayEncodings: {
    mz: { encoding: "modular-delta-shuffle", compression: "zlib" },
    intensity: "MS:1003782",
  },
})
```

`registerEncoding`, `registerCompressor`, and `registerExtension` accept versioned
namespaced IDs. Custom code is installed locally and never loaded from a token.
`readTokenDocument` inspects metadata and operation declarations without invoking
array decoders. Unknown required operations or extensions fail full decoding.
The decoded model preserves source, acquisition, processing, nested user parameters,
and per-array metadata. Core Float32Array and Int32Array retain their types in
lossless mode. Sorting and selection require explicitly updating or removing
extensions that might depend on array content or order.

### Outer payload compression

Tokens use `spectrl.v3.<mode>.<payload>.<checksum>`. Mode `z` is the default
zlib-compressed CBOR. Mode `r` is raw CBOR and `b` is Brotli.
All use unpadded base64url. Only `r` and `z` are required reader capabilities.
Optional `auto` selection is described above.
The checksum includes the mode and is checked before bounded decompression.
The expanded CBOR limit is 16 MiB, including during metadata inspection.
