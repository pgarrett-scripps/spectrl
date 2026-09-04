import assert from "node:assert/strict"
import test from "node:test"
import { encodeSpectrum, decodeToken, encodingPlan, tokenBreakdown, toFragment, extractToken } from "../src/index.ts"
import { encodeLinear, encodePic } from "../src/numpress.ts"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"
import { cborDecode, cborEncode } from "../src/cbor.ts"
import { tokenChecksum } from "../src/checksum.ts"
import { DESC_DATA } from "../src/header.ts"
import { zlibCompress } from "../src/zlibp.ts"

for (const mz of [[50000], [0, 1, 50000], [1e300]]) test(`linear overflow fallback ${mz}`, () => {
  const spec = { defaultArrayLength: mz.length, mz }
  assert.deepEqual(Array.from(decodeToken(encodeSpectrum(spec)).mz!), mz)
  assert.equal(encodingPlan(spec)[0]!.comp, 1000574)
  assert.throws(() => encodeSpectrum(spec, { arrayEncodings: { mz: "numlin-zlib" } }), /Numpress linear/)
})
for (const charge of [[4294967296], [1.5]]) test(`PIC boundary ${charge}`, () => {
  assert.deepEqual(Array.from(decodeToken(encodeSpectrum({ defaultArrayLength: 1, charge })).charge!), charge)
  assert.throws(() => encodePic(Float64Array.from(charge)), /uint32/)
})
test("linear residual range", () => assert.throws(() => encodeLinear(Float64Array.from([0, 0, 2147483648]), 1), /residual/))

test("arbitrary property names remain own array properties", () => {
  const extraArrays = JSON.parse('{"__proto__":[1,2],"constructor":[3,4],"toString":[5,6]}')
  const spec = { defaultArrayLength: 2, mz: [200, 100], extraArrays }
  const decoded = decodeToken(encodeSpectrum(spec, { lossless: true }))
  for (const key of Object.keys(extraArrays)) {
    assert.ok(Object.hasOwn(decoded.extraArrays, key))
    assert.deepEqual(Array.from(decoded.extraArrays[key]!), extraArrays[key].slice().reverse())
  }
  assert.equal(Object.getPrototypeOf(decoded.extraArrays), Object.prototype)
})

test("auto fixed points are applied and validated", () => {
  const spec = { defaultArrayLength: 1, mz: [1.23456] }
  assert.equal(encodingPlan(spec, { arrayEncodings: { mz: { fixedPoint: 1000 } } })[0]!.fixedPoint, 1000)
  for (const fixedPoint of [0, -1, 1.5]) assert.throws(() => encodeSpectrum(spec, { arrayEncodings: { mz: { fixedPoint } } }))
  assert.throws(() => encodeSpectrum(spec, { lossless: true, arrayEncodings: { mz: { fixedPoint: 1 } } }))
})

test("replace an existing URL fragment", () => {
  const token = encodeSpectrum({ defaultArrayLength: 0 })
  assert.equal(extractToken(toFragment(token, "https://example.org/?a=1#old")), token)
})

test("incomplete and concatenated zlib streams are rejected including empty arrays", () => {
  for (const mz of [[], [1, 2]]) {
    const original = encodeSpectrum({ defaultArrayLength: mz.length, mz }, { lossless: true })
    for (const mode of ["truncate", "junk", "concatenate"]) {
      const doc = cborDecode(b64urlDecode(original.split(".")[2]!)) as Map<number, unknown>
      const desc = (doc.get(6) as Map<number, unknown>[])[0]!
      const blob = desc.get(DESC_DATA) as Uint8Array
      desc.set(DESC_DATA, mode === "truncate" ? blob.slice(0, -4) : Uint8Array.from([...blob, ...(mode === "junk" ? [1, 2, 3] : zlibCompress(new Uint8Array()))]))
      const body = "spectrl.v1." + b64urlEncode(cborEncode(doc))
      assert.throws(() => decodeToken(body + "." + tokenChecksum(body)), /zlib/)
    }
  }
})

test("inspection rejects invalid structure", () => {
  const body = "spectrl.v1." + b64urlEncode(cborEncode(new Map([[0, -1]])))
  assert.throws(() => tokenBreakdown(body + "." + tokenChecksum(body)))
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 0, extraArrays: { "": [] } }))
})
