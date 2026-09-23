# spectrl (Rust)

An independent Rust implementation of the `spectrl.v3` token format: one mass
spectrum's peak arrays and modeled mzML metadata in a URL-safe string,

```text
spectrl.v3.<mode>.<base64url(CBOR payload)>.<crc32>
```

that decodes with no lookup service. It was written from
[`SPECIFICATION.md`](../SPECIFICATION.md), [`schema/registry.json`](../schema/registry.json)
and the shared [`test-vectors/`](../test-vectors) only, without reading the Python
or TypeScript sources, and writes the same tokens as both byte for byte.
Ambiguities met on the way are recorded in [`SPEC-NOTES.md`](SPEC-NOTES.md).

## Install

```bash
cargo add spectrl         # library
cargo install spectrl     # CLI
```

Rust 1.85 or newer and a C compiler. The crate itself is `#![forbid(unsafe_code)]`.
zlib and Brotli are the bundled reference C libraries (`libz-sys`, `brotlic`), so
`z` and `b` payloads match the Python and Node writers exactly. CBOR, base64url,
the codecs and fdlibm `log1p`/`expm1` are implemented in the crate.

Features: `brotli` (default) adds `b` payloads. Without it, `b` tokens fail with
an `Unsupported` error, as the specification allows.

## Library

```rust
use spectrl::{Array, Compression, EncodeOptions, Spectrum, decode_token, encode_spectrum};

fn main() -> Result<(), spectrl::Error> {
    let mut s = Spectrum::new(3);
    s.mz = Some(Array::F64(vec![100.0, 200.5, 300.25]));
    s.intensity = Some(Array::F32(vec![10.0, 20.0, 5.0]));

    // Default profile: size-chosen encodings within the stated bounds, zlib payload.
    let token = encode_spectrum(&s, EncodeOptions::default())?;
    println!("{token}");

    // Lossless profile with a raw payload: the reproducible representation.
    let exact = encode_spectrum(&s, EncodeOptions { lossless: true, compression: Compression::Raw })?;

    let back = decode_token(&exact)?;
    assert_eq!(back.spectrum.mz, s.mz);
    Ok(())
}
```

- `decode_token` applies the default reader budgets (4 MiB token, 1,000,000 peaks,
  64 arrays, 64 MiB of reconstructed arrays). `decode_token_with(token,
  &Budgets::ceilings())` raises them to the hard limits for a trusted producer.
- `inspect_token` validates a token and lists its arrays without decoding values;
  unknown encodings and required extensions are reported, not rejected.
- Every rejection is an `Error` with a `kind()` of `Decode`, `Encode` or
  `Unsupported`. Malformed input never panics.

## CLI

```bash
spectrl encode --lossless --compression raw spectrum.json   # prints a token
spectrl decode TOKEN                                        # prints JSON
spectrl inspect TOKEN                                       # descriptors as JSON
spectrl batch < requests.jsonl                              # parity harness mode
```

The JSON shape is the one the shared vectors use (`spectrum_to_dict` in
Python). It is a harness format, not part of the token format.

## Tests

```bash
cargo test            # vectors, fdlibm against StrictMath, property tests
cargo test --no-default-features
```

`tests/vectors.rs` reads `../test-vectors`, so run it from a repository checkout.
The cross-implementation checks live in `../scripts`:

```bash
uv run --extra brotli python scripts/check_token_parity.py
uv run python scripts/check_adversarial_parity.py
```

Both build this crate in release mode and skip Rust with a message when cargo is
not installed.

## License

Apache-2.0.
