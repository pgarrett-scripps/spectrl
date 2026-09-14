import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { decodeToken, encodeSpectrum } from "../src/index.ts"
import { decodeV1Token } from "../src/legacy.ts"
import { cborEncode } from "../src/cbor.ts"
import { b64urlEncode } from "../src/base64url.ts"
import { installZstd } from "../src/zstd.ts"

installZstd()

import { tokenChecksum } from "../src/checksum.ts"

test("v2 rejects every use of reserved key 7", () => {
  for (const value of [null, "PEPTIDE", 0, new Map(), []]) {
    const body = "spectrl.v2." + b64urlEncode(cborEncode(new Map<number, unknown>([[0, 0], [7, value]])))
    assert.throws(() => decodeToken(body + "." + tokenChecksum(body)), /reserved/)
  }
})

test("identification input cannot be silently discarded", () => {
  const source = { defaultArrayLength: 0, interp: "PEPTIDE" }
  assert.throws(() => encodeSpectrum(source), /identification/)
  const token = encodeSpectrum({ defaultArrayLength: 0 })
  assert.equal(decodeToken(token).formatVersion, 2)
  assert.equal("interp" in decodeToken(token), false)
  assert.throws(() => decodeV1Token(token))
})

for (const filename of ["vectors.json", "reverse-vectors.json"]) {
  test(`archived v1 ${filename} requires the explicit legacy decoder`, () => {
    const vectors = JSON.parse(readFileSync(new URL(`../../test-vectors/v1/${filename}`, import.meta.url), "utf8")).vectors
    for (const vector of vectors) {
      assert.throws(() => decodeToken(vector.token))
      const decoded = decodeV1Token(vector.token)
      assert.equal(decoded.interpretation, vector.decoded.interp)
      assert.equal(decoded.spectrum.formatVersion, 1)
      assert.equal("interp" in decoded.spectrum, false)
      assert.equal(decoded.spectrum.defaultArrayLength, vector.decoded.default_array_length)
      const migrated = decodeToken(encodeSpectrum(decoded.spectrum, { lossless: true }))
      assert.equal(migrated.formatVersion, 2)
      for (const name of ["mz", "intensity", "charge"] as const) {
        assert.deepEqual(migrated[name], decoded.spectrum[name])
      }
      assert.deepEqual(migrated.precursors, decoded.spectrum.precursors)
      const corrupt = vector.token.slice(0, -1) + (vector.token.endsWith("0") ? "1" : "0")
      assert.throws(() => decodeV1Token(corrupt), /checksum/)
    }
  })
}
