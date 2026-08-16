/** Encode-side validation and API edge cases (0.3.0 fixes). */

import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeToken, encodeSpectrum, toQuery, type InlineSpectrum } from "../src/index.ts";

function spec(overrides: Partial<InlineSpectrum> = {}): InlineSpectrum {
  return {
    defaultArrayLength: 3,
    mz: [100.0, 200.0, 300.0],
    intensity: [1e4, 2e4, 3e4],
    ...overrides,
  };
}

test("mismatched array lengths are rejected", () => {
  assert.throws(() => encodeSpectrum(spec({ intensity: [1e4, 2e4] }), { quiet: true }), /length/);
  assert.throws(() => encodeSpectrum(spec({ defaultArrayLength: 5 }), { quiet: true }), /length/);
  assert.throws(
    () => encodeSpectrum(spec({ extraArrays: { snr: new Float64Array([1, 2]) } }), { quiet: true }),
    /length/,
  );
});

for (const badLength of [-1, 1.5, 4_000_001]) {
  test(`invalid defaultArrayLength ${badLength} is rejected without arrays`, () => {
    assert.throws(() => encodeSpectrum({ defaultArrayLength: badLength }, { quiet: true }), /defaultArrayLength/);
  });
}

test("non-numeric accession tail round-trips as a string key", () => {
  const s = spec({ params: [{ accession: "NCIT:C25330", value: 7 }] });
  const d = decodeToken(encodeSpectrum(s, { quiet: true }));
  assert.equal(d.params[0]!.accession, "NCIT:C25330");
  assert.equal(d.params[0]!.value, 7);
});

test("non-seven-digit unit accession round-trips", () => {
  const s = spec({ params: [{ accession: "MS:1000045", value: 27.0, unitAccession: "MOD:00046" }] });
  const d = decodeToken(encodeSpectrum(s, { quiet: true }));
  assert.equal(d.params[0]!.unitAccession, "MOD:00046");
});

test("duplicate CV accessions are rejected", () => {
  assert.throws(
    () => encodeSpectrum(spec({ params: [{ accession: "MS:1000511", value: 1 }, { accession: "MS:1000511", value: 2 }] }), { quiet: true }),
    /duplicate CV accession/,
  );
});

test("toQuery preserves existing query params and replaces its own", () => {
  const token = encodeSpectrum(spec(), { quiet: true });
  const url = toQuery(token, "https://viewer.example.com/spectrum?keep=1&d=old");
  assert.ok(url.includes("keep=1"));
  assert.ok(!url.includes("d=old"));
  assert.ok(url.includes(`d=${token}`));
});
