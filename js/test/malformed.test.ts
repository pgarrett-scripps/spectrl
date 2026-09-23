import { readTokenPayload } from "../src/cbor_format.ts"
/** Adversarial decode: every malformed token must throw SpectrlDecodeError. */

import assert from "node:assert/strict";
import { test } from "node:test";
import { deflateSync, inflateSync } from "node:zlib";

import { b64urlDecode, b64urlEncode } from "../src/base64url.js";
import { cborDecode, cborEncode } from "../src/cbor.js";
import { tokenChecksum } from "../src/checksum.js";
import { DESC_ARRAY, DESC_DATA } from "../src/header.js";
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
  return cborDecode(readTokenPayload(t)) as Doc;
}

/** Re-wrap a tampered document with a valid checksum so decode reaches it. */
function retoken(doc: Doc): string {
  const body = "spectrl.v3.r." + b64urlEncode(cborEncode(doc));
  return `${body}.${tokenChecksum(body)}`;
}

const GARBAGE = ["", "notatoken", "spectrl.v3", "spectrl1.AAAA", "spectrl.v3.", "spectrl.v3.!!!!", "spectrl.v3.A", "spectrl.v3.AAAA"];

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
  const body = "spectrl.v3.r." + b64urlEncode(raw);
  assert.throws(() => decodeToken(`${body}.${tokenChecksum(body)}`), /duplicate/);
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

test("Quantized descriptor rejects unknown parameters", () => {
  const doc = payload(encodeSpectrum({ defaultArrayLength: 3, mz: [100, 200, 300] }, { arrayEncodings: { mz: [3, 1, { scale: 1000, width: 4 }] } }))
  const descs = doc.get(6) as Array<Map<number, unknown>>
  (descs[0]!.get(2) as any[])[2].set("fp", 100001)
  assert.throws(() => decodeToken(retoken(doc)), /scale|width|parameter/);
});

test("Quantized descriptor requires parameters", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  descs[0]!.set(2, [3, 1]);
  assert.throws(() => decodeToken(retoken(doc)), /scale|width|parameter/);
});

test("unknown codec throws SpectrlDecodeError", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(2, [999999, 1]);
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
  assert.throws(() => decodeToken(retoken(doc)), /shape|count/);
});

test("zlib bomb is rejected without materializing", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(2, [0, 1]); // zlib raw
  descs[0]!.set(DESC_DATA, new Uint8Array(deflateSync(new Uint8Array(10 * 1024 * 1024)))); // expands ~1000x past the bound
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("misaligned raw blob throws SpectrlDecodeError", () => {
  const doc = payload(token());
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  descs[0]!.set(2, [0, 1]); // zlib raw; 7 bytes is not a float64 multiple
  descs[0]!.set(DESC_DATA, new Uint8Array(deflateSync(new Uint8Array(7))));
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});

test("truncated quantized words throws instead of decoding garbage", () => {
  const doc = payload(encodeSpectrum({ defaultArrayLength: 3, mz: [100, 200, 300], intensity: [1, 2, 3] }));
  const descs = doc.get(6) as Array<Map<string, unknown>>;
  const mzDesc = descs.find((d) => d.get(DESC_ARRAY) === 1000514)!;
  const raw = mzDesc.get(DESC_DATA) as Uint8Array;
  mzDesc.set(DESC_DATA, raw.subarray(0, raw.length - 1));
  assert.throws(() => decodeToken(retoken(doc)), SpectrlDecodeError);
});
