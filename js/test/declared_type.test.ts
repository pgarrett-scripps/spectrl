/** Every encoding reconstructs the array's declared type, lossy ones included. */

import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { zlibCompress } from "../src/zlibp.ts"

import { decodeToken, encodeSpectrum, encodingPlan } from "../src/index.ts"
import { decodeQuantized, encodeQuantized, intensityParameters, ppmParameters, quantizedParameters } from "../src/quantized.ts"
import { defaultCandidates } from "../src/canonical.ts"
import { decodePipeline, encodePipeline, type Operation } from "../src/pipeline.ts"

const F32 = 1000521, F64 = 1000523
const here = dirname(fileURLToPath(import.meta.url))
const inputs = JSON.parse(readFileSync(resolve(here, "../../test-vectors/token-parity-inputs.json"), "utf-8"))
const EXPLICIT: Record<string, Operation> = {
  raw: [0, 1],
  "byte-shuffle": [1, 1],
  "modular-delta-shuffle": [2, 1],
  "quantized-linear": [3, 1, { scale: 1000, width: 4, delta: true }],
  "quantized-log": [3, 1, { scale: 3600, width: 2, log: true }],
  "rounded-float": [4, 1, { bits: 12, width: 4 }],
}

function lcg(seed: number) {
  let state = seed
  return () => (state = (state * 1103515245 + 12345) % 2 ** 31) / 2 ** 31
}
const make = (ctor: typeof Float32Array | typeof Float64Array, values: number[]) => ctor.from(values)
const mzValues = (n = 64, seed = 3) => { const r = lcg(seed); return Array.from({ length: n }, () => 150 + r() * 1650).sort((a, b) => a - b) }
const countValues = (n = 64, seed = 4) => { const r = lcg(seed); return Array.from({ length: n }, () => Math.floor(r() * 5000)) }
const logNormal = (n: number, seed: number, spread: number) => { const r = lcg(seed); return Array.from({ length: n }, () => Math.exp(3 + (r() - 0.5) * spread)) }

for (const ctor of [Float32Array, Float64Array]) for (const [name, enc] of Object.entries(EXPLICIT)) {
  test(`${name} decodes ${ctor.name} to ${ctor.name}`, () => {
    const spec = { defaultArrayLength: 64, mz: make(ctor, mzValues()), intensity: make(ctor, logNormal(64, 5, 12)) }
    const encodings = { mz: enc, intensity: enc }
    const tail = `MS:${ctor === Float32Array ? F32 : F64}`
    assert.deepEqual(encodingPlan(spec, { arrayEncodings: encodings }).slice(0, 2).map((p) => p.typeAccession), [tail, tail])
    const decoded = decodeToken(encodeSpectrum(spec, { arrayEncodings: encodings }))
    assert.ok(decoded.mz instanceof ctor)
    assert.ok(decoded.intensity instanceof ctor)
  })
}

for (const name of ["raw", "byte-shuffle", "modular-delta-shuffle"]) {
  test(`int32 array keeps int32 under ${name}`, () => {
    const spec = { defaultArrayLength: 3, mz: [1, 2, 3], extraArrays: { flags: Int32Array.of(3, 1, 2) } }
    assert.ok(decodeToken(encodeSpectrum(spec, { arrayEncodings: { flags: EXPLICIT[name]! } })).extraArrays.flags instanceof Int32Array)
  })
}

for (const name of ["quantized-linear", "rounded-float"]) {
  test(`${name} declares float64 for an int32 array`, () => {
    const spec = { defaultArrayLength: 3, mz: [1, 2, 3], extraArrays: { flags: Int32Array.of(3, 1, 2) } }
    const token = encodeSpectrum(spec, { arrayEncodings: { flags: EXPLICIT[name]! }, allowUnsafeLossyCustom: true })
    assert.ok(decodeToken(token).extraArrays.flags instanceof Float64Array)
  })
}

for (const ctor of [Float32Array, Float64Array]) for (const key of ["mz", "intensity"]) {
  test(`every default ${key} candidate declares and decodes ${ctor.name}`, () => {
    const source = make(ctor, key === "mz" ? mzValues() : countValues())
    const tail = ctor === Float32Array ? F32 : F64
    const candidates = defaultCandidates(key, source, false, 0.1, 3600)
    assert.equal(candidates.length, key === "mz" ? 2 : 4)
    let failed = 0
    for (const [type, build] of candidates) {
      assert.equal(type, tail)
      let enc: Operation
      try { enc = build() } catch { failed++; continue }
      const { blob, fidelity } = encodePipeline(source, type, enc)
      assert.ok(decodePipeline(blob, type, source.length, enc, fidelity) instanceof ctor)
    }
    // Only the float32 ppm candidate fails its checked bound here, as in Python.
    assert.equal(failed, key === "mz" && ctor === Float32Array ? 1 : 0)
  })
}

