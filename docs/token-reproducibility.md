# Token reproducibility

Python and JavaScript now agree on numeric metadata serialization: integral
values in the safe integer range use CBOR integers, other finite numbers use
the shortest exact float representation, and metadata negative zero becomes
integer zero. This applies recursively to operation parameters and extensions.
Numeric array bytes keep their declared types and exact bits in lossless mode.
Additional arrays use Unicode scalar-value ordering in both writers.

The comparison checks complete tokens, including framing and CRC, from the same
source model rather than decoding one language's output and re-encoding it.
Fifteen targeted metadata/array cases plus 54 seeded generated spectra produced
414 Python tokens across the two profiles and three fixed compression modes;
JavaScript and Rust each wrote all 414 byte-identically (rerun 2026-09-23 on the
3.0.0 code). The paper's 237-spectrum selection produced another 1,422 identical
Python/JavaScript tokens, rechecked by every paper asset build. Both runs had
zero differences; their runtime versions are recorded in
[`token-parity-results.json`](../experiments/v3/token-parity-results.json) and
[`token-parity-corpus-results.json`](../experiments/v3/token-parity-corpus-results.json).

The corpus inputs came from `encode_all()` in the companion spectrl-paper
repository's `paper/analysis/scripts/_datasets.py`, using this working library
through `PYTHONPATH`. Each source spectrum was serialized with `spectrum_to_dict`
as a `{name, spec}` entry. Run the same comparison with:

```sh
uv run --extra brotli python scripts/check_token_parity.py --inputs corpus-inputs.json
```

The checked-in raw tokens run in both language test suites. A separate CI job
compares live complete tokens on Linux, macOS, and Windows, covering Node 22/24
and Python 3.12–3.14. Those CI environments were configured here; the reported
measurements were run locally on Linux with Python 3.13 and Node 22.

The default lossy profile chooses each array's encoding by size. For `raw`
payloads the measure is the encoded array length, so the choice depends only on
the candidate bytes. For zlib and Brotli payloads, and `auto`, it is the length
of each array's bytes after zlib level 6, so writers on different zlib
implementations can choose different candidates for the same array. Python's
zlib and the JavaScript writer's pako produced the same lengths, and therefore
the same choices, on every input compared here. Encoding 4 uses integer
operations only, so its words are identical wherever it is chosen.

For a portable deterministic representation, use the existing lossless profile
and raw payload mode with identical metadata, array dtypes, and codec settings.
Compressed and lossy outputs matched in this study, but arbitrary compressor
versions and runtime logarithm implementations are not specified bit for bit.
Different settings, metadata, or dtypes can still produce different tokens for
scientifically equivalent spectra. No codec-independent fingerprint is added,
and the CRC is not a cryptographic hash.

Use the existing writer options for the portable lossless/raw representation:

```python
token = encode_spectrum(spec, lossless=True, compression="raw")
```

```typescript
const token = encodeSpectrum(spec, { lossless: true, compression: "raw" });
```

The input spectrum must carry the same metadata, numeric array types and values
in each language. Shared fixtures test exact token equality rather than only
successful decoding.
