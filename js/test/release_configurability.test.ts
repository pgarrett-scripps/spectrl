import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ArrayAccession,
  CompressionAccession,
  UnitAccession,
  decodeToken,
  encodeSpectrum,
  encodingPlan,
  type InlineSpectrum,
} from "../src/index.ts";
import { installZstd } from "../src/zstd.ts";

installZstd();

test("array units survive and appear in the resolved plan", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 2,
    mz: [100, 200],
    intensity: [1, 2],
    extraArrays: { [ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME]: [12.1, 13.4] },
    arrayUnits: { [ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME]: UnitAccession.MILLISECOND },
  };
  const decoded = decodeToken(encodeSpectrum(spec, { quiet: true }));
  assert.equal(decoded.arrayUnits[ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME], UnitAccession.MILLISECOND);
  assert.equal(encodingPlan(spec)[2]?.unitAccession, UnitAccession.MILLISECOND);
});

test("full compression accessions work and incompatible codecs fail", () => {
  const spec: InlineSpectrum = { defaultArrayLength: 2, mz: [100.1, 200.2], intensity: [1, 2] };
  assert.doesNotThrow(() => encodeSpectrum(spec, {
    quiet: true, arrayEncodings: { mz: CompressionAccession.NUMPRESS_LINEAR_ZSTD },
  }));
  assert.throws(() => encodeSpectrum(spec, {
    quiet: true, arrayEncodings: { mz: CompressionAccession.NUMPRESS_PIC_ZLIB },
  }), /not compatible/);
});

test("reserved custom names fail", () => {
  assert.throws(() => encodeSpectrum({
    defaultArrayLength: 1, mz: [1], intensity: [2], extraArrays: { mz: [3] },
  }, { quiet: true }), /reserved/);
});