for (const params of [{ scale: 1000, width: 4 }, { scale: 7.25, width: 2, delta: true },
  { scale: 3600, width: 2, log: true }, { scale: 5_000_000, width: 4, log: true, delta: true }]) {
  test(`float32 decode rounds the binary64 reconstruction to nearest even ${JSON.stringify(params)}`, () => {
    const r = lcg(6)
    const source = Float64Array.from(Array.from({ length: 500 }, () => r() * 1800).sort((a, b) => a - b))
    const blob = encodeQuantized(source, F64, params)
    const wide = decodeQuantized(blob, F64, source.length, params)
    const narrow = decodeQuantized(blob, F32, source.length, params)
    assert.ok(narrow instanceof Float32Array)
    for (let i = 0; i < source.length; i++) assert.ok(Object.is(narrow[i], Math.fround(wide[i]!)))
  })
}

test("float32 reconstruction that overflows is rejected", () => {
  const params = { scale: 1, width: 1, log: true }
  assert.ok(decodeQuantized(Uint8Array.of(100), F64, 1, params)[0]! > 3.4028234663852886e38)
  assert.throws(() => decodeQuantized(Uint8Array.of(100), F32, 1, params), /finite/)
})

test("explicit float32 grid accounts for the final rounding", () => {
  const r = lcg(8)
  const source = Float32Array.from(Array.from({ length: 20000 }, () => 1 + r() * 1999))
  const params = quantizedParameters(source, 100000, true)
  const { blob, fidelity } = encodePipeline(source, F32, [3, 1, params])
  const decoded = decodePipeline(blob, F32, source.length, [3, 1, params], fidelity)
  let beyondGrid = false
  for (let i = 0; i < source.length; i++) {
    const x = source[i]!, y = decoded[i]!
    const grid = (x + 1) * Math.expm1(0.5 / 100000)
    if (Math.abs(y - x) > grid) beyondGrid = true
    assert.ok(Math.abs(y - x) <= grid + Math.max(y * 2 ** -24, 2 ** -150))
  }
  assert.ok(beyondGrid)
})

test("float32 ppm candidate fails its bound and exact wins", () => {
  const input = inputs.find((x: { name: string }) => x.name === "float32-mz-ppm-fails").spec
  const mz = Float32Array.from(input.mz as number[])
  const grid = ppmParameters(mz, 0.1, F64)
  assert.throws(() => ppmParameters(mz, 0.1, F32), /ppm bound/)
  const wide = encodePipeline(mz, F64, [3, 1, grid]).blob
  const exact = encodePipeline(mz, F32, [2, 1]).blob
  assert.ok(zlibCompress(wide, 6).length < zlibCompress(exact, 6).length)
  const spec = { defaultArrayLength: mz.length, mz }
  assert.deepEqual(encodingPlan(spec, { compression: "zlib" })[0]!.encoding, [2, 1])
  assert.deepEqual(decodeToken(encodeSpectrum(spec)).mz, mz)
})

test("float32 ppm candidate when it passes decodes within bound", () => {
  const mz = Float32Array.of(100.5, 200.25, 300.125)
  const params = ppmParameters(mz, 0.1, F32)
  const { blob, fidelity } = encodePipeline(mz, F32, [3, 1, params])
  const decoded = decodePipeline(blob, F32, mz.length, [3, 1, params], fidelity)
  assert.ok(decoded instanceof Float32Array)
  for (let i = 0; i < mz.length; i++) assert.ok(Math.abs(decoded[i]! - mz[i]!) <= mz[i]! * 1e-7)
})

for (const ctor of [Float32Array, Float64Array]) {
  test(`log intensity candidate checks its relative bound in ${ctor.name}`, () => {
    const source = make(ctor, logNormal(5000, 9, 16))
    const tail = ctor === Float32Array ? F32 : F64
    const params = intensityParameters(source, 3600, tail)
    const { blob, fidelity } = encodePipeline(source, tail, [3, 1, params])
    const decoded = decodePipeline(blob, tail, source.length, [3, 1, params], fidelity)
    assert.ok(decoded instanceof ctor)
    for (let i = 0; i < source.length; i++) assert.ok(Math.abs(decoded[i]! - source[i]!) <= source[i]! * 2 * Math.expm1(0.5 / 3600))
  })
}

for (const ctor of [Float32Array, Float64Array]) for (const compression of ["raw", "zlib"] as const) {
  test(`default lossy profile preserves ${ctor.name} under ${compression}`, () => {
    const spec = { defaultArrayLength: 64, mz: make(ctor, mzValues()), intensity: make(ctor, countValues()), charge: Int32Array.from(countValues(64, 1), (v) => 1 + (v % 3)) }
    const decoded = decodeToken(encodeSpectrum(spec, { compression }))
    assert.ok(decoded.mz instanceof ctor && decoded.intensity instanceof ctor && decoded.charge instanceof Int32Array)
  })
}
