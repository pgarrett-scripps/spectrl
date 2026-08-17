/** Low-level unit tests: base64url and numpress boundaries. */

import assert from "node:assert/strict";
import { test } from "node:test";

import { b64urlDecode, b64urlEncode } from "../src/base64url.ts";
import { cborDecode } from "../src/cbor.ts";
import { decodeArray, DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, encodeArray, safeSlofFp } from "../src/codecs.ts";
import { DESC_ARRAY, DESC_FP } from "../src/header.ts";
import { encodeSpectrum, type InlineSpectrum } from "../src/index.ts";
import { decodeLinear, decodePic, decodeSlof, encodeLinear, encodePic, encodeSlof } from "../src/numpress.ts";
import { installZstd } from "../src/zstd.ts";

installZstd();

test("zstd decoding honors the declared output bound", () => {
  const blob = encodeArray(Float64Array.from({ length: 1000 }, (_, i) => i), 1003780, null);
  assert.throws(() => decodeArray(blob, 1003780, 1000523, 32), /exceeds/);
});

test("zstd raw codec handles boundary array lengths", () => {
  for (const n of [0, 1, 2, 3, 1000]) {
    const expected = Float64Array.from({ length: n }, (_, i) => i * 0.25);
    const blob = encodeArray(expected, 1003780, null);
    assert.deepEqual(decodeArray(blob, 1003780), expected);
  }
});

// ── base64url ──────────────────────────────────────────────────────────────

test("base64url round-trips every byte value and all lengths", () => {
  for (let len = 0; len < 260; len++) {
    const data = new Uint8Array(len);
    for (let i = 0; i < len; i++) data[i] = (i * 37 + len) & 0xff;
    const enc = b64urlEncode(data);
    assert.ok(!enc.includes("="), "no padding");
    assert.ok(!/[+/]/.test(enc), "url-safe alphabet");
    assert.deepEqual(Array.from(b64urlDecode(enc)), Array.from(data), `len ${len}`);
  }
});

test("base64url decode tolerates padding but rejects non-alphabet input", () => {
  const data = Uint8Array.from([0xff, 0xee, 0xdd, 0xcc]);
  const padded = b64urlEncode(data) + "="; // trailing padding tolerated
  assert.deepEqual(Array.from(b64urlDecode(padded)), Array.from(data));
  // strict: standard-base64 chars, whitespace, and impossible lengths rejected
  assert.throws(() => b64urlDecode("+/=="));
  assert.throws(() => b64urlDecode("AA A"));
  assert.throws(() => b64urlDecode("A"));
});

// ── numpress boundaries ────────────────────────────────────────────────────

const FP = 100000.0;

test("numpress linear handles 0/1/2/n element arrays", () => {
  for (const arr of [[], [123.456], [100.0, 200.0], [100.0, 100.5, 101.0, 250.25, 999.999]]) {
    const data = Float64Array.from(arr);
    const out = decodeLinear(encodeLinear(data, FP));
    assert.equal(out.length, data.length);
    for (let i = 0; i < data.length; i++) assert.ok(Math.abs(out[i]! - data[i]!) < 1e-3, `mz[${i}]`);
  }
});

test("numpress slof round-trips intensities within tolerance", () => {
  const data = Float64Array.from([0, 1e3, 5e4, 9.9e4, 1e5]);
  const out = decodeSlof(encodeSlof(data, 3600.0));
  assert.equal(out.length, data.length);
  for (let i = 0; i < data.length; i++) {
    const tol = Math.max(1.0, data[i]! * 1e-2);
    assert.ok(Math.abs(out[i]! - data[i]!) <= tol, `int[${i}]: ${out[i]} vs ${data[i]}`);
  }
});

test("numpress pic round-trips non-negative integers exactly", () => {
  const data = Float64Array.from([0, 1, 2, 1, 3, 100, 7]);
  const out = decodePic(encodePic(data));
  assert.deepEqual(Array.from(out), Array.from(data));
});

// ── Numpress fixed point ──────────────────────────────────────────────────────

test("clamped slof fp is a whole number that cannot overflow uint16", () => {
  for (const peak of [9.9e8, 1.0e9, 5.0e9, 1.0e12]) {
    const fp = safeSlofFp(Float64Array.from([1.0, peak]), DEFAULT_NUMSLOF_FP);
    assert.equal(Number.isInteger(fp), true, `fp ${fp} is not a whole number`);
    assert.ok(Math.log(peak + 1) * fp <= 65535, `fp ${fp} overflows uint16 for peak ${peak}`);
  }
});

test("descriptor records fp when it is the codec default", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [100, 200, 300],
    intensity: [1e3, 2e3, 3e3],
  };
  const doc = cborDecode(b64urlDecode(encodeSpectrum(spec, { quiet: true }).split(".")[2]!)) as Map<number, unknown>;
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  assert.equal(descs[0]!.get(DESC_FP), DEFAULT_NUMLIN_FP);
  assert.equal(descs[1]!.get(DESC_FP), DEFAULT_NUMSLOF_FP);
});

test("descriptor carries a clamped fp as an integer", () => {
  const spec: InlineSpectrum = {
    defaultArrayLength: 3,
    mz: [100, 200, 300],
    intensity: [1e8, 5e8, 9.9e8],
  };
  const doc = cborDecode(b64urlDecode(encodeSpectrum(spec, { quiet: true }).split(".")[2]!)) as Map<number, unknown>;
  const descs = doc.get(6) as Array<Map<number, unknown>>;
  const intensity = descs.find((d) => d.get(DESC_ARRAY) === 1000515)!;
  const fp = intensity.get(DESC_FP) as number;
  assert.ok(fp !== undefined, "clamped fp must be recorded");
  assert.equal(Number.isInteger(fp), true);
  assert.ok(fp < DEFAULT_NUMSLOF_FP);
});
