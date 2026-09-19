import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { decodeToken, encodeSpectrum, readTokenDocument, registerEncoding, registerExtension, topN } from "../src/index.ts"
import { encodings } from "../src/pipeline.ts"
const doc = JSON.parse(readFileSync(new URL("../../test-vectors/v3-pipelines.json", import.meta.url), "utf8"))
const metadata = (v: any): any => v instanceof Uint8Array ? "<bytes>" : v instanceof Map ? Object.fromEntries([...v].map(([k, x]) => [String(k), metadata(x)])) : Array.isArray(v) ? v.map(metadata) : v
for (const vector of doc.vectors) test(`v3 independent pipeline ${vector.name}`, () => {
  const decoded = decodeToken(vector.token)
  const ctor = { float32: Float32Array, float64: Float64Array, int32: Int32Array }[vector.dtype as "float32" | "float64" | "int32"]
  assert.ok(decoded.mz instanceof ctor)
  assert.equal(Buffer.from(decoded.mz!.buffer).toString("hex"), vector.hex)
  assert.equal(Buffer.from(decoded.intensity!.buffer).toString("hex"), vector.hex)
  const original = readTokenDocument(vector.token).doc
  const descriptors = original.get(6) as Map<number, any>[]
  const setting = { encoding: descriptors[0]!.get(2) }
  const encoded = encodeSpectrum(decoded, { lossless: true, arrayEncodings: { mz: setting, intensity: setting } })
  assert.deepEqual(metadata(readTokenDocument(encoded).doc), vector.metadata)
})
test("custom numeric encoding registry roundtrip", () => {
  const raw = encodings.get(JSON.stringify([0, 1]))!
  registerEncoding("test:raw", raw)
  const t = encodeSpectrum({ defaultArrayLength: 2, mz: new Float32Array([1, 2]) }, {
    lossless: true, arrayEncodings: { mz: { encoding: "test:raw" } },
  })
  assert.deepEqual(decodeToken(t).mz, new Float32Array([1, 2]))
  assert.throws(() => registerEncoding("test:raw", raw), /already registered/)
})
test("required extensions permit inspection but gate decoding and mutation", () => {
  const spec = { defaultArrayLength: 2, mz: [1, 2], intensity: [3, 4], extensions: {
    "test:required": { revision: 1, required: true, data: [1, 2] },
  } }
  const token = encodeSpectrum(spec, { lossless: true })
  assert.ok(readTokenDocument(token).decoded.extensions)
  assert.throws(() => decodeToken(token), /unsupported required extension/)
  assert.throws(() => topN(spec, 1), /extensions/)
  registerExtension("test:required", data => assert.deepEqual(data, [1, 2]))
  assert.deepEqual(decodeToken(token).extensions, spec.extensions)
})
