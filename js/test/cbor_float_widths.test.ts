import assert from "node:assert/strict"
import { test } from "node:test"
import { cborDecode, cborEncode, canonicalize, validateCborDocument } from "../src/cbor.ts"

// Expected bytes from Python cbor2.dumps(value, canonical=True).
const cases: [number, string][] = [
  [1.5, "f93e00"],
  [-1.5, "f9be00"],
  [23.5, "f94de0"],
  [2 ** -24, "f90001"],
  [2 ** -14 - 2 ** -24, "f903ff"],
  [2 ** -14, "f90400"],
  [2 ** -25, "fa33000000"],
  [1 + 2 ** -23, "fa3f800001"],
  [0.1, "fb3fb999999999999a"],
  [23.41, "fb403768f5c28f5c29"],
  [Number.MAX_VALUE, "fb7fefffffffffffff"],
  [Number.MIN_VALUE, "fb0000000000000001"],
]

for (const [value, hex] of cases) {
  test(`shortest exact CBOR float matches Python: ${value}`, () => {
    const bytes = cborEncode(value)
    assert.equal(Buffer.from(bytes).toString("hex"), hex)
    assert.ok(Object.is(cborDecode(bytes), value))
    validateCborDocument(bytes)
  })
}

test("nested float compaction preserves strings, integers, and opaque array bytes", () => {
  for (const length of [23, 24, 255, 256, 65536]) {
    const blob = new Uint8Array(length).fill(0xfb)
    const nested = new Map<unknown, unknown>([
      [1, [1.5, "x".repeat(length), blob, 23.41, 1 + 2 ** -23]],
      [0, new Map([["half", -1.5], ["integer", 65536]])],
    ])
    const expected = canonicalize(nested)
    const bytes = cborEncode(expected)
    validateCborDocument(bytes)
    assert.deepEqual(cborDecode(bytes), expected)
  }
})
