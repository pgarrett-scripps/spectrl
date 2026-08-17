import assert from "node:assert/strict";
import { test } from "node:test";

import { ArrayAccession, decodeToken, encodeSpectrum, mobilityArrays, type InlineSpectrum } from "../src/index.ts";

function spec(extraArrays?: InlineSpectrum["extraArrays"]): InlineSpectrum {
  return {
    defaultArrayLength: 3,
    mz: [100, 200, 300],
    intensity: [1000, 2000, 3000],
    extraArrays,
  };
}

test("multiple mobility accessions survive independently", () => {
  const d = decodeToken(
    encodeSpectrum(
      spec({
        [ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY]: [0.8, 0.9, 1.0],
        [ArrayAccession.RAW_ION_MOBILITY_DRIFT_TIME]: [12.1, 13.4, 15.2],
      }),
      { quiet: true },
    ),
  );
  assert.deepEqual(Object.keys(d.extraArrays).sort(), ["MS:1003008", "MS:1003153"]);
  assert.deepEqual(Object.keys(mobilityArrays(d)).sort(), ["MS:1003008", "MS:1003153"]);
});

test("core accession aliases and friendly encoding keys are identical", () => {
  const byName = encodeSpectrum(spec(), { quiet: true, arrayEncodings: { mz: "zlib" } });
  const byAccession = encodeSpectrum(spec(), {
    quiet: true,
    arrayEncodings: { [ArrayAccession.MZ]: "zlib" },
  });
  assert.equal(byAccession, byName);
});

test("mobility enum selects its exact encoding override", () => {
  const d = decodeToken(
    encodeSpectrum(spec({ [ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY]: [0.8, 0.9, 1.0] }), {
      quiet: true,
      arrayEncodings: { [ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY]: "zlib" },
    }),
  );
  assert.deepEqual(Array.from(d.extraArrays["MS:1003008"]!), [0.8, 0.9, 1.0]);
});

test("conflicting core aliases are rejected", () => {
  assert.throws(
    () =>
      encodeSpectrum(spec(), {
        quiet: true,
        arrayEncodings: { mz: "zlib", "MS:1000514": "numlin-zlib" },
      }),
    /conflicting aliases/,
  );
});

test("core and non-MS accessions cannot masquerade as extra PSI-MS arrays", () => {
  assert.throws(() => encodeSpectrum(spec({ "MS:1000514": [1, 2, 3] }), { quiet: true }), /core array accession/);
  assert.throws(
    () => encodeSpectrum(spec({ [ArrayAccession.NON_STANDARD_DATA]: [1, 2, 3] }), { quiet: true }),
    /free-text/,
  );
  assert.throws(() => encodeSpectrum(spec({ "UO:0000031": [1, 2, 3] }), { quiet: true }), /PSI-MS/);
});

test("future PSI-MS array accessions remain forward-compatible", () => {
  const d = decodeToken(encodeSpectrum(spec({ "MS:1999999": new Float32Array([1, 2, 3]) }), { quiet: true }));
  assert.ok(d.extraArrays["MS:1999999"] instanceof Float32Array);
});
