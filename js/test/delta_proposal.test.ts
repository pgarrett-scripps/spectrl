import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { deltaShuffle, deltaUnshuffle } from "../src/delta.ts"
import { zlibCompress, zlibDecompress } from "../src/zlibp.ts"

const vectors = JSON.parse(readFileSync(new URL("../../test-vectors/delta-proposal.json", import.meta.url), "utf8")).vectors

test("proposed delta codec matches independent vectors and decodes Python streams", () => {
  for (const vector of vectors) {
    const raw = Buffer.from(vector.raw_hex, "hex")
    const shuffled = Buffer.from(vector.shuffled_hex, "hex")
    const width = vector.item_size
    assert.deepEqual(Buffer.from(deltaShuffle(raw, width)), shuffled)
    assert.deepEqual(Buffer.from(deltaUnshuffle(shuffled, width)), raw)
  }
})

test("proposed codec handles random patterns and views with a nonzero offset", () => {
  let state = 901
  for (const width of [4, 8]) {
    for (const n of [0, 1, 2, 3, 33, 257, 1024]) {
      const storage = new Uint8Array(n * width + 11)
      const raw = storage.subarray(7, 7 + n * width)
      let i = 0
      while (i < raw.length) {
        state = (Math.imul(state, 1664525) + 1013904223) >>> 0
        raw[i] = state >>> 24
        i += 1
      }
      assert.deepEqual(deltaUnshuffle(deltaShuffle(raw, width), width), raw)
    }
  }
})

test("proposed codec rejects invalid widths, framing, and decompression over budget", () => {
  for (const width of [0, 1, 2, 16]) assert.throws(() => deltaShuffle(new Uint8Array(), width))
  assert.throws(() => deltaUnshuffle(new Uint8Array(3), 4), /multiple/)
})
