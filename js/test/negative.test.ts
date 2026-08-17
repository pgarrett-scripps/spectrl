/** Negative-value policy: mz rejected; intensity/charge/ion mobility fall back to lossless. */

import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeToken, encodeSpectrum, type InlineSpectrum } from "../src/index.ts";
import { encodeLinear, encodePic, encodeSlof } from "../src/numpress.js";

test("negative charge sentinels round-trip exactly in lossy mode", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [100.0, 200.0, 300.0],
    intensity: [1000.0, 5000.0, 2500.0],
    charge: [1, 2, -1], // -1 = unassigned/singleton sentinel
  };
  const d = decodeToken(encodeSpectrum(spec, { quiet: true })); // default: lossy
  assert.deepEqual(Array.from(d.charge!), [1, 2, -1]);
});

test("negative intensities round-trip exactly in lossy mode", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [100.0, 200.0, 300.0],
    intensity: [-0.5, 1e4, -3.0], // baseline-subtracted data
  };
  const d = decodeToken(encodeSpectrum(spec, { quiet: true }));
  assert.deepEqual(Array.from(d.intensity!), [-0.5, 1e4, -3.0]);
});

test("negative ion mobility round-trips exactly in lossy mode", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 2,
    mz: [100.0, 200.0],
    intensity: [1e3, 2e3],
    extraArrays: { "MS:1003007": [-0.001, 0.9] }, // raw ion mobility array
  };
  const d = decodeToken(encodeSpectrum(spec, { quiet: true }));
  assert.deepEqual(Array.from(d.extraArrays["MS:1003007"]!), [-0.001, 0.9]);
});

test("negative m/z is rejected", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 2,
    mz: [-1.0, 100.0],
    intensity: [1e3, 2e3],
  };
  assert.throws(() => encodeSpectrum(spec, { quiet: true }), /mz/);
  assert.throws(() => encodeSpectrum(spec, { quiet: true, lossless: true }), /mz/);
});

test("numpress codecs throw on negative input instead of corrupting", () => {
  assert.throws(() => encodePic(Float64Array.from([1, -1, 2])), /negative/);
  assert.throws(() => encodeSlof(Float64Array.from([5, -3])), /negative/);
  assert.throws(() => encodeLinear(Float64Array.from([-2, 100]), 100000.0), /negative/);
});
