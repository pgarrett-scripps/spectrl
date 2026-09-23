/** Free-text userParams at spectrum and scan level (omit-when-empty). */

import assert from "node:assert/strict";
import { test } from "node:test";

import { decodeToken, encodeSpectrum, type InlineSpectrum } from "../src/index.ts";

function base(extra: Partial<InlineSpectrum> = {}): InlineSpectrum {
  return { defaultArrayLength: 2, mz: [100, 200], intensity: [1e3, 2e3], ...extra };
}

test("empty userParams is byte-identical (omit-when-empty)", () => {
  assert.equal(encodeSpectrum(base(), { quiet: true }), encodeSpectrum(base({ userParams: [] }), { quiet: true }));
});

test("spectrum-level userParams round-trip", () => {
  const d = decodeToken(
    encodeSpectrum(
      base({
        userParams: [
          { name: "Mascot score", value: 42.7 },
          { name: "note", value: "rerun" },
          { name: "elapsed", value: 3.5, unitAccession: "UO:0000010" },
        ],
      }),
      { quiet: true },
    ),
  );
  assert.deepEqual(d.userParams.map((u) => u.name), ["Mascot score", "note", "elapsed"]);
  assert.equal(d.userParams[0]!.value, 42.7);
  assert.equal(d.userParams[2]!.unitAccession, "UO:0000010");
});

test("scan-level userParams round-trip", () => {
  const d = decodeToken(
    encodeSpectrum(
      base({
        scans: [
          {
            params: [{ accession: "MS:1000016", value: 10, unitAccession: "UO:0000031" }],
            userParams: [{ name: "[Thermo Trailer Extra]Mono M/Z", value: "445.12" }],
          },
        ],
      }),
      { quiet: true },
    ),
  );
  assert.equal(d.scans[0]!.userParams![0]!.name, "[Thermo Trailer Extra]Mono M/Z");
  assert.equal(d.scans[0]!.userParams![0]!.value, "445.12");
});

test("no userParams decodes to empty array", () => {
  assert.deepEqual(decodeToken(encodeSpectrum(base(), { quiet: true })).userParams, []);
});

const VENDOR: Partial<InlineSpectrum> = {
  userParams: [{ name: "filter string", value: "ITMS + c NSI" }],
  scans: [
    {
      params: [{ accession: "MS:1000016", value: 10.0, unitAccession: "UO:0000031" }],
      userParams: [{ name: "[Thermo]Mono M/Z", value: "445.12" }],
    },
  ],
};

test("dropUserParams records the omission", () => {
  const d = decodeToken(encodeSpectrum(base(VENDOR), { quiet: true, dropUserParams: true }))
  assert.equal(d.processing!.at(-1)!.operation, "spectrl:metadata-omission")
  assert.equal(d.processing!.at(-1)!.parameters!.userParamsRemoved, 2)
})

test("dropUserParams keeps CV params and peaks", () => {
  const d = decodeToken(encodeSpectrum(base(VENDOR), { quiet: true, dropUserParams: true }));
  assert.deepEqual(d.userParams, []);
  assert.deepEqual(d.scans[0]!.userParams ?? [], []);
  assert.equal(d.scans[0]!.params[0]!.accession, "MS:1000016");
  for (const [i, value] of [100, 200].entries()) assert.ok(Math.abs(d.mz![i]! - value) <= value * 1e-7)
});

test("dropUserParams is inert when there are none", () => {
  assert.equal(
    encodeSpectrum(base(), { quiet: true, dropUserParams: true }),
    encodeSpectrum(base(), { quiet: true }),
  );
});

test("dropUserParams does not mutate the input", () => {
  const spec = base(VENDOR);
  encodeSpectrum(spec, { quiet: true, dropUserParams: true });
  assert.equal(spec.userParams!.length, 1);
  assert.equal(spec.scans![0]!.userParams!.length, 1);
});

test("native parameter values preserve text versus numbers without type annotations", () => {
  for (const value of [null, "", "2.5", 2, 2.5, 1e20, Number.MAX_SAFE_INTEGER]) {
    const decoded = decodeToken(encodeSpectrum({ defaultArrayLength: 0, userParams: [{ name: "example", value }] }))
    assert.deepEqual(decoded.userParams, [{ name: "example", value, unitAccession: null }])
  }
})

test("removed type annotation is rejected even through the JavaScript API", () => {
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 0, userParams: [
    { name: "example", value: "2.5", type: "xsd:float" } as any,
  ] }), /type annotations are not supported/)
})
