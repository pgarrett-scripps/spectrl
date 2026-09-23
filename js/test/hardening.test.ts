import { readTokenPayload } from "../src/cbor_format.ts"
import assert from "node:assert/strict"
import test from "node:test"
import { encodeSpectrum, decodeToken, encodingPlan, tokenBreakdown, toFragment, extractToken } from "../src/index.ts"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"
import { cborDecode, cborEncode } from "../src/cbor.ts"
import { tokenChecksum } from "../src/checksum.ts"
import { DESC_DATA } from "../src/header.ts"
import { zlibCompress } from "../src/zlibp.ts"

for (const mz of [[50000], [0, 1, 50000], [1e300]]) test(`large m/z values respect the ppm bound ${mz}`, () => {
  const spec = { defaultArrayLength: mz.length, mz }
  const decoded = decodeToken(encodeSpectrum(spec)).mz!
  for (const [i, value] of mz.entries()) assert.ok(Math.abs(decoded[i]! - value) <= value * 1e-7)
  // The default keeps the ppm grid only when it is smaller than exact delta.
  assert.ok([2, 3].includes(encodingPlan(spec)[0]!.encoding![0] as number))
})
for (const charge of [[4294967296], [1.5]]) test(`PIC boundary ${charge}`, () => {
  assert.deepEqual(Array.from(decodeToken(encodeSpectrum({ defaultArrayLength: 1, charge })).charge!), charge)
})

test("arbitrary property names remain own array properties", () => {
  const extraArrays = JSON.parse('{"__proto__":[1,2],"constructor":[3,4],"toString":[5,6]}')
  const spec = { defaultArrayLength: 2, mz: [200, 100], extraArrays }
  const decoded = decodeToken(encodeSpectrum(spec, { lossless: true, arrayEncodings: { mz: "raw" } }))
  for (const key of Object.keys(extraArrays)) {
    assert.ok(Object.hasOwn(decoded.extraArrays, key))
    assert.deepEqual(Array.from(decoded.extraArrays[key]!), extraArrays[key].slice().reverse())
  }
  assert.equal(Object.getPrototypeOf(decoded.extraArrays), Object.prototype)
})


test("replace an existing URL fragment", () => {
  const token = encodeSpectrum({ defaultArrayLength: 0 })
  assert.equal(extractToken(toFragment(token, "https://example.org/?a=1#old")), token)
})


test("inspection rejects invalid structure", () => {
  const body = "spectrl.v3.r." + b64urlEncode(cborEncode(new Map([[0, -1]])))
  assert.throws(() => tokenBreakdown(body + "." + tokenChecksum(body)))
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 0, extraArrays: { "": [] } }))
})
