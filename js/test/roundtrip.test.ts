/** Self-consistency: JS encode → JS decode, plus URL bindings. */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  decodeToken,
  encodeSpectrum,
  extractToken,
  toDataUri,
  toFragment,
  toQuery,
  type InlineSpectrum,
} from "../src/index.ts";

function makeSpec(): InlineSpectrum {
  return {
    defaultArrayLength: 5,
    mz: [110.071, 175.119, 288.203, 405.221, 600.33],
    intensity: [2.1e4, 9.9e4, 5.4e4, 1.2e4, 8.0e3],
    charge: [1, 1, 2, 1, 2],
    id: "scan=42",
    params: [
      { accession: "MS:1000511", value: 2 },
      { accession: "MS:1000130" },
      { accession: "MS:1000127" },
    ],
    precursors: [
      {
        isolationWindow: { params: [{ accession: "MS:1000827", value: 445.12 }] },
        selectedIons: [{ params: [{ accession: "MS:1000744", value: 445.12 }, { accession: "MS:1000041", value: 2 }] }],
        activation: { params: [{ accession: "MS:1000422" }, { accession: "MS:1000045", value: 27.0, unitAccession: "UO:0000266" }] },
      },
    ],
    interp: "ELVISK/2",
  };
}

test("lossy round-trip recovers peaks within numpress tolerance", () => {
  const spec = makeSpec();
  const token = encodeSpectrum(spec, { quiet: true });
  const d = decodeToken(token);

  assert.equal(d.defaultArrayLength, 5);
  assert.equal(d.id, "scan=42");
  assert.equal(d.interp, "ELVISK/2");
  for (let i = 0; i < 5; i++) {
    assert.ok(Math.abs(d.mz![i]! - spec.mz![i]!) < 1e-3, `mz[${i}]`);
    assert.ok(Math.abs(d.intensity![i]! - (spec.intensity as number[])[i]!) / (spec.intensity as number[])[i]! < 1e-2, `int[${i}]`);
    assert.equal(Math.round(d.charge![i]!), (spec.charge as number[])[i]);
  }
  // metadata (param maps are canonically key-sorted, so compare as sets)
  assert.equal(d.params.length, 3);
  assert.deepEqual(
    d.params.map((p) => p.accession).sort(),
    ["MS:1000127", "MS:1000130", "MS:1000511"],
  );
  assert.equal(d.precursors.length, 1);
  const ce = d.precursors[0]!.activation!.params.find((p) => p.accession === "MS:1000045")!;
  assert.equal(ce.unitAccession, "UO:0000266");
});

test("lossless round-trip is bit-exact", () => {
  const spec = makeSpec();
  const token = encodeSpectrum(spec, { lossless: true, quiet: true });
  const d = decodeToken(token);
  for (let i = 0; i < 5; i++) {
    assert.equal(d.mz![i], spec.mz![i]);
    assert.equal(d.intensity![i], (spec.intensity as number[])[i]);
    assert.equal(d.charge![i], (spec.charge as number[])[i]);
  }
});

test("canonical sort orders peaks by m/z ascending", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [300.0, 100.0, 200.0],
    intensity: [3, 1, 2],
  };
  const d = decodeToken(encodeSpectrum(spec, { lossless: true, quiet: true }));
  assert.deepEqual(Array.from(d.mz!), [100.0, 200.0, 300.0]);
  assert.deepEqual(Array.from(d.intensity!), [1, 2, 3]);
});

test("maxLen overflow throws", () => {
  const n = 2000;
  const mz = Array.from({ length: n }, (_, i) => 100 + i * 0.5);
  const intensity = Array.from({ length: n }, () => 1e4);
  assert.throws(() => encodeSpectrum({ defaultArrayLength: n, mz, intensity }, { maxLen: 100, quiet: true }), /maxLen/);
});

test("rejects NaN/Inf", () => {
  assert.throws(
    () => encodeSpectrum({ defaultArrayLength: 2, mz: [1, NaN], intensity: [1, 2] }, { quiet: true }),
    /NaN or Inf/,
  );
});

test("URL bindings round-trip", () => {
  const token = encodeSpectrum(makeSpec(), { quiet: true });
  assert.equal(extractToken(toFragment(token, "https://viewer.example.com/s")), token);
  assert.equal(extractToken(toQuery(token, "https://viewer.example.com/s")), token);
  assert.equal(extractToken(toDataUri(token)), token);
});

test("ion mobility array round-trips", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [300.1, 600.2, 900.3],
    intensity: [4e4, 3e4, 2e4],
    ionMobility: [0.82, 0.91, 1.05],
    ionMobilityType: "MS:1003008",
  };
  const d = decodeToken(encodeSpectrum(spec, { lossless: true, quiet: true }));
  assert.equal(d.ionMobilityType, "MS:1003008");
  assert.deepEqual(Array.from(d.ionMobility!), [0.82, 0.91, 1.05]);
});
