# @spectrl-ms/spectrl

JavaScript / TypeScript implementation of the **spectrl.v1** inline-spectrum token
format. Encodes peak arrays and modeled spectrum metadata into a compact,
URL-safe string and back, with no backend required. Runs in the browser and in
Node.

This package is a separate implementation of the format specified in
[`SPECIFICATION.md`](../SPECIFICATION.md) and is validated against the shared
conformance vectors in [`test-vectors/`](../test-vectors). It decodes tokens
produced by the Python reference implementation byte-for-byte (including the
MS-Numpress codecs and the CRC-32 transport checksum).

## Install

> Not yet published to npm. Until then, build from source (below) or depend on
> this directory directly (`"@spectrl-ms/spectrl": "file:../js"`).

```bash
npm install @spectrl-ms/spectrl   # once published
```

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
// "spectrl.v1.hQ..."

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

- `encodeSpectrum(spec, { lossless?, maxLen?, quiet?, arrayEncodings? }) => string`
- `decodeToken(token) => DecodedSpectrum` (verifies the trailing CRC-32 checksum, throws on mismatch)
- `encodingPlan(spec, options?)` reports resolved codecs, fixed points, types, and units
- `toFragment(token, base)`, `toQuery(token, base, param?)`, `toDataUri(token)`, `extractToken(urlOrUri)`

## Develop

```bash
npm install
npm test         # node:test against ../test-vectors + round-trip
npm run build    # emit dist/ (ESM + d.ts)
npm run typecheck
```

## License

Apache-2.0. See [../LICENSE](../LICENSE).
