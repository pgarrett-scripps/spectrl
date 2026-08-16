/** Auxiliary (extra) per-peak arrays: named CV arrays + non-standard MS:1000786. */

import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeToken, encodeSpectrum, type InlineSpectrum } from "../src/index.ts";

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
    assert.deepEqual(Array.from(e["MS:1000517"]!), [10, 20, 30, 40]);
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
