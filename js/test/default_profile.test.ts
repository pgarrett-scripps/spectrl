import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { decodeToken, encodeSpectrum, encodingPlan } from "../src/index.ts"
import { arraySize, defaultArray, defaultCandidates } from "../src/canonical.ts"
import { encodePipeline } from "../src/pipeline.ts"
import type { PayloadCompression } from "../src/payload.ts"

const F32 = 1000521, F64 = 1000523
const inputs = JSON.parse(readFileSync(new URL("../../test-vectors/token-parity-inputs.json", import.meta.url), "utf8"))
const list = Array.isArray(inputs) ? inputs : inputs.inputs
const tinyMinimum = Float32Array.from(list.find((x: { name: string }) => x.name === "profile-tiny-minimum").spec.intensity as number[])
const mzFor = (n: number) => Float64Array.from({ length: n }, (_, i) => 400 + (1000 * i) / 63)
const intensityPlan = (intensity: Float32Array | Float64Array, compression: PayloadCompression) =>
  encodingPlan({ defaultArrayLength: intensity.length, mz: mzFor(intensity.length), intensity }, { compression })[1]!

test("integer counts choose exact scale-one words", () => {
  const counts = Float64Array.from(Array.from({ length: 4 }, () => [0, 1, 2, 5, 18, 42, 91, 250, 1000, 3, 0, 7]).flat())
  for (const compression of ["raw", "zlib"] as const) {
    assert.deepEqual(intensityPlan(counts, compression).encoding, [3, 1, { scale: 1, width: 2 }])
    const spec = { defaultArrayLength: counts.length, mz: mzFor(counts.length), intensity: counts }
    assert.deepEqual([...decodeToken(encodeSpectrum(spec, { compression })).intensity!], [...counts])
  }
})

test("candidate order and integer gate", () => {
  const kinds = (key: string, a: Float64Array, lossless = false) =>
    defaultCandidates(key, a, lossless, 5, 3600).map(([, make]) => make()[0])
  assert.deepEqual(kinds("intensity", Float64Array.of(1.5, 2, 3)), [1, 4, 3])
  assert.deepEqual(kinds("intensity", Float64Array.of(1, 2, 2 ** 53 - 1)), [1, 3, 4, 3])
  assert.deepEqual(kinds("intensity", Float64Array.of(1, 2 ** 53)), [1, 4, 3])
  assert.deepEqual(kinds("mz", mzFor(64)), [2, 3])
  assert.deepEqual(kinds("intensity", Float64Array.of(1.5), true), [1])
  assert.deepEqual(kinds("intensity", Float64Array.of(-1.5)), [1])
})

for (const compression of ["raw", "zlib"] as const) {
  test(`tiny minimum never larger than lossless (${compression})`, () => {
    const { result } = defaultArray("intensity", tinyMinimum, false, 5, 3600, compression)
    const exact = new Uint8Array(tinyMinimum.buffer.slice(0))
    assert.ok(arraySize(result.blob, compression) <= arraySize(exact, compression))
  })
}

test("tie keeps the exact candidate; raw and zlib measure differently", () => {
  assert.deepEqual(intensityPlan(tinyMinimum, "raw").encoding, [1, 1])
  assert.equal((intensityPlan(tinyMinimum, "zlib").encoding as number[])[0], 4)
})

test("default never exceeds the exact candidate", () => {
  let state = 11
  const random = () => (state = (state * 1103515245 + 12345) % 2 ** 31) / 2 ** 31
  for (let seed = 0; seed < 40; seed++) for (const compression of ["raw", "zlib"] as const) {
    const n = 1 + Math.floor(random() * 199)
    const raw = Array.from({ length: n }, () => Math.exp((random() - 0.3) * (seed % 4 === 2 ? 60 : 12)))
    const a = seed % 4 === 1 ? Float64Array.from(raw, Math.floor) : seed % 4 === 3 ? Float32Array.from(raw) : Float64Array.from(raw)
    const mz = Float64Array.from(Array.from({ length: n }, () => 100 + random() * 1900).sort((x, y) => x - y))
    for (const [key, array, exactEnc] of [["intensity", a, 1], ["mz", mz, 2]] as const) {
      const type = array instanceof Float32Array ? F32 : F64
      const exact = arraySize(encodePipeline(array, type, [exactEnc, 1]).blob, compression)
      const chosen = defaultArray(key, array, false, 5, 3600, compression)
      assert.ok(arraySize(chosen.result.blob, compression) <= exact)
    }
  }
})
