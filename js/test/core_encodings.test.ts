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

test("seeded finite bit patterns survive every exact encoding and stable sorting", () => {
  let seed = 7301
  const randomWord = () => seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
  for (const Ctor of [Float32Array, Float64Array, Int32Array]) {
    const words = Uint32Array.from({ length: 256 }, randomWord)
    const values = new Ctor(words.buffer).filter(Number.isFinite)
    const mz = Array.from(values, () => randomWord() % 9)
    const order = [...mz.keys()].sort((a, b) => mz[a]! - mz[b]! || a - b)
    const expected = Ctor.from(order, i => values[i]!)
    for (const compression of ["raw", "zlib"] as const) for (const encoding of [0, 1, 2]) {
      const token = encodeSpectrum({ defaultArrayLength: values.length, mz, extraArrays: { custom: values } },
        { lossless: true, compression, arrayEncodings: { custom: encoding }, quiet: true })
      const actual = decodeToken(token).extraArrays.custom!
      assert.ok(actual instanceof Ctor)
      assert.deepEqual(new Uint8Array(actual.buffer), new Uint8Array(expected.buffer))
    }
  }
})
