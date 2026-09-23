import assert from "node:assert/strict"
import test from "node:test"
import { encodingReport, fitToBudget, parsePeakList, formatPeakList, decodeToken, topN } from "../src/index.ts"

test("numeric custom names keep quality metrics paired with their descriptors", () => {
  const report = encodingReport({ defaultArrayLength: 2, mz: [200, 100], intensity: [2, 1],
    extraArrays: { "10": Int32Array.from([10, 11]), "2": Float32Array.from([2, 3]) } }, { lossless: true })
  assert.deepEqual(report.arrays.map(a => [a.key, a.accession, a.typeAccession]), [
    ["mz", "MS:1000514", "MS:1000523"], ["intensity", "MS:1000515", "MS:1000523"],
    ["10", "MS:1000786", "MS:1000519"], ["2", "MS:1000786", "MS:1000521"],
  ])
  assert.equal(report.allArraysExact, true)
})

test("peak selection preserves dtype and parallel-array alignment across numeric boundaries", () => {
  for (const Ctor of [Int32Array, Float32Array, Float64Array]) {
    const intensity = Ctor.from([-2147483648, 0, 2147483647, 2, 2, -1, -0])
    const mz = [3, 1, 2, 2, 1, 4, 1]
    const spec = { defaultArrayLength: mz.length, mz, intensity, extraArrays: { position: Int32Array.from(mz.keys()) } }
    // Independent bucket selection avoids reusing the implementation's comparator.
    const descending = [...new Set(intensity)].sort((a, b) => b - a)
    const ranked = descending.flatMap(value => [...intensity.keys()].filter(i => intensity[i] === value)
      .sort((a, b) => mz[a]! - mz[b]! || a - b))
    for (let n = 0; n < mz.length; n++) {
      const selected = topN(spec, n)
      const expected = ranked.slice(0, n).sort((a, b) => mz[a]! - mz[b]! || a - b)
      assert.deepEqual(Array.from(selected.extraArrays!.position!), expected)
      assert.ok(selected.intensity instanceof Ctor)
      assert.deepEqual(Array.from(selected.intensity!), expected.map(i => intensity[i]!))
    }
  }
})

test("quality measures sorted arrays and zero references", () => {
  const spec = { defaultArrayLength: 3, mz: [200.123456, 0, 100.123456], intensity: [-1, 0, 10],
    extraArrays: { score: Int32Array.from([1, 2, 3]) }, userParams: [{ name: "note", value: "hello" }] }
  const r = encodingReport(spec, { dropUserParams: true })
  assert.ok(r.arrays[0]!.maxErrorPpm! > 0 && r.arrays[0]!.maxErrorPpm! <= 0.1)
  assert.equal(r.arrays[0]!.zeroReferenceValues, 1)
  assert.equal(r.arrays[1]!.maxRelativeError, 0)
  assert.equal(r.arrays[2]!.exact, true)
  assert.equal(r.omittedUserParams, 1)
  assert.equal(decodeToken(r.token).userParams.length, 0)
  assert.equal(spec.userParams.length, 1)
  assert.equal(encodingReport(spec, { lossless: true }).allArraysExact, true)
  for (const mz of [[], [0, 0]]) assert.equal(encodingReport({ defaultArrayLength: mz.length, mz }).arrays[0]!.maxErrorPpm, null)
})

test("fit requires opt-in and counts carrier UTF-8 bytes", () => {
  const spec = { defaultArrayLength: 100, mz: Array.from({ length: 100 }, (_, i) => i * 1.2345),
    intensity: Array.from({ length: 100 }, (_, i) => i), extraArrays: { score: Int32Array.from({ length: 100 }, (_, i) => i) } }
  assert.throws(() => fitToBudget(spec, 500))
  const r = fitToBudget(spec, 500, { baseUrl: "https://example.org/é#old", allowPeakTrimming: true })
  assert.ok(r.carrierBytes <= 500)
  assert.equal(r.carrierBytes, new TextEncoder().encode(r.carrier).length)
  assert.ok(r.keptPeaks > 0 && r.keptPeaks < 100)
  assert.deepEqual(Array.from(decodeToken(r.token).extraArrays.score!), Array.from({ length: r.keptPeaks }, (_, i) => 100 - r.keptPeaks + i))
  assert.equal(spec.defaultArrayLength, 100)
  assert.throws(() => fitToBudget(spec, 1, { allowPeakTrimming: true }))
})

test("metadata removal is explicit and visible", () => {
  const source = { defaultArrayLength: 1, mz: [100], intensity: [42], userParams: [{ name: "note" }] }
  const r = fitToBudget(source, 1000, { dropUserParams: true })
  assert.equal(r.omittedUserParams, 1)
  assert.deepEqual(r.spectrum.userParams, [])
  assert.equal(source.userParams.length, 1)
})

for (const text of ['mz,intensity\n100.5,2\n200,-3', '# comment\nm/z\tintensity\n100.5\t2\n200\t-3',
  '\uFEFF100.5 2\n\n200 -3', '"mz","intensity"\n"100.5","2"\n"200","-3"']) test(`peak list ${JSON.stringify(text)}`, () => {
  const s = parsePeakList(text)
  assert.deepEqual(s.mz, [100.5, 200])
  assert.deepEqual(s.intensity, [2, -3])
  assert.deepEqual(parsePeakList(formatPeakList(s)), s)
})
for (const text of ["", "mz,intensity", "1,2,3", "1,", "-1,2", "nan,2", "1e999,2", "1,2\n3,4,5"]) test(`reject peak list ${text}`, () => {
  assert.throws(() => parsePeakList(text))
})
