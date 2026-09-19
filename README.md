# spectrl

[![CI](https://github.com/pgarrett-scripps/spectrl/actions/workflows/ci.yml/badge.svg)](https://github.com/pgarrett-scripps/spectrl/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/spectrl.svg)](https://pypi.org/project/spectrl/)
[![Python](https://img.shields.io/pypi/pyversions/spectrl.svg)](https://pypi.org/project/spectrl/)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21960544.svg)](https://doi.org/10.5281/zenodo.21960544)
[![License](https://img.shields.io/github/license/pgarrett-scripps/spectrl.svg)](https://github.com/pgarrett-scripps/spectrl/blob/main/LICENSE)

**Put a mass spectrum directly in a URL.**

Encodes one spectrum's peak arrays and modeled mzML metadata into a compact,
URL-safe token. The encoded payload lives in the string. No backend is required.

```
spectrl.v3.<mode>.<base64url(payload)>.<checksum>
```

[Try the browser demo](https://pgarrett-scripps.github.io/spectrl/) ·
[Read the format specification](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) ·
[See the changelog](https://github.com/pgarrett-scripps/spectrl/blob/main/CHANGELOG.md)

[![A spectrl token embedded in a URL and decoded into a mass spectrum, with portable text, Python and JavaScript implementations, and local decoding.](https://raw.githubusercontent.com/pgarrett-scripps/spectrl/main/docs/spectrl-overview.png)](https://pgarrett-scripps.github.io/spectrl/)

*A spectrum travels as ordinary URL-safe text and decodes entirely client-side.*

## Why

Use `spectrl` to share a spectrum in a URL, QR code, notebook, paper, or
application handoff. The token contains the spectrum itself, so decoding does
not depend on an external service or file. A Universal Spectrum Identifier
(USI) points to a spectrum in a repository. Spectrl embeds the spectrum. Use a
USI when long-term repository lookup is the goal, and spectrl when a compact,
self-contained handoff is more useful.

## What's included

| Component | Purpose |
| --- | --- |
| `spectrl` Python package | Reference encoder/decoder, mzML bridge, URL helpers, and CLI |
| [`js/`](https://github.com/pgarrett-scripps/spectrl/tree/main/js) | Independent TypeScript implementation for browsers and Node |
| [`SPECIFICATION.md`](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) | Normative `spectrl.v3` wire-format specification |
| [`test-vectors/`](https://github.com/pgarrett-scripps/spectrl/tree/main/test-vectors) | Shared positive, negative, and cross-language conformance vectors |

## Install

```bash
pip install spectrl
```

Requires Python 3.12+. All core numeric encodings work in Python and Pyodide.

To install the unreleased development version:

```bash
pip install "spectrl @ git+https://github.com/pgarrett-scripps/spectrl.git"
```

The TypeScript implementation is published as `@spectrl-ms/spectrl`:

```bash
npm install @spectrl-ms/spectrl
```

For service integration, see the [producer and consumer examples](docs/services.md),
including precision policies, optional decoder budgets,
HTTP limits, and worker guidance. JavaScript requires Node
22+ and also supports browser bundlers.

## Quick start

### Encode from mzmlpy

The mzML bridge is optional. Install it with `pip install "spectrl[mzml]"`.
Applications such as Spectacular that already depend on `mzmlpy` do not need
the extra.

```python
from mzmlpy.run import Mzml
from spectrl import encode_spectrum, from_mzmlpy

with Mzml("data.mzML") as mzml:
    spec = mzml.spectra[0]
    token = encode_spectrum(from_mzmlpy(spec))

print(token)
# spectrl.v3.z.…
```

### Encode manually

```python
import numpy as np
from spectrl import encode_spectrum
from spectrl.model import InlineSpectrum, SpectrlCvParam

spec = InlineSpectrum(
    default_array_length=3,
    mz=np.array([147.0, 175.1, 246.2]),
    intensity=np.array([1e5, 8e4, 3e4]),
    id="scan=42",
    params=[
        SpectrlCvParam(accession="MS:1000511", value=2),   # ms level
        SpectrlCvParam(accession="MS:1000130"),             # positive scan
        SpectrlCvParam(accession="MS:1000127"),             # centroid
    ],
)

token = encode_spectrum(spec)
```

### Decode

```python
from spectrl import decode_token

decoded = decode_token(token)
print(decoded.mz)        # numpy array
print(decoded.intensity) # numpy array
print(decoded.id)        # "scan=42"
```

### URL bindings

```python
from spectrl import to_fragment, to_query, to_data_uri, extract_token

# Embed in a URL fragment. This is recommended because it is never sent to the server.
url = to_fragment(token, "https://viewer.example.com/spectrum")
# https://viewer.example.com/spectrum#spectrl.v3.z.…

# Or as a query parameter
url = to_query(token, "https://viewer.example.com/spectrum")
# https://viewer.example.com/spectrum?d=spectrl.v3.z.…

# Or as a data URI
uri = to_data_uri(token)
# data:application/vnd.spectrl;v=3,spectrl.v3.z.…

# Extract token back from any of the above
token = extract_token(url)
```

### Additional arrays

Beyond the dedicated m/z, intensity, and charge fields, attach any per-peak
array by PSI-MS accession (a standard mzML binary array) or by a free-text name
(a non-standard `MS:1000786` array). Every ion-mobility variant lives here, so
multiple distinct mobility arrays are preserved. `int32`/`float32` dtypes are
preserved. `ArrayAccession` provides readable string-valued enum keys while
still allowing future PSI-MS accessions as plain strings.

```python
import numpy as np
from spectrl import ArrayAccession, UnitAccession, encode_spectrum, decode_token
from spectrl.model import InlineSpectrum

spec = InlineSpectrum(
    default_array_length=3,
    mz=np.array([147.0, 175.1, 246.2]),
    intensity=np.array([1e5, 8e4, 3e4]),
    extra_arrays={
        ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY: np.array([0.82, 0.91, 1.05]),
        "MS:1000517": np.array([120.0, 80.0, 45.0]),         # signal-to-noise array (named CV)
        "iso_score": np.array([0.98, 0.91, 0.74], np.float32),  # non-standard (MS:1000786)
    },
    array_units={
        ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY:
            UnitAccession.VOLT_SECOND_PER_SQUARE_CENTIMETER,
    },
)
decoded = decode_token(encode_spectrum(spec))
decoded.extra_arrays["iso_score"]  # float32 array, round-tripped
decoded.mobility_arrays["MS:1003008"]  # accession-keyed filtered view
```

Auxiliary arrays retain their native numeric types and exact values in both
profiles. Default lossy encoding quantizes floating m/z to a maximum error of 0.1 ppm and
nonnegative floating intensity on a log1p grid. Unsupported domains use exact
encoding. JavaScript exposes the same arrays through `extraArrays`.

Override any array independently when needed:

```python
token = encode_spectrum(spec, lossless=True, array_encodings={
    "mz": "modular-delta-shuffle",
    "intensity": "byte-shuffle",
    "iso_score": "raw",
})
```

Supported names are `raw`, `byte-shuffle`, `modular-delta-shuffle`, and
`quantized`. Namespaced custom encodings can be registered explicitly.
With `lossless=True`, every array remains exact and lossy overrides are rejected.
The fixed lossless defaults are modular delta plus shuffle for m/z, byte shuffle
for intensity, and raw words for other arrays. Both profiles compress the complete
CBOR document once. There is no per-array compressor or PSI codec alias.

Unknown arrays remain exact unless the caller passes
`allow_unsafe_lossy_custom=True` with an explicit lossy encoding.
In JavaScript, enable Brotli with `await installBrotli()` from
`@spectrl-ms/spectrl/brotli` to read or write Brotli payloads.

### Payload compression

Fidelity and compression are independent options:

```python
token = encode_spectrum(spec, lossless=True, compression="zlib")
token = encode_spectrum(spec, compression="auto")
```

The default is zlib level 6. Other choices are `raw` and `brotli` at quality 5. Install `spectrl[brotli]` to enable Brotli in Python.
Explicit `auto` selects the shortest complete token among available backends,
with ties preferring zlib, raw, then Brotli. The token stores the
selected method. Explicitly requesting an unavailable backend raises an error.

The core array encodings are raw words (0), byte shuffle (1), modular delta plus
shuffle (2), and quantized words (3). Encoding 3 shares one unsigned integer
layout for linear and log1p quantization, with optional first-order delta.
Its parameters record `scale`, byte `width`, and optional `log` and `delta` flags.
For example, an explicit linear intensity grid can be requested with:

```python
token = encode_spectrum(spec, array_encodings={
    "intensity": {"encoding": [3, 1, {"scale": 100, "width": 4}]},
})
```

This rounds to increments of 0.01, with a checked absolute error bound of 0.005.
Choose a width that fits the indices. A tighter tolerance requires a larger
scale. The default intensity mapping instead uses log1p with scale 3600, whose
bound is `(x + 1) * expm1(0.5 / 3600)`. It is not a strict relative bound near
zero. The m/z default uses a logarithmic grid calibrated to a maximum error
of 0.1 ppm relative to each source value. Its scale is derived from the smallest
positive m/z, with a numerical margin and a check of the reconstructed values.
Zero remains exactly zero. For example, the allowed error is 0.00001 at m/z 100
and 0.0001 at m/z 1000.
All peaks remain present. See the specification for domains and fallback rules.

### User params (free-text metadata)

For values with no CV term, attach mzML `userParam`s at the spectrum or scan
level. They're omitted entirely when empty, so a spectrum without any is
byte-identical to one produced before the feature existed.

```python
from spectrl.model import InlineSpectrum, SpectrlUserParam

spec = InlineSpectrum(
    default_array_length=3, mz=mz, intensity=intensity,
    user_params=[
        SpectrlUserParam(name="Mascot score", value=42.7, type="xsd:float"),
        SpectrlUserParam(name="reanalysis note", value="rerun semitryptic"),
    ],
)
```

`from_mzmlpy` reads spectrum- and scan-level `userParam`s automatically. The JS
implementation exposes the same via `userParams`. Prefer a CV term whenever one
exists. UserParams are heavier (no accession to compress) and uncontrolled.

### Trim large spectra

```python
from spectrl import top_n

# Keep the 50 most intense peaks before encoding
trimmed = top_n(spec, 50)
token = encode_spectrum(trimmed)
```

### Quality, import, and sharing budgets

Use `encoding_report()` to measure error in the exact token it returns,
`fit_to_budget()` to propose explicit peak or user-param removal for a URL byte
budget, and `parse_peak_list()` / `format_peak_list()` for two-column text,
CSV, or TSV. The TypeScript package provides the same workflows as
`encodingReport`, `fitToBudget`, `parsePeakList`, and `formatPeakList`.

The browser demo supports importing your own peaks, downloading quality
reports, and previewing a budget candidate before applying it. The Python
`conversion_report()` API and `spectrl convert-mzml` command report observable
mzML omissions alongside the converted spectrum.

See [the workflow guide](docs/workflows.md) for runnable examples, JSON dtype
preservation, CLI commands, and the limits of each report.

### Lossless encoding

```python
# Default is lossy quantization
# Use lossless=True for bit-exact native arrays
token = encode_spectrum(spec, lossless=True)
```

## Token format

```
spectrl.v3.<mode>.<base64url(payload)>.<checksum>
```

- **`spectrl.v3`**: stable `spectrl` identifier + explicit `v3` format version. The prefix is the version's only carrier.
- **Mode**: `z` is the default zlib-compressed CBOR. `r` is raw CBOR and `b` is Brotli. All use unpadded base64url. Readers require `r` and `z`, with an optional `b` capability.
- The payload contains one **CBOR** document ([RFC 8949](https://www.rfc-editor.org/rfc/rfc8949)). Outer compression includes metadata and already encoded array blobs. Inspection expands this layer without decoding numeric arrays.
- The required trailing **checksum** is CRC-32/ISO-HDLC over everything before the last `.`, encoded as eight lowercase hexadecimal characters. It detects accidental corruption without decoding the CBOR payload.
- **Header**: a CBOR map with integer keys mirroring mzML structure: ms level, polarity, scan times, precursor isolation window, activation method, and collision energy.
- **Array blobs**: one per array type (m/z, intensity, charge, and accession-keyed additional arrays, including every ion-mobility variant), each encoded through a versioned numeric encoding and embedded inline in the CBOR document as a byte string.

## Validation

The shared conformance vectors test field-level Python/TypeScript
interoperability in both directions. The test suites also cover malformed and
adversarial inputs, canonicalization, URL bindings, mzML conversion, and all core numeric encodings.

```bash
# Python: lint, formatting check, and tests
just check

# TypeScript: install, typecheck, test, and build
cd js
npm ci
npm run typecheck
npm test
npm run build
```

Run `just release-check` from the repository root for the full Python,
TypeScript, distribution, and demo release gate.

## CLI

```bash
# Encode from JSON
echo '{"mz":[147.0,175.1],"intensity":[1e5,8e4]}' | spectrl encode

# Decode a token
echo "spectrl.v3.z.…" | spectrl decode

# Inspect the header as readable JSON
echo "spectrl.v3.z.…" | spectrl inspect
```

## Demo

A browser demo encodes example spectra live, shows the shareable URL + QR, and
decodes + plots them entirely client-side (no server). Use the
[hosted demo](https://pgarrett-scripps.github.io/spectrl/) or launch it locally:

```bash
just demo   # → http://127.0.0.1:8000
```

See [`demo/`](https://github.com/pgarrett-scripps/spectrl/tree/main/demo) for details.

## Design

- **mzML-aligned**: modeled metadata uses mzML `cvParam` semantics and existing
  ontology accessions. A token is not an arbitrary mzML `<spectrum>` XML
  round-trip: run-level references, processing provenance, source-file links,
  and unmodeled XML structure are outside its scope.
- **CV binding**: accession constants are generated into spectrl from its shared
  registry and validated against [mzmlpy](https://github.com/tacular-omics/mzmlpy)'s
  StrEnum enums during development. Core encoding and decoding do not import an
  mzML parser.
- **Deterministic (within an implementation)**: canonical form (m/z-ascending, deterministic quantization policies, RFC 8949 §4.2 CBOR) yields a stable token from a given implementation. A required CRC-32 checksum covers the received token text and is verified before decoding. Token bytes are not guaranteed identical across implementations (DEFLATE output is not canonical). See [SPECIFICATION.md](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md#8-canonical-form-and-checksum).
- **Scope**: represents measured spectra and acquisition context across mass spectrometry. Molecular identifications and fragment assignments are outside the format.

## Scope and security

- Services accepting public tokens should set per-call decoding budgets.
  The API provides `decode_token(token, limits=DecodeLimits(...))`
  and `decodeToken(token, limits)`. See [service integration](docs/services.md)
  for defaults, byte accounting, examples, and release availability.

- URL lengths vary by browser and receiving system. Encoding warns above 8 KiB.
  Use `top_n()` or a repository identifier for spectra that are too large.
- Lossy quantization is the default. Pass `lossless=True` when bit-exact arrays
  are required.
- The trailing checksum detects accidental corruption. It does not authenticate the
  sender or make untrusted content safe.
- spectrl preserves modeled spectrum-level metadata, not an entire mzML file or
  its run-level provenance. See the [specification](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) for the
  exact data model and decoder limits.

## Specification

The normative token format is specified in [SPECIFICATION.md](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md)
(an open specification governed in this repository). This README is a tutorial. The
specification is the contract. A machine-readable CV/codec/key registry lives in
[schema/registry.json](https://github.com/pgarrett-scripps/spectrl/blob/main/schema/registry.json).

`spectrl.v3` carries measured spectra and acquisition context. Its header
uses keys 0 through 11, with spectrum-level free-text parameters at key 7.
Molecular identifications belong in the surrounding application.

## Contributing

See [CONTRIBUTING.md](https://github.com/pgarrett-scripps/spectrl/blob/main/CONTRIBUTING.md) and the [Code of Conduct](https://github.com/pgarrett-scripps/spectrl/blob/main/CODE_OF_CONDUCT.md).
Changes to the on-the-wire token format are governed more strictly. See the
*Format changes* section of the contributing guide.

Bug reports and focused pull requests are welcome. Please report security
problems privately as described in [SECURITY.md](https://github.com/pgarrett-scripps/spectrl/blob/main/SECURITY.md).

## Citation

If spectrl supports published work, cite the archived software release rather
than the moving `main` branch. GitHub exposes the current metadata through
[`CITATION.cff`](https://github.com/pgarrett-scripps/spectrl/blob/main/CITATION.cff).

## License

Licensed under the [Apache License 2.0](https://github.com/pgarrett-scripps/spectrl/blob/main/LICENSE). If you use spectrl in
research, please cite it via [CITATION.cff](https://github.com/pgarrett-scripps/spectrl/blob/main/CITATION.cff). Third-party test-data
attribution is recorded in [NOTICE](https://github.com/pgarrett-scripps/spectrl/blob/main/NOTICE).

## Related

- [mzmlpy](https://github.com/tacular-omics/mzmlpy): the mzML parser this library bridges from

## V3 pipelines and selected-spectrum context

V3 separates numeric encoding from whole-document compression. No PSI codec term
is needed. Earlier token versions and superseded development layouts are not
supported. The trailing CRC32 protects the complete encoded token.

```python
from spectrl import ArrayEncoding, encode_spectrum

token = encode_spectrum(spectrum, lossless=True, array_encodings={
    "mz": ArrayEncoding(encoding="modular-delta-shuffle"),
    "intensity": "byte-shuffle",
})
```

float32, float64, and int32 inputs retain their declared representation when
encoded exactly. Quantization reconstructs float64 and records its error settings.

Use `from_mzmlpy(spectrum, run=mzml)` to include resolved source, instrument,
software, and processing context. Repeated CV terms and nested user parameters are
preserved. `conversion_report(..., run=mzml)` reports omissions. Trimming records
selection history and scopes acquisition-derived summaries to their source.

`register_encoding(id, Encoding(...), revision=1)` installs trusted local
callbacks. Numeric callbacks receive array/type/parameters for encoding and
bytes/type/count/parameters for decoding. Each implementation supplies a
parameter validator. Custom encoding registration is the only codec extension API.
See [the complete wire and callback contract](SPECIFICATION.md). Inspection can
read unknown operation descriptors without decoding the arrays. Full decoding
fails clearly when a required operation or extension is unavailable.

Python JSON interchange preserves native dtypes with `array_dtypes` and
`extra_array_dtypes`. Opaque byte strings use `{"$spectrl":"bytes","hex":"..."}`.
Maps with non-string keys or a literal `$spectrl` key use a tagged `map` with
an `items` list of key/value pairs, so extension data round-trips without ambiguity.
These tags belong to the JSON API, not the CBOR wire format.
