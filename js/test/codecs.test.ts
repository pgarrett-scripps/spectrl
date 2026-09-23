import assert from "node:assert/strict"
import { test } from "node:test"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"

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

test("base64url decode accepts only the canonical unpadded spelling", () => {
  const data = Uint8Array.from([0xff, 0xee, 0xdd, 0xcc]);
  const canonical = b64urlEncode(data);
  assert.deepEqual(Array.from(b64urlDecode(canonical)), Array.from(data));
  // One spelling per payload: padding and non-zero unused trailing bits are errors.
  assert.throws(() => b64urlDecode(canonical + "="), /unpadded/);
  assert.throws(() => b64urlDecode("_-5"), /trailing bits/); // "_-4" is the canonical spelling of those bytes
  assert.deepEqual(Array.from(b64urlDecode("_-4")), [0xff, 0xee]);
  // strict: standard-base64 chars, whitespace, and impossible lengths rejected
  assert.throws(() => b64urlDecode("+/=="));
  assert.throws(() => b64urlDecode("AA A"));
  assert.throws(() => b64urlDecode("A"));
});
