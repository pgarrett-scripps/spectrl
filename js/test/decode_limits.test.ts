import assert from "node:assert/strict"
import test from "node:test"
import { DEFAULT_DECODE_LIMITS, decodeToken, encodeSpectrum, SpectrlDecodeError } from "../src/index.ts"
import { decodeV1Token } from "../src/legacy.ts"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"
import { cborDecode, cborEncode } from "../src/cbor.ts"
import { tokenChecksum } from "../src/checksum.ts"

const token = encodeSpectrum({
  defaultArrayLength: 2,
  mz: [100, 200], intensity: [1, 2],
  extraArrays: { score: new Float32Array([1, 2]), index: new Int32Array([0, 1]) },
}, { lossless: true })

const limits = { maxTokenBytes: token.length, maxPeaks: 2, maxArrays: 4, maxDecodedBytes: 48 }

test("exact budgets account for all arrays and declared dtypes", () => {
  const decoded = decodeToken(token, limits)
  assert.ok(decoded.extraArrays.score instanceof Float32Array)
  assert.ok(decoded.extraArrays.index instanceof Int32Array)
  for (const [key, value] of Object.entries(limits)) {
    assert.throws(() => decodeToken(token, { ...limits, [key]: value - 1 }),
      (e: unknown) => e instanceof SpectrlDecodeError && e.message.includes(key))
  }
  assert.equal(limits.maxDecodedBytes, 48)
})

function frame(doc: unknown, version = 2) {
  const body = `spectrl.v${version}.${b64urlEncode(cborEncode(doc))}`
  return `${body}.${tokenChecksum(body)}`
}

test("aggregate budget is checked before decompressing even the first array", () => {
  const doc = cborDecode(b64urlDecode(token.split(".")[2]!)) as Map<number, unknown>
  const descriptors = doc.get(6) as Map<number, unknown>[]
  descriptors[0]!.set(5, new Uint8Array([0xff]))
  const badBlob = frame(doc)
  assert.throws(() => decodeToken(badBlob, { maxDecodedBytes: 47 }), /maxDecodedBytes/)
  assert.throws(() => decodeToken(badBlob, { maxDecodedBytes: 48 }), /malformed array blob/)
})

test("token limit precedes checksum and CBOR work", () => {
  assert.throws(() => decodeToken("x".repeat(100), { maxTokenBytes: 99 }), /maxTokenBytes/)
})

test("metadata only and empty arrays still obey peak and array limits", () => {
  assert.throws(() => decodeToken(encodeSpectrum({ defaultArrayLength: 100 }), { maxPeaks: 99 }), /maxPeaks/)
  const empty = encodeSpectrum({ defaultArrayLength: 0,
    extraArrays: Object.fromEntries(Array.from({ length: 65 }, (_, i) => [`a${i}`, []])),
  })
  assert.equal(Object.keys(decodeToken(empty).extraArrays).length, 65)
  assert.throws(() => decodeToken(empty, {}), /maxArrays/)
  assert.equal(Object.keys(decodeToken(empty, { maxArrays: 65, maxDecodedBytes: 0 }).extraArrays).length, 65)
  assert.ok(decodeToken(encodeSpectrum({ defaultArrayLength: 0 }), { maxPeaks: 0, maxArrays: 0, maxDecodedBytes: 0 }))
})

test("Numpress is budgeted as decoded float64", () => {
  const compressed = encodeSpectrum({ defaultArrayLength: 2, mz: [100, 200], intensity: [1, 2] })
  assert.ok(decodeToken(compressed, { maxDecodedBytes: 32 }))
  assert.throws(() => decodeToken(compressed, { maxDecodedBytes: 31 }), /maxDecodedBytes/)
})

test("invalid configuration is rejected and undefined fields keep defaults", () => {
  for (const key of Object.keys(DEFAULT_DECODE_LIMITS)) {
    for (const value of [-1, true, 1.5, NaN, Infinity, "10", 2 ** 53, null]) {
      assert.throws(() => decodeToken(token, { [key]: value }), RangeError)
    }
  }
  assert.ok(decodeToken(token, { maxArrays: undefined }))
  assert.ok(Object.isFrozen(DEFAULT_DECODE_LIMITS))
})

test("legacy decoding applies the same budgets", () => {
  const body = `spectrl.v1.${token.split(".")[2]}`
  const legacy = `${body}.${tokenChecksum(body)}`
  assert.equal(decodeV1Token(legacy, { maxDecodedBytes: 48 }).spectrum.defaultArrayLength, 2)
  assert.throws(() => decodeV1Token(legacy, { maxDecodedBytes: 47 }), /maxDecodedBytes/)
})

test("caller budgets cannot relax wire format ceilings", () => {
  const doc = cborDecode(b64urlDecode(token.split(".")[2]!)) as Map<number, unknown>
  doc.set(0, 4_000_001)
  assert.throws(() => decodeToken(frame(doc), { maxPeaks: 10_000_000 }), /invalid declared array length/)
})
