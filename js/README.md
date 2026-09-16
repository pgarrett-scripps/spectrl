# @spectrl-ms/spectrl

JavaScript / TypeScript implementation of the **spectrl.v2** inline-spectrum token
format. Encodes peak arrays and modeled spectrum metadata into a compact,
URL-safe string and back, with no backend required. Runs in the browser and in
Node.

This package is a separate implementation of the format specified in
[`SPECIFICATION.md`](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) and is validated against the shared
conformance vectors in [`test-vectors/`](https://github.com/pgarrett-scripps/spectrl/tree/main/test-vectors). It decodes tokens
produced by the Python reference implementation byte-for-byte (including the
MS-Numpress codecs and the CRC-32 transport checksum).

## Install

```bash
npm install @spectrl-ms/spectrl
```

Version 2.1.0 requires Node 22+ and exports ESM JavaScript and TypeScript
declarations. Browser applications can bundle the same package. Decoder budgets
are available starting in 2.1.0. The token format remains `spectrl.v2`.

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
// "spectrl.v2.hQ..."

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
// Default is lossy MS-Numpress. Use lossless for bit-exact IEEE-754 doubles:
const token = encodeSpectrum(spec, { lossless: true });
```

### Per-array encoding

```ts
import { installZstd } from "@spectrl-ms/spectrl/zstd";

installZstd();

const token = encodeSpectrum(spec, {
  arrayEncodings: {
    mz: "numlin-zstd",
    "MS:1000517": { codec: "numslof-zstd", fixedPoint: 3600 },
    iso_score: "byte-shuffled-zstd",
  },
});
```

Known PSI-MS auxiliary arrays receive semantic Numpress defaults. Unknown arrays
remain lossless raw + zlib. Supported explicit codecs include zlib, zstd,
byte-shuffled zstd, and all three Numpress transforms followed by zlib or zstd.
Expert callers may combine `allowUnsafeLossyCustom: true` with an explicit
codec for a semantically unknown custom array.

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

Zstd is an intentional installed dependency. The core import does not initialize
its WASM backend. Call `installZstd()` from the `/zstd` entry point once in each
execution context before accepting zstd tokens. The same setup works in workers.

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

The `spectrl.v2` header uses keys 0 through 7. Spectrum-level free-text
parameters use key 7. Identifications and fragment assignments belong in
the surrounding application.
