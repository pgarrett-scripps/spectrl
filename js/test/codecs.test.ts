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

test("base64url decode tolerates padding but rejects non-alphabet input", () => {
  const data = Uint8Array.from([0xff, 0xee, 0xdd, 0xcc]);
  const padded = b64urlEncode(data) + "="; // trailing padding tolerated
  assert.deepEqual(Array.from(b64urlDecode(padded)), Array.from(data));
  // strict: standard-base64 chars, whitespace, and impossible lengths rejected
  assert.throws(() => b64urlDecode("+/=="));
  assert.throws(() => b64urlDecode("AA A"));
  assert.throws(() => b64urlDecode("A"));
});
