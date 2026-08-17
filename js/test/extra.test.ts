/** Auxiliary (extra) per-peak arrays: named CV arrays + non-standard MS:1000786. */

import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeToken, encodeSpectrum, tokenBreakdown, type InlineSpectrum } from "../src/index.ts";
import { installZstd } from "../src/zstd.ts";

installZstd();

function spec(extraArrays: InlineSpectrum["extraArrays"]): InlineSpectrum {
  return {
    defaultArrayLength: 4,
    mz: [150, 300, 450, 600],
    intensity: [8e4, 5e4, 3e4, 1e4],
    extraArrays,
  };
}

for (const lossless of [false, true]) {
  test(`named + non-standard extra arrays round-trip (lossless=${lossless})`, () => {
    const d = decodeToken(
      encodeSpectrum(
        spec({
          "MS:1000517": new Float64Array([10, 20, 30, 40]),
          iso_score: new Float32Array([0.9, 0.8, 0.7, 0.6]),
          flags: new Int32Array([1, 0, 1, 0]),
        }),
        { lossless, quiet: true },
      ),
    );
    const e = d.extraArrays;
    assert.deepEqual(Object.keys(e).sort(), ["MS:1000517", "flags", "iso_score"]);
    assert.ok(e["MS:1000517"] instanceof Float64Array);
    for (let i = 0; i < 4; i++) {
      const expected = [10, 20, 30, 40][i]!;
      assert.ok(Math.abs(e["MS:1000517"]![i]! - expected) / expected < 5e-4);
    }
    assert.ok(e["iso_score"] instanceof Float32Array);
    for (let i = 0; i < 4; i++) assert.ok(Math.abs(e["iso_score"]![i]! - [0.9, 0.8, 0.7, 0.6][i]!) < 1e-6);
    assert.ok(e["flags"] instanceof Int32Array);
    assert.deepEqual(Array.from(e["flags"]!), [1, 0, 1, 0]);
  });
}

test("multiple non-standard arrays disambiguated by name", () => {
  const d = decodeToken(
    encodeSpectrum(spec({ score_a: new Float64Array([1, 2, 3, 4]), score_b: new Float64Array([5, 6, 7, 8]) }), { quiet: true }),
  );
  assert.deepEqual(Array.from(d.extraArrays["score_a"]!), [1, 2, 3, 4]);
  assert.deepEqual(Array.from(d.extraArrays["score_b"]!), [5, 6, 7, 8]);
});

for (const codec of ["zstd", "byte-shuffled-zstd"] as const) {
  test(`per-array ${codec} override round-trips`, () => {
    const expected = new Float64Array([1, 2, 3, 4]);
    const d = decodeToken(
      encodeSpectrum(spec({ custom: expected }), { quiet: true, arrayEncodings: { custom: codec } }),
    );
    assert.deepEqual(d.extraArrays.custom, expected);
  });
}

for (const codec of ["numlin-zstd", "numslof-zstd", "numpic-zstd"] as const) {
  test(`unknown auxiliary arrays reject ${codec}`, () => {
    assert.throws(() => encodeSpectrum(spec({ custom: [1, 2, 3, 4] }), {
      quiet: true, arrayEncodings: { custom: codec },
    }), /not compatible/);
  });
}

test("expert override allows lossy custom arrays but not known mismatches", () => {
  const source = spec({ custom: [1, 2, 3, 4] });
  assert.doesNotThrow(() => encodeSpectrum(source, {
    quiet: true,
    allowUnsafeLossyCustom: true,
    arrayEncodings: { custom: "numlin-zlib" },
  }));
  assert.throws(() => encodeSpectrum(source, {
    quiet: true,
    allowUnsafeLossyCustom: true,
    arrayEncodings: { mz: "numpic-zlib" },
  }), /not compatible/);
});

test("unknown auxiliary arrays stay lossless by default", () => {
  const expected = new Float64Array([0.123456789, 0.234567891, 0.345678912, 0.456789123]);
  const d = decodeToken(encodeSpectrum(spec({ custom: expected }), { quiet: true }));
  assert.deepEqual(d.extraArrays.custom, expected);
});

test("lossless mode rejects explicit lossy overrides", () => {
  assert.throws(
    () => encodeSpectrum(spec({ custom: new Float64Array([1, 2, 3, 4]) }), {
      quiet: true,
      lossless: true,
      arrayEncodings: { custom: "numlin-zstd" },
    }),
    /lossy codec/,
  );
});

test("fixedPoint requires a compatible codec and a whole number", () => {
  const source = spec({ "MS:1000517": new Float64Array([1, 2, 3, 4]) });
  assert.throws(
    () => encodeSpectrum(source, { quiet: true, arrayEncodings: { "MS:1000517": { codec: "zstd", fixedPoint: 1000 } } }),
    /takes no fixed point/,
  );
  assert.throws(
    () => encodeSpectrum(source, { quiet: true, arrayEncodings: { "MS:1000517": { codec: "numlin-zstd", fixedPoint: 1.5 } } }),
    /positive whole number/,
  );
});

test("extra arrays permuted by canonical m/z sort", () => {
  const d = decodeToken(
    encodeSpectrum(
      { defaultArrayLength: 3, mz: [300, 100, 200], intensity: [3, 1, 2], extraArrays: { snr: new Float64Array([30, 10, 20]) } },
      { quiet: true },
    ),
  );
  assert.deepEqual(Array.from(d.mz!), [100, 200, 300]);
  assert.deepEqual(Array.from(d.extraArrays["snr"]!), [10, 20, 30]);
});

test("no extra arrays decodes to empty object", () => {
  const d = decodeToken(encodeSpectrum({ defaultArrayLength: 2, mz: [1, 2], intensity: [3, 4] }, { quiet: true }));
  assert.deepEqual(d.extraArrays, {});
});

test("float extra array with NaN is rejected", () => {
  assert.throws(() => encodeSpectrum(spec({ snr: new Float64Array([1, NaN, 3, 4]) }), { quiet: true }), /NaN or Inf/);
});

test("cross-decode: a Python-style named-accession key survives", () => {
  // Encode with a CV accession key, confirm it decodes back to the same key.
  const d = decodeToken(encodeSpectrum(spec({ "MS:1000517": new Float64Array([5, 6, 7, 8]) }), { quiet: true }));
  assert.ok("MS:1000517" in d.extraArrays);
});

test("size breakdown gives the signal-to-noise array a readable label", () => {
  const token = encodeSpectrum(spec({ "MS:1000517": new Float64Array([5, 6, 7, 8]) }), { quiet: true });
  assert.ok(tokenBreakdown(token).some((part) => part.label === "signal-to-noise"));
});
