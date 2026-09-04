import assert from "node:assert/strict"
import test from "node:test"
import { encodingReport, fitToBudget, parsePeakList, formatPeakList, decodeToken } from "../src/index.ts"

test("quality measures sorted arrays and zero references", () => {
  const spec = { defaultArrayLength: 3, mz: [200.123456, 0, 100.123456], intensity: [-1, 0, 10],
    extraArrays: { score: Int32Array.from([1, 2, 3]) }, userParams: [{ name: "note", value: "hello" }] }
  const r = encodingReport(spec, { dropUserParams: true })
  assert.ok(r.arrays[0]!.maxAbsoluteError! > 0 && r.arrays[0]!.maxAbsoluteError! < 1e-5)
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
  assert.throws(() => fitToBudget(spec, 250))
  const r = fitToBudget(spec, 250, { baseUrl: "https://example.org/é#old", allowPeakTrimming: true })
  assert.ok(r.carrierBytes <= 250)
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
