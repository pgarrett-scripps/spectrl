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
spectrl.v1.<base64url(CBOR document)>.<checksum>
```

[Try the browser demo](https://pgarrett-scripps.github.io/spectrl/) ·
[Read the format specification](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) ·
[See the changelog](https://github.com/pgarrett-scripps/spectrl/blob/main/CHANGELOG.md)

[![A spectrl token embedded in a URL and decoded into a mass spectrum, with summary cards for token size, carriers, implementations, and client-side decoding.](https://raw.githubusercontent.com/pgarrett-scripps/spectrl/main/docs/spectrl-overview.png)](https://pgarrett-scripps.github.io/spectrl/)

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
| [`SPECIFICATION.md`](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md) | Normative `spectrl.v1` wire-format specification |
| [`test-vectors/`](https://github.com/pgarrett-scripps/spectrl/tree/main/test-vectors) | Shared positive, negative, and cross-language conformance vectors |

## Install

```bash
pip install spectrl
```

Requires Python 3.12+. Pure Python out of the box: the MS-Numpress codecs ship
with a dependency-free backend (this is what lets spectrl run in Pyodide / the
browser). For the C-extension backend (byte-identical, faster on large arrays):

```bash
pip install "spectrl[speed]"
```

To install the unreleased development version:

```bash
pip install "spectrl @ git+https://github.com/pgarrett-scripps/spectrl.git"
```

The TypeScript implementation is tested and built from [`js/`](https://github.com/pgarrett-scripps/spectrl/tree/main/js), but is
not yet published to npm because the final package scope has not been claimed.

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
# spectrl.v1.hQ...
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
# https://viewer.example.com/spectrum#spectrl.v1.hQ...

# Or as a query parameter
url = to_query(token, "https://viewer.example.com/spectrum")
# https://viewer.example.com/spectrum?d=spectrl.v1.hQ...

# Or as a data URI
uri = to_data_uri(token)
# data:application/vnd.spectrl;v=1,spectrl.v1.hQ...

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

Known PSI-MS auxiliary arrays receive semantic defaults. Coordinate arrays use
Numpress linear, positive magnitude arrays such as signal-to-noise use Numpress
slof, and integer index arrays use Numpress pic. Unknown and non-standard arrays
remain lossless raw + zlib. The JavaScript implementation exposes the same via
`extraArrays` and preserves `Int32Array` and `Float32Array` types for raw codecs.

Override any array independently when needed:

```python
token = encode_spectrum(
    spec,
    array_encodings={
        ArrayAccession.MZ: "numlin-zstd",  # "mz" is an equivalent alias
        ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY: "numlin-zstd",
        "MS:1000517": {"codec": "numslof-zstd", "fixed_point": 3600},
        "iso_score": "byte-shuffled-zstd",
    },
)
```

Supported names are `zlib`, `zstd`, `byte-shuffled-zstd`, and each Numpress
transform followed by either zlib or zstd. Passing `lossless=True` keeps every
array exact and rejects an explicitly lossy override.

Unknown arrays remain lossless unless an expert explicitly passes
`allow_unsafe_lossy_custom=True` together with a lossy codec override. Known
incompatible array/codec combinations are rejected even with that option.

In JavaScript, call `installZstd()` from `@spectrl-ms/spectrl/zstd` before encoding
or decoding zstd arrays. The explicit setup cannot be removed by tree-shaking.

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

### Lossless encoding

```python
# Default is lossy MS-Numpress
# Use lossless=True for bit-exact IEEE-754 doubles
token = encode_spectrum(spec, lossless=True)
```

## Token format

```
spectrl.v1.<base64url(CBOR document)>.<checksum>
```

- **`spectrl.v1`**: stable `spectrl` identifier + explicit `v1` format version. The prefix is the version's only carrier.
- The payload is a single **CBOR** document ([RFC 8949](https://www.rfc-editor.org/rfc/rfc8949)), base64url-encoded without padding (RFC 4648 §5).
- The required trailing **checksum** is CRC-32/ISO-HDLC over everything before the last `.`, encoded as eight lowercase hexadecimal characters. It detects accidental corruption without decoding the CBOR payload.
- **Header**: a CBOR map with integer keys mirroring mzML structure: ms level, polarity, scan times, precursor isolation window, activation method, collision energy, and ProForma interpretation.
- **Array blobs**: one per array type (m/z, intensity, charge, and accession-keyed additional arrays, including every ion-mobility variant), each encoded through an official PSI-MS Numpress, zlib, or zstd pipeline and embedded inline in the CBOR document as a byte string.

## Validation

The shared conformance vectors test field-level Python/TypeScript
interoperability in both directions. The test suites also cover malformed and
adversarial inputs, canonicalization, URL bindings, mzML conversion, and both
Numpress backends.

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
echo "spectrl.v1.hQ..." | spectrl decode

# Inspect the header as readable JSON
echo "spectrl.v1.hQ..." | spectrl inspect
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
- **Deterministic (within an implementation)**: canonical form (m/z-ascending, fixed numpress scale factors, RFC 8949 §4.2 CBOR) yields a stable token from a given implementation. A required CRC-32 checksum covers the received token text and is verified before decoding. Token bytes are not guaranteed identical across implementations (DEFLATE output is not canonical). See [SPECIFICATION.md](https://github.com/pgarrett-scripps/spectrl/blob/main/SPECIFICATION.md#8-canonical-form-and-checksum).
- **ProForma**: carries an optional ProForma 2.0 peptide interpretation string (key 7).

## Scope and security

- URL lengths vary by browser and receiving system. Encoding warns above 8 KiB.
  Use `top_n()` or a repository identifier for spectra that are too large.
- Lossy MS-Numpress is the default. Pass `lossless=True` when bit-exact arrays
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

`spectrl.v1` is the frozen format described here. It intentionally uses a new
magic because its wire layout is not compatible with the development
`spectrl1` tokens emitted by earlier package releases.

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
The archived v1.0.0 release is available at
[doi:10.5281/zenodo.21986776](https://doi.org/10.5281/zenodo.21986776).

## License

Licensed under the [Apache License 2.0](https://github.com/pgarrett-scripps/spectrl/blob/main/LICENSE). If you use spectrl in
research, please cite it via [CITATION.cff](https://github.com/pgarrett-scripps/spectrl/blob/main/CITATION.cff). Third-party test-data
attribution is recorded in [NOTICE](https://github.com/pgarrett-scripps/spectrl/blob/main/NOTICE).

## Related

- [mzmlpy](https://github.com/tacular-omics/mzmlpy): the mzML parser this library bridges from
- [ProForma 2.0](https://www.psidev.info/proforma): peptidoform notation carried in the token
