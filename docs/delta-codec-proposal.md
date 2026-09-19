# Proposed lossless modular-delta, byte-shuffle, and zlib codec

Historical design record. The current defaults and supported core are defined in
[SPECIFICATION.md](../SPECIFICATION.md) and the
[final encoding decision](../experiments/v3/clean-core-decision.md).

Status: draft byte-level contract with Python and JavaScript reference implementations. No PSI-MS accession is assigned or claimed. This codec is deliberately absent from the spectrl.v2 registry and public encoding options. No vocabulary proposal has been submitted.

A [local PSI-MS submission draft](psi-ms-submission/PR.md) includes the proposed
upstream patch and validation notes. It has not been posted and requires
explicit user approval before any GitHub publication.

## Existing use outside PSI-MS

This proposal makes no claim of algorithmic novelty. The `zap` serialization
project documents a float64 `delta_shuffle` transform that reinterprets doubles
as unsigned 64-bit integers, differences consecutive words, and shuffles their
bytes before compression. This is the same core transform used here for float64.
The reference establishes existing use of the method, not compatibility between
zap files and the zlib array streams specified below.
[zap floating-point transform](https://github.com/coolbutuseless/zap#floating-point-delta_shuffle-delta-and-byte-shuffle)

The contribution proposed here is a precise mass-spectrometry codec definition,
cross-language conformance vectors, and evaluation on spectral arrays. Absence
of a matching PSI-MS term does not establish novelty or explain why the method
has not been registered.

## Relationship to existing PSI-MS codecs

Numpress linear is already predictive coding. It quantizes numbers onto a fixed-point integer grid, predicts the next integer from the previous two, and packs the residual. This is closely related to second differences. Quantization prevents a general guarantee of bit-exact float64 reconstruction. [Numpress reference](https://github.com/ms-numpress/ms-numpress)

PSI-MS `MS:1003089` describes the mzMLb truncation and delta pipeline, while `MS:1003090` describes its linear predictor. These are related existing methods, but the reference delta algorithm operates on floating-point values with an offset and feedback. It does not subtract unsigned representations of the IEEE-754 words. Byte layout and decoder behavior are therefore different from this proposal. [PSI-MS vocabulary](https://raw.githubusercontent.com/HUPO-PSI/psi-ms-CV/master/psi-ms.obo), [mzMLb encoder and decoder](https://github.com/biospi/pwiz/blob/mzMLb/pwiz/data/msdata/IO.cpp#L1804-L1816)

Disabling mantissa truncation does not make that floating predictor universally bit-exact. Reproducing its encode and decode equations on `[100.0, 100.1, 100.2]` changes the last value from float64 bits `40590ccccccccccd` to `40590ccccccccccc`, a one-ULP difference of approximately `1.4210854715202004e-14`. The regression test records this counterexample. Pyteomics independently implements the corresponding floating-point inverse. [Pyteomics mzMLb decoder](https://pyteomics.readthedocs.io/en/latest/_modules/pyteomics/mzmlb.html#delta_predict)

An existing compression accession specifies how consumers decode the data. The proposed bytes MUST NOT be labeled `MS:1003089`, Numpress, raw zlib, or byte-shuffled zstd. Similarity of the predictor concept is insufficient for wire compatibility.

## Proposed vocabulary request

Suggested name: **lossless modular delta and byte-shuffled zlib compression**.

Suggested definition: Data array compression by modular differences of consecutive unsigned words representing the declared numeric type, followed by byte shuffling and one zlib stream. The first word is stored unchanged. The transform preserves all original bits and performs no numeric quantization or mantissa truncation.

Proposed parent: `MS:1000572`, binary data compression type.

The eventual request should link this byte contract, the independent implementations, conformance vectors, and [corpus measurements](../experiments/encoding/FINDINGS.md). The accession remains pending PSI-MS review. A parallel Zstandard variant could be considered separately because the final compressor is part of the decoder contract.

The expanded [PSI mode comparison](../experiments/encoding/PSI_SWEEP.md) includes
dictionary-encoded Zstandard and separates m/z, intensity, and mobility results.
It also distinguishes generally lossless codecs from normally lossy candidates
that happen to pass an exact-byte check for a particular array.

## Normative transform

Let `w` be the declared numeric word width in bytes, either 4 or 8, and let `n` be the number of elements. Float32 and int32 use 4 bytes. Float64 uses 8 bytes. The input is exactly `n * w` bytes in little-endian numeric representation.

1. Interpret each word as an unsigned little-endian integer `u[i]`. This is a reinterpretation of its bits, never a floating-point conversion or a cast of its numeric value to an integer.
2. Set `d[0] = u[0]` when `n > 0`.
3. For `i > 0`, set `d[i] = (u[i] - u[i-1]) mod 2^(8*w)`.
4. Encode each `d[i]` as `w` little-endian bytes. Transpose the resulting `n` by `w` byte matrix. The output location is `shuffled[b*n + i] = delta_bytes[i*w + b]`, with byte planes ordered from least significant to most significant.
5. Compress all shuffled bytes as one RFC 1950 zlib stream with DEFLATE and the Adler-32 checksum. The reference encoder uses level 6. A conforming encoder MAY use another zlib level because the compressed stream identifies its own coding. It MUST NOT use a gzip wrapper, raw DEFLATE, a preset dictionary, concatenated streams, or additional bytes after the stream.

The empty input produces a zlib stream for an empty byte sequence. A singleton retains its word bits, with shuffling reducing to identity. Each independently encoded array resets prediction at its first word. Arrays need not be sorted, and there is no cross-array state.

For example, 32-bit words `[1, 3, 2]` become differences `[1, 2, 4294967295]`. The shuffled bytes before zlib are:

```text
01 02 ff  00 00 ff  00 00 ff  00 00 ff
```

## Normative inverse and limits

1. Validate the numeric type, declared length, and application budgets before decompressing. Compute `n * w` with checked arithmetic.
2. Inflate one complete zlib stream with an output bound of `n * w`. Reject over-budget output, a truncated stream, a checksum failure, dictionary requests, additional streams, or trailing bytes.
3. Require exactly `n * w` output bytes. Undo the transpose to reconstruct the little-endian difference words.
4. Reconstruct `u[0] = d[0]`, then `u[i] = (u[i-1] + d[i]) mod 2^(8*w)`.
5. Reinterpret the recovered bytes as the declared numeric type. Never convert a 64-bit word through a JavaScript `Number`.

The reference compression helpers accept a byte budget and check whole-word alignment. A future token adapter must additionally enforce the exact declared element count, as the existing spectrl decoder does for other codecs.

The byte transform preserves signed zeros, subnormals, infinities, and NaN payloads. This property does not change spectrl's input-domain restrictions. Tokens must still obey the format's numeric validation rules.

## Reference implementations and conformance

- Python: [private reference module](../src/spectrl/codecs/_delta.py). Uses unsigned NumPy word operations with explicit widths and little-endian serialization.
- JavaScript: [internal reference module](../js/src/delta.ts). Uses bytewise borrow and carry, preserving all 64 bits without `Number` integer conversion.
- [Forward vectors](../test-vectors/delta-proposal.json) have independently computed transformed bytes and Python zlib streams. JavaScript decodes these streams.
- [Reverse vectors](../test-vectors/delta-proposal-reverse.json) contain JavaScript zlib streams. Python decodes them.

Vectors cover empty and singleton inputs, unsigned wraparound, signed integer extremes, signed zero, subnormal values, infinities, NaN payloads, and an m/z example. Additional tests cover random bit patterns, nonzero buffer offsets, malformed streams, and decompression budgets. Python and JavaScript must agree on the transformed bytes. They need not emit identical valid zlib streams.

Regenerate and verify from the repository root:

```bash
.venv/bin/python scripts/gen_delta_vectors.py
cd js
node --import tsx scripts/gen_delta_reverse_vectors.ts
node --import tsx --test test/delta_proposal.test.ts
cd ..
.venv/bin/pytest tests/test_delta_proposal.py
```

## Integration path

The implemented adaptive lossless default uses the three existing registered codecs. It does not emit this proposal's bytes.

After an appropriate PSI-MS term and byte contract are agreed, add the assigned accession to the registry generator, codec dispatch in both languages, the public per-array encoding names, introspection, the specification, and shared token vectors. Existing consumers that do not implement the new codec must reject its unknown accession. No hidden descriptor flag or reused compression identifier should cause an older consumer to decode the transformed bytes as ordinary floats.

Evaluate the new codec as an explicit override first. Its inclusion in adaptive defaults should follow browser measurements and corpus validation, with particular attention to intensity and mobility arrays. Compression gains are strongest on m/z arrays and vary by array semantics.
