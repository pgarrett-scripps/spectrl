/** Adversarial decode: every malformed token must throw SpectrlDecodeError. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { deflateSync, inflateSync } from "node:zlib";

import { b64urlDecode, b64urlEncode } from "../src/base64url.js";
import { cborDecode, cborEncode } from "../src/cbor.js";
import { DESC_ARRAY, DESC_COMP, DESC_DATA } from "../src/header.js";
import { SpectrlDecodeError, decodeToken, encodeSpectrum, type InlineSpectrum } from "../src/index.ts";

function token(): string {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [100.0, 200.0, 300.0],
    intensity: [1e4, 2e4, 3e4],
  };
  return encodeSpectrum(spec, { quiet: true });
}

type Doc = Map<unknown, unknown>;

function payload(t: string): Doc {
  return cborDecode(b64urlDecode(t.split(".")[1]!)) as Doc;
}

/** Re-wrap a (tampered) document as an unhashed two-part token so decode
 * reaches the body instead of failing hash verification. */
function retoken(doc: Doc): string {
  return "spectrl2." + b64urlEncode(cborEncode(doc));
}

const GARBAGE = ["", "notatoken", "spectrl2", "spectrl1.AAAA", "spectrl2.", "spectrl2.!!!!", "spectrl2.A", "spectrl2.AAAA"];

for (const bad of GARBAGE) {
  test(`garbage token ${JSON.stringify(bad)} throws SpectrlDecodeError`, () => {
    assert.throws(() => decodeToken(bad), SpectrlDecodeError);
  });
}

test("truncated token throws SpectrlDecodeError", () => {
  const t = token();
  assert.throws(() => decodeToken(t.slice(0, Math.floor(t.length / 2))), SpectrlDecodeError);
});

test("missing length key throws SpectrlDecodeError", () => {
  const doc = payload(token());
  doc.delete(0);
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

for (const badLength of [-1, 1.5, true, "3"]) {
  test(`invalid declared length ${JSON.stringify(badLength)} is rejected`, () => {
    const doc = payload(token());
    doc.set(0, badLength);
    doc.set(6, []);
    assert.throws(() => decodeToken(retoken(doc)), /array length/);
  });
}

test("duplicate CBOR map keys are rejected before decoding", () => {
  const raw = Uint8Array.from(Buffer.from("a40001000101000780", "hex"));
  assert.throws(() => decodeToken("spectrl2." + b64urlEncode(raw)), /duplicate/);
});

test("duplicate semantic arrays are rejected", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  descs.push(new Map(descs[0]!));
  assert.throws(() => decodeToken(retoken(doc)), /duplicate array/);
});

test("unknown array data types are rejected", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  descs[0]!.set(0, 999999);
  assert.throws(() => decodeToken(retoken(doc)), /data type/);
});

test("Numpress descriptor fixed point must match the stream", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  descs[0]!.set(3, 100001);
  assert.throws(() => decodeToken(retoken(doc)), /fixed point mismatch/);
});

test("unknown codec throws SpectrlDecodeError", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(DESC_COMP, 999999);
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("corrupt blob throws SpectrlDecodeError", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(DESC_DATA, Uint8Array.from([0, 1, 2, 3]));
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("array length mismatch throws SpectrlDecodeError", () => {
  const doc = payload(token());
  doc.set(0, 5); // header claims 5 peaks; blobs hold 3
  assert.throws(() => decodeToken(retoken(doc)), /declares/);
});

test("zlib bomb is rejected without materializing", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(DESC_COMP, 1000574); // zlib raw
  descs[0]!.set(DESC_DATA, new Uint8Array(deflateSync(new Uint8Array(10 * 1024 * 1024)))); // expands ~1000x past the bound
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("misaligned raw blob throws SpectrlDecodeError", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(DESC_COMP, 1000574); // zlib raw; 7 bytes is not a float64 multiple
  descs[0]!.set(DESC_DATA, new Uint8Array(deflateSync(new Uint8Array(7))));
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("truncated numpress stream throws instead of decoding garbage", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  const mzDesc = descs.find((d) => d.get(DESC_ARRAY) === 1000514)!;
  const raw = new Uint8Array(inflateSync(mzDesc.get(DESC_DATA) as Uint8Array));
  mzDesc.set(DESC_DATA, new Uint8Array(deflateSync(raw.subarray(0, raw.length - 1))));
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});
