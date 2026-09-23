import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { encodeSpectrum } from "../src/index.ts"
import { cborDecode, cborEncode, canonicalize, validateCborDocument } from "../src/cbor.ts"
import { inputSpectrum } from "../scripts/token_parity.ts"

const inputs = JSON.parse(readFileSync(new URL("../../test-vectors/token-parity-inputs.json", import.meta.url), "utf8"))
const tokens = JSON.parse(readFileSync(new URL("../../test-vectors/token-parity.json", import.meta.url), "utf8"))
for (const item of inputs) {
  for (const lossless of [true, false]) {
    test(`complete raw token matches Python: ${item.name}, lossless=${lossless}`, () => {
      const token = encodeSpectrum(inputSpectrum(item.spec), { lossless, compression: "raw", quiet: true })
      assert.equal(token, tokens[item.name][lossless ? "lossless" : "lossy"])
    })
  }
}

test("safe integers including uint64/int64 keys use Python's integer representation", () => {
  const cases: [number, string][] = [
    [2, "02"], [-0, "00"], [2 ** 32, "1b0000000100000000"],
    [-(2 ** 32) - 1, "3b0000000100000000"],
    [Number.MAX_SAFE_INTEGER, "1b001fffffffffffff"],
    [Number.MIN_SAFE_INTEGER, "3b001ffffffffffffe"],
  ]
  for (const [value, hex] of cases) {
    const bytes = cborEncode(value)
    assert.equal(Buffer.from(bytes).toString("hex"), hex)
    assert.equal(cborDecode(bytes), value === 0 ? 0 : value)
    const map = new Map([[value, value]])
    const encodedMap = cborEncode(canonicalize(map))
    validateCborDocument(encodedMap)
    assert.deepEqual(cborDecode(encodedMap), new Map([[value, value === 0 ? 0 : value]]))
  }
})
