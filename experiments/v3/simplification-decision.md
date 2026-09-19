# V3 encoding decision

> Historical checkpoint. The final clean core is documented in
> [clean-core-decision.md](clean-core-decision.md).


The pinned selection contains 237 spectra. The working inputs were preserved
under `/tmp/spectrl-v3-simplification-start`. Exploratory results are in
`simplification-results.json` and `log-quantization-results.json`.

The measured complete-token totals support one outer compressor and a small
core of reversible word transforms plus one quantized-word representation.

| Policy | Complete text characters |
| --- | ---: |
| Previous adaptive lossless default | 6,815,155 |
| Same exact transforms, outer compression only | 6,849,691 |
| Fixed delta/shuffle m/z and shuffled intensity, outer zlib | 7,188,926 |
| Previous Numpress lossy default | 5,177,997 |
| Shared quantized-word representation at comparable default precision | 5,323,505 |
| Absolute quantization at the S9 middle budget | 3,078,258 |

These are design experiments, not the final publication benchmark. The first
study includes the existing per-array compression field even when disabled.
The logarithmic study omits that field. Final shipped descriptors and defaults
must be measured again. Brotli and Zstandard use one fixed preset each.

Choose the following design:

- Default to whole-document zlib, with explicit raw, Zstandard, Brotli, and auto.
- Omit per-array compression in ordinary output. Read old explicit compression
  fields and retain expert overrides as compatibility facilities.
- Use raw words, byte shuffle, and modular delta plus byte shuffle as the exact
  core. The fixed lossless default uses delta/shuffle for m/z, byte shuffle for
  intensity, and raw words for other arrays.
- Add one quantized-word encoding that shares the same byte shuffle and optional
  first-order delta. It supports a linear or log1p numeric mapping. Integer
  words have a declared width of 1, 2, 4, or 8 bytes.
- Use linear quantization for default m/z with scale 100000. Use log1p
  quantization for default nonnegative intensity with scale 3600. Wide integer
  words remove SLOF's 16-bit restriction. Unsupported domains fall back to exact
  representations. Preserve integer arrays exactly by default.
- Permit an explicit linear intensity quantizer for callers who accept an
  absolute error budget. Do not silently adopt the S9 base-peak tolerance as the
  default. The much smaller token comes with additional weak-peak rounding.
- Keep historical Numpress and dictionary identifiers unchanged and readable.
  Treat them as compatibility encodings rather than expanding the mandatory
  core or selecting them by default. PSI aliases remain advanced API adapters.
- Keep custom namespaced encodings for application extensions. Do not add XOR,
  bit shuffle, second-order prediction, varints, or mantissa rounding to the core.

The fixed exact policy costs about 5.5% in this corpus relative to the previous
adaptive default. The comparable-precision shared quantizer costs about 2.8%
relative to the previous lossy default. First-order delta was smaller than the
more elaborate predictors under the chosen shared quantizer. This is a modest
size cost for predictable defaults and substantially fewer mandatory methods.

The current 16 MiB expanded-CBOR ceiling remains sufficient for this selection.
The largest measured transformed document was 1,736,614 bytes. Larger inputs
still require explicit size-limit errors. This corpus does not establish
universal rankings or suitable scientific tolerances.

The word-level predictor and shuffle implementations are shared between exact
and quantized encodings. Keeping quantization parameters within one versioned
encoding avoids a general pipeline language with arbitrary stage combinations.

Final acceptance requires Python and TypeScript agreement, bounded decoding,
full-corpus fidelity checks, and regenerated paper results. Development tokens
remain readable through the compatibility fields without reassigning IDs.

## Final shipped profiles

Fresh measurements of the shipped defaults supersede the provisional size
tradeoff above. Across the same 237 selected spectra, final zlib tokens total
5,119,808 characters in lossy mode and 7,187,545 in lossless mode. Compared with
the preserved previous defaults, that is 1.12% smaller for lossy and 5.46% larger
for lossless. The finalized descriptors, word widths, checked fallback, and
unclipped log scale differ from the exploratory logarithmic candidate.

Brotli quality 5 reduces these final totals by 4.31% and 4.02%, respectively,
relative to zlib level 6. Zstandard level 3 is larger in both profiles. These
are corpus results, not a general ranking. Retain zlib as the portable default.
The quantizer can express more aggressive absolute intensity rounding without
adding another encoding, but that choice needs an explicit caller tolerance.

The transport/profile matrix passed 2,370 exchanges in each language direction.
`final-profile-results.json` records the totals and source report hash.
`summarize_final_profiles.py` derives that comparison from the paper's final
`payload-v3.json` report and the preserved exploratory results.

`baseline-source.tar.gz` preserves the pre-change Python implementation and
analysis source. `baseline-hashes.json` identifies the complete pre-change
working files. Earlier exploratory scripts require that baseline and its pinned
corpus, or the trusted local corpus cache. Running them against final defaults
would answer a different question. The paper's generators always use the final
synchronized implementation.
