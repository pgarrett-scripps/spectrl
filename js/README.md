# @spectrl-ms/spectrl

JavaScript / TypeScript implementation of the **spectrl.v3** inline-spectrum token
format. Encodes peak arrays and modeled spectrum metadata into a compact,
URL-safe string and back, with no backend required. Runs in the browser and in
Node.

This package is a separate implementation of the format specified in
[`SPECIFICATION.md`](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) and is validated against the shared
conformance vectors in [`test-vectors/`](https://github.com/pgarrett-scripps/spectrl/tree/main/test-vectors). It decodes tokens
produced by the Python reference implementation byte-for-byte (including the
core numeric encodings and the CRC-32 transport checksum).

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
// Default is lossy quantization. Use lossless for bit-exact native arrays:
const token = encodeSpectrum(spec, { lossless: true })
```

Lossless encoding uses modular delta plus byte shuffle for m/z, byte shuffle
for intensity, and raw typed words for auxiliary arrays. Default lossy encoding
uses one quantized-word layout with a logarithmic m/z grid calibrated to a
maximum error of 0.1 ppm per source value, and a log1p intensity grid with
scale 3600. Zero m/z remains exact. Unsupported quantization falls back to
exact encoding.
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

The four core encodings are raw (0), byte shuffle (1), modular delta plus shuffle
(2), and quantized words (3). Compression applies once to the complete document.
Auxiliary arrays stay exact by default. Custom namespaced encodings use trusted
callbacks registered explicitly. Unknown custom array semantics require
`allowUnsafeLossyCustom: true` before applying an explicit lossy encoding.

## API

- `encodeSpectrum(spec, options?) => string`, with lossless, size, warning,
  user-param omission, per-array codec, and unsafe-custom-codec options
- `decodeToken(token, limits?) => DecodedSpectrum`, verifying the checksum and
  optional token-byte, peak-count, array-count, and total decoded-byte budgets
- `DecodeLimits` and `DEFAULT_DECODE_LIMITS` describe the optional service budgets
- `SpectrlDecodeError` identifies malformed, unsupported, and over-budget tokens
- `encodingPlan(spec, options?)` reports resolved codecs, fixed points, types, and units
- `tokenBreakdown(token)` reports compressed array and header sizes
- `encodingReport(spec, options?)` measures encoding error against the source
- `fitToBudget(spec, maxBytes, options?)` proposes explicitly permitted omissions
- `parsePeakList(text)`, `formatPeakList(spec, delimiter?)`, and `topN(spec, n)`
- `toFragment(token, base)`, `toQuery(token, base, param?)`, `toDataUri(token)`, `extractToken(urlOrUri)`

See the [service integration guide](https://github.com/pgarrett-scripps/spectrl/blob/main/docs/services.md)
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

Apache-2.0. See [LICENSE](https://github.com/pgarrett-scripps/spectrl/blob/main/LICENSE).

**Quality and sharing workflows**

`encodingReport`, `fitToBudget`, `parsePeakList`, `formatPeakList`, and `topN`
are exported from the main package. The [workflow guide](https://github.com/pgarrett-scripps/spectrl/blob/main/docs/workflows.md)
includes examples and documents zero-reference error metrics, explicit
omission permissions, complete URL budgets, and peak-list limitations.

CI covers Node 22 and 24, matching the current Node 22 package minimum.

## Token format

The `spectrl.v3` header uses keys 0 through 11. Spectrum-level free-text
parameters use key 7. Identifications and fragment assignments belong in
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
