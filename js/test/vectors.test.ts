/**
 * Conformance: decode the Python-generated shared vectors and verify the
 * recovered spectrum matches. This is the cross-implementation contract.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { test } from "node:test";

import { b64urlEncode } from "../src/base64url.ts";
import { tokenChecksum } from "../src/checksum.ts";
import { decodeToken } from "../src/index.ts";
import { installZstd } from "../src/zstd.ts";

installZstd();

const here = dirname(fileURLToPath(import.meta.url));
const vectorsPath = resolve(here, "../../test-vectors/vectors.json");
const doc = JSON.parse(readFileSync(vectorsPath, "utf-8"));
const negativeDoc = JSON.parse(readFileSync(resolve(here, "../../test-vectors/negative-vectors.json"), "utf-8"));

interface Tol {
  abs: number;
  rel: number;
}

function closeArray(actual: Float64Array | null, expected: number[] | null, tol: Tol, label: string): void {
  if (expected === null) {
    assert.equal(actual, null, `${label}: expected null`);
    return;
  }
  assert.ok(actual !== null, `${label}: expected array, got null`);
  assert.equal(actual!.length, expected.length, `${label}: length`);
  for (let i = 0; i < expected.length; i++) {
    const a = actual![i]!;
    const e = expected[i]!;
    const bound = tol.abs + tol.rel * Math.abs(e);
    assert.ok(Math.abs(a - e) <= bound, `${label}[${i}]: |${a} - ${e}| > ${bound}`);
  }
}

function closeNum(a: unknown, e: unknown, label: string): void {
  if (typeof e === "number" && typeof a === "number") {
    assert.ok(Math.abs(a - e) <= 1e-9 + 1e-9 * Math.abs(e), `${label}: ${a} != ${e}`);
  } else {
    assert.deepEqual(a, e, label);
  }
}

function cmpParams(actual: any[], expected: any[], label: string): void {
  assert.equal(actual.length, expected.length, `${label}: param count`);
  for (let i = 0; i < expected.length; i++) {
    assert.equal(actual[i].accession, expected[i].accession, `${label}[${i}].accession`);
    const av = actual[i].value ?? null;
    const ev = expected[i].value ?? null;
    closeNum(av, ev, `${label}[${i}].value`);
    const au = actual[i].unitAccession ?? null;
    const eu = expected[i].unit_accession ?? null;
    assert.equal(au, eu, `${label}[${i}].unit`);
  }
}

function cmpUserParams(actual: any[], expected: any[], label: string): void {
  assert.equal(actual.length, expected.length, `${label}: user-param count`);
  for (let i = 0; i < expected.length; i++) {
    assert.equal(actual[i].name, expected[i].name, `${label}[${i}].name`);
    assert.deepEqual(actual[i].value ?? null, expected[i].value ?? null, `${label}[${i}].value`);
    assert.equal(actual[i].type ?? null, expected[i].type ?? null, `${label}[${i}].type`);
    assert.equal(actual[i].unitAccession ?? null, expected[i].unit_accession ?? null, `${label}[${i}].unit`);
  }
}

for (const v of doc.vectors) {
  test(`vector: ${v.name} (${v.mode})`, () => {
    const tol: Tol = v.tolerance;
    const d = decodeToken(v.token); // throws on checksum mismatch
    const exp = v.decoded;

    assert.equal(d.defaultArrayLength, exp.default_array_length, "defaultArrayLength");
    assert.equal(d.id, exp.id, "id");
    assert.equal(d.interp, exp.interp, "interp");
    assert.equal(d.formatVersion, exp.format_version, "formatVersion");
    assert.equal(d.checksum, exp.checksum, "checksum");

    closeArray(d.mz, exp.mz, tol, "mz");
    closeArray(d.intensity, exp.intensity, tol, "intensity");
    closeArray(d.charge, exp.charge, tol, "charge");

    cmpParams(d.params, exp.params, "params");

    assert.equal(d.scans.length, exp.scans.length, "scan count");
    for (let i = 0; i < exp.scans.length; i++) {
      cmpParams(d.scans[i]!.params, exp.scans[i].params, `scan[${i}].params`);
      const ew = exp.scans[i].windows ?? [];
      const aw = d.scans[i]!.windows ?? [];
      assert.equal(aw.length, ew.length, `scan[${i}] window count`);
      for (let j = 0; j < ew.length; j++) cmpParams(aw[j]!.params, ew[j].params, `scan[${i}].window[${j}]`);
      cmpUserParams(d.scans[i]!.userParams ?? [], exp.scans[i].user_params ?? [], `scan[${i}].userParams`);
    }

    assert.equal(d.precursors.length, exp.precursors.length, "precursor count");
    for (let i = 0; i < exp.precursors.length; i++) {
      const ap = d.precursors[i]!;
      const ep = exp.precursors[i];
      if (ep.isolation_window) cmpParams(ap.isolationWindow!.params, ep.isolation_window.params, `precursor[${i}].isoWin`);
      assert.equal((ap.selectedIons ?? []).length, (ep.selected_ions ?? []).length, `precursor[${i}] selIon count`);
      for (let j = 0; j < (ep.selected_ions ?? []).length; j++) {
        cmpParams(ap.selectedIons![j]!.params, ep.selected_ions[j].params, `precursor[${i}].selIon[${j}]`);
      }
      if (ep.activation) cmpParams(ap.activation!.params, ep.activation.params, `precursor[${i}].activation`);
    }

    assert.equal(d.products.length, exp.products.length, "product count");
    for (let i = 0; i < exp.products.length; i++) {
      if (exp.products[i].isolation_window) {
        cmpParams(d.products[i]!.isolationWindow!.params, exp.products[i].isolation_window.params, `product[${i}].isoWin`);
      }
    }

    cmpUserParams(d.userParams, exp.user_params ?? [], "userParams");

    const expExtra = exp.extra_arrays ?? {};
    const dtypeCtor: Record<string, string> = { float64: "Float64Array", float32: "Float32Array", int32: "Int32Array" };
    assert.deepEqual(Object.keys(d.extraArrays).sort(), Object.keys(expExtra).sort(), "extraArrays keys");
    for (const k of Object.keys(expExtra)) {
      const ea = d.extraArrays[k]!;
      const ee = expExtra[k];
      assert.equal(ea.constructor.name, dtypeCtor[ee.dtype], `extra[${k}] dtype`);
      closeArray(ea as unknown as Float64Array, ee.values, tol, `extra[${k}]`);
    }
    assert.deepEqual(d.arrayUnits, exp.array_units ?? {}, "arrayUnits");
  });
}

test("tampered token fails checksum verification", () => {
  const t: string = doc.vectors[0].token;
  // perturb the tail of the CBOR payload; the stored checksum no longer matches
  const parts = t.split(".");
  const payload = parts[2]!;
  parts[2] = payload.slice(0, -3) + (payload.slice(-3) === "AAA" ? "BBB" : "AAA");
  const bad = parts.join(".");
  assert.throws(() => decodeToken(bad), /checksum mismatch/);
});

test("bad magic is rejected", () => {
  assert.throws(() => decodeToken("spectrl9.aaaa"), /spectrl.v1|magic|version/i);
});

for (const v of negativeDoc.vectors) {
  test(`negative vector: ${v.name}`, () => {
    const body = `spectrl.v1.${b64urlEncode(Uint8Array.from(Buffer.from(v.cbor_hex, "hex")))}`;
    const token = `${body}.${tokenChecksum(body)}`;
    assert.throws(() => decodeToken(token), new RegExp(v.error));
  });
}
