# Integrating spectrl into a service

Use spectrl at the boundary where a service hands one spectrum to another
application. The producer maps its data to a spectrum object and encodes a
token. The consumer decodes it into arrays and modeled metadata. The service
owns authentication, storage, search, identification results, and rendering.

This example uses the local v3 source packages.
Python requires 3.12+. JavaScript requires Node 22+ and ships ESM
JavaScript with TypeScript declarations. CI verifies Node 22 and 24.

## Run a Python producer and Node consumer

The complete [Python producer](../examples/services/producer.py) exposes
`GET /spectra/example`. It returns a token with an explicit lossless policy.
The [Node consumer](../examples/services/consumer.mjs) bounds the HTTP response,
validates the token against application budgets, and prints the
decoded spectrum. Neither example needs mzML files or an mzML parser.

From the repository root:

```bash
python -m venv /tmp/spectrl-service-example
/tmp/spectrl-service-example/bin/pip install . fastapi uvicorn
npm --prefix js run build
cd examples/services
npm install
/tmp/spectrl-service-example/bin/uvicorn producer:app --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```bash
node examples/services/consumer.mjs http://127.0.0.1:8000/spectra/example
```

The output has three peaks in ascending m/z order. Unknown spectrum identifiers
return HTTP 404. The producer refuses a token above its byte budget with HTTP
422. The consumer exits unsuccessfully for HTTP errors, excessive response
size, malformed JSON, invalid tokens, or exceeded decoding budgets.

Both examples use the local 3.0.0 source packages and the `spectrl.v3` format.
The Node dependency links to `../../js`, so no unpublished package is fetched.
FastAPI and Uvicorn are example dependencies only. The same encoder call works
inside other service frameworks. Keep authentication and deployment policy in
your existing service.

## Set decoding budgets before accepting public input

Python:

```python
from spectrl import DecodeLimits, SpectrlDecodeError, decode_token

limits = DecodeLimits(
    max_token_bytes=256 * 1024,
    max_peaks=100_000,
    max_arrays=16,
    max_decoded_bytes=16 * 1024 * 1024,
)

def accept_token(token: str):
    try:
        return decode_token(token, limits=limits)
    except SpectrlDecodeError as exc:
        raise ValueError("Invalid spectrum or exceeded service budget") from exc
```

JavaScript and TypeScript:

```typescript
import { decodeToken, SpectrlDecodeError, type DecodeLimits } from "@spectrl-ms/spectrl"

const limits: DecodeLimits = {
  maxTokenBytes: 256 * 1024,
  maxPeaks: 100_000,
  maxArrays: 16,
  maxDecodedBytes: 16 * 1024 * 1024,
}

function acceptToken(token: string) {
  try {
    return decodeToken(token, limits)
  } catch (error) {
    if (error instanceof SpectrlDecodeError) {
      throw new Error("Invalid spectrum or exceeded service budget", { cause: error })
    }
    throw error
  }
}
```

Map rejected tokens to your framework's client-error response. Invalid limit
configuration is a programming error: Python rejects it when constructing
`DecodeLimits`, and JavaScript throws `RangeError` or `TypeError`.

| Budget | Meaning |
| --- | --- |
| Token bytes | Complete ASCII token, including its prefix and checksum |
| Peaks | Declared per-array length, including tokens with no arrays |
| Arrays | Core and auxiliary arrays combined, including empty arrays |
| Decoded bytes | Sum of declared output array sizes, accounting for float64, float32, and int32 |

All four budgets are inclusive and accept nonnegative safe integers. The token
budget is checked before base64 decoding. Array count and total output bytes
are checked across all validated descriptors before decompressing any array.
Each array consumes the size of its declared type per element: four bytes for
float32 and int32, eight for float64, including quantized and rounded arrays. Existing per-blob decompression checks still apply.

Budgets are applied by default. Omitting `limits`, passing `DecodeLimits()` in
Python, or passing `{}` in JavaScript all give 4 MiB of token, 1,000,000 peaks,
64 arrays, and 64 MiB of total decoded array data. Python exposes these as
`DEFAULT_DECODE_LIMITS` and JavaScript as the immutable `DEFAULT_DECODE_LIMITS`
object. Applications can tighten them, or raise their own budgets up to the
format ceilings, which cannot be bypassed.

The defaults are on because the ceilings alone still allow substantial
expansion: four single-byte quantized arrays at the element ceiling reconstruct
to 128 MB of float64 from a token of roughly 21 kB. They sit about an order of
magnitude above the largest spectrum in the reference corpus (217,009 peaks in
a 1.05 MB token), so ordinary data is unaffected. Reading from a producer you
trust, raise them to the ceilings explicitly with `DecodeLimits.unlimited()` in
Python or `UNLIMITED_DECODE_LIMITS` in JavaScript. Encoding is never subject to
them, so a large spectrum remains writable.

Decoded bytes measure retained array data. They exclude metadata, the token,
CBOR objects, decompression buffers, and other temporary allocations. They
are not a process-memory or CPU-time guarantee. Set HTTP request-body limits
before parsing request JSON, and bound request concurrency in the host service.
The consumer example bounds the response body before parsing it.

## Choose precision deliberately

Both encoders default to a bounded lossy profile for suitable arrays. This
is useful for compact sharing. For a service handoff that must preserve array
values, explicitly pass `lossless=True` in Python or `{ lossless: true }` in
JavaScript. Encoding sorts peaks by m/z and carries every parallel array through
that ordering. Lossless encoding does not preserve the original peak order or
unmodeled mzML XML.

Use `encoding_report` or `encodingReport` to measure error against the source
when choosing a lossy policy. Use `conversion_report(..., strict=True)` for
the Python mzML bridge when warning-level omissions must fail conversion.
Pass `run=mzml` to resolve the selected spectrum context.

The producer's `precision` field describes its chosen policy. A receiver cannot
measure error relative to an original spectrum that it does not possess. The
CRC checksum detects accidental corruption and does not authenticate a sender.

## Keep larger decodes off the JavaScript main thread

Encoding and decoding are synchronous. A JavaScript timeout cannot interrupt a
decode running on that same thread. The consumer's timeout bounds network I/O,
not codec execution. For a busy Node service, execute codec work in a bounded
worker pool and cap its queue. A parent can terminate a worker that exceeds a
deadline.

For a browser application, this module worker keeps decoding off the UI thread:

```javascript
// spectrum-worker.js, bundled by the consuming application
import { decodeToken, SpectrlDecodeError } from "@spectrl-ms/spectrl"

self.onmessage = ({ data }) => {
  try {
    const spectrum = decodeToken(data, {
      maxTokenBytes: 256 * 1024,
      maxPeaks: 100_000,
      maxArrays: 16,
      maxDecodedBytes: 16 * 1024 * 1024,
    })
    self.postMessage({ spectrum })
  } catch (error) {
    self.postMessage({ error: error instanceof SpectrlDecodeError
      ? error.message : "Could not decode spectrum" })
  }
}
```

Create it with `new Worker(new URL("./spectrum-worker.js", import.meta.url),
{ type: "module" })`, send the token with `worker.postMessage(token)`, and
handle the response in `worker.onmessage`. Terminate or reuse the worker after
completion. Structured cloning copies its typed arrays, so allow for that
additional memory or transfer their buffers in a performance-sensitive viewer.
