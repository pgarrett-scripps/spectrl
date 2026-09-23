import test from "node:test"
import assert from "node:assert/strict"
import { encodeQuantized, decodeQuantized, validateQuantized, ppmParameters, intensityParameters } from "../src/quantized.ts"
import { encodeSpectrum, decodeToken } from "../src/index.ts"

test("hand-calculated quantized word layouts", () => {
  assert.equal(Buffer.from(encodeQuantized(Float64Array.from([1, 2, 2.5]), 1000523,
    { scale: 2, width: 1, delta: true })).toString("hex"), "020201")
  assert.equal(Buffer.from(encodeQuantized(Float64Array.from([256, 513]), 1000523,
    { scale: 1, width: 2 })).toString("hex"), "00010102")
})
for (const width of [1, 2, 4, 8]) for (const delta of [false, true]) for (const log of [false, true]) {
  test(`quantized bound width ${width} delta ${delta} log ${log}`, () => {
    const values = Float64Array.from([0, 0.001, 1.234, 2.567, 1.2])
    const params = { scale: 10, width, delta, log }
    const blob = encodeQuantized(values, 1000523, params)
    const decoded = decodeQuantized(blob, 1000523, values.length, params)
    for (const [i, x] of values.entries()) assert.ok(Math.abs(x - decoded[i]!) <= (log ? (x + 1) * Math.expm1(0.05) : 0.05))
  })
}
test("quantizer rejects malformed parameters and unsafe indices", () => {
  for (const p of [{}, { scale: 0, width: 1 }, { scale: true, width: 1 }, { scale: 1, width: true },
    { scale: 1, width: 3 }, { scale: 1, width: 1, log: 1 }, { scale: Infinity, width: 1 }]) assert.throws(() => validateQuantized(p))
  const p = { scale: 1, width: 8, delta: true }
  const values = Float64Array.from([2**32 + 1, 2**53 - 1, 0])
  assert.deepEqual(decodeQuantized(encodeQuantized(values, 1000523, p), 1000523, 3, p), values)
  for (const v of [-1, Infinity, 2**53]) assert.throws(() => encodeQuantized(Float64Array.of(v), 1000523, p))
  assert.throws(() => decodeQuantized(Uint8Array.of(), 1000523, 1, p))
  assert.throws(() => decodeQuantized(new Uint8Array(8).fill(255), 1000523, 1, p))
})
test("integer defaults preserve their numeric type", () => {
  const input = new Int32Array([1, 2, 3])
  const decoded = decodeToken(encodeSpectrum({ defaultArrayLength: 3, mz: input, intensity: input }))
  assert.deepEqual(decoded.mz, input)
  assert.deepEqual(decoded.intensity, input)
})
for (const Dtype of [Float32Array, Float64Array]) {
  test(`default m/z checks pointwise 0.1 ppm for ${Dtype.name}`, () => {
    const source = Dtype.from([0, 0, 0.001234567, ...Array.from({ length: 1000 }, (_, i) => 10 ** (6 * i / 999))])
    const decoded = decodeToken(encodeSpectrum({ defaultArrayLength: source.length, mz: source }, { quiet: true }))
    let maxAbsoluteError = 0
    for (const [i, value] of source.entries()) {
      const error = Math.abs(decoded.mz![i]! - value)
      assert.ok(error <= value * 1e-7)
      maxAbsoluteError = Math.max(maxAbsoluteError, error)
      if (i) assert.ok(decoded.mz![i]! >= decoded.mz![i - 1]!)
    }
    assert.equal(decoded.mz![0], 0)
    assert.equal(decoded.mz![1], 0)
    assert.ok(maxAbsoluteError > 5e-6)
  })
}
test("default m/z preserves zero and unsupported domains", () => {
  for (const values of [[], [0, 0], [0, 1e-300, 100], [0, Number.MIN_VALUE, 100]]) {
    const mz = Float64Array.from(values)
    assert.deepEqual(decodeToken(encodeSpectrum({ defaultArrayLength: mz.length, mz })).mz, mz)
  }
})
test("explicit linear m/z grid remains available", () => {
  const mz = Float64Array.from([100.123456, 500.234567, 1000.345678])
  const decoded = decodeToken(encodeSpectrum({ defaultArrayLength: mz.length, mz }, {
    arrayEncodings: { mz: { encoding: [3, 1, { scale: 100000, width: 4, delta: true }] } },
  }))
  for (const [i, value] of mz.entries()) assert.ok(Math.abs(decoded.mz![i]! - value) <= 5e-6)
})
test("ppm parameters reject invalid error bounds", () => {
  for (const ppm of [0, -1, NaN, Infinity]) assert.throws(() => ppmParameters(Float64Array.of(100), ppm))
})
test("default intensity scale refines below one and keeps small peaks", () => {
  assert.equal(intensityParameters(Float64Array.of(1, 3, 1e5)).scale, 3600)
  assert.equal(intensityParameters(Float64Array.of(0, 0, 0)).scale, 3600)
  assert.equal(intensityParameters(Float64Array.of(0.5, 2)).scale, 5400)
  assert.throws(() => intensityParameters(Float64Array.of(1e-300, 1)), /outside the supported range/)
  const intensity = Float64Array.of(1e-5, 0.3, 1)
  const decoded = decodeToken(encodeSpectrum({ defaultArrayLength: 3, mz: Float64Array.of(100, 200, 300), intensity }))
  for (const [i, value] of intensity.entries())
    assert.ok(Math.abs(decoded.intensity![i]! - value) <= value * 2 * Math.expm1(0.5 / 3600))
})
