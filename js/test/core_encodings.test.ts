import assert from "node:assert/strict"
import { test } from "node:test"
import { decodeToken, encodeSpectrum, encodingPlan } from "../src/index.ts"
import { encodings, encodePipeline, decodePipeline } from "../src/pipeline.ts"

test("three exact representations preserve native bits and enforce counts", () => {
  for (const n of [0, 1, 2, 31, 256]) {
    for (const type of [1000521, 1000523, 1000519]) {
      const Ctor = type === 1000521 ? Float32Array : type === 1000523 ? Float64Array : Int32Array
      const a = Ctor.from({ length: n }, (_, i) => i === 0 ? -0 : i % 2 ? -12345.67 : 2147483647)
      for (const id of [0, 1, 2]) {
        const { blob, fidelity } = encodePipeline(a, type, [id, 1])
        const b = decodePipeline(blob, type, n, [id, 1], fidelity)
        assert.deepEqual(new Uint8Array(b.buffer), new Uint8Array(a.buffer))
        assert.throws(() => decodePipeline(new Uint8Array([...blob, 0]), type, n, [id, 1], fidelity))
      }
    }
  }
})

test("only four builtins and no development codec aliases", () => {
  assert.equal(encodings.size, 4)
  const s = { defaultArrayLength: 1, mz: [1], intensity: [2] }
  assert.deepEqual(encodingPlan(s, { lossless: true }).map(p => p.encoding), [[2, 1], [1, 1]])
  for (const option of ["numlin-zlib", "numpic-zstd", "numslof-zlib", "dictionary-zstd", "zlib", "MS:1002746", 1002746, { compression: "zlib" }, { encoding: 0, compression: 0 }, { codec: "raw" }, { fixedPoint: 1000 }]) {
    assert.throws(() => encodeSpectrum(s, { arrayEncodings: { mz: option as any } }))
  }
})

test("explicit quantization and custom array permission", () => {
  const s = { defaultArrayLength: 2, mz: [1.01, 2.04], extraArrays: { score: [1.01, 2.04] } }
  const option: [number, number, Record<string, number>] = [3, 1, { scale: 10, width: 1 }]
  assert.throws(() => encodeSpectrum(s, { lossless: true, arrayEncodings: { mz: option } }), /lossy/)
  assert.throws(() => encodeSpectrum(s, { arrayEncodings: { score: option } }), /permission/)
  const d = decodeToken(encodeSpectrum(s, { arrayEncodings: { score: option }, allowUnsafeLossyCustom: true }))
  assert.deepEqual(Array.from(d.extraArrays.score!), [1, 2])
})
