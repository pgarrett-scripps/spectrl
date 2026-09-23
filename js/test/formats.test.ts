import test from "node:test"
import assert from "node:assert/strict"
import { decodeToken, encodeSpectrum } from "../src/index.ts"
import { FORMATS, formatForPath, readMgf, readMs2, write, writeMgf, writeMs2, writeMzml } from "../src/formats/index.ts"
import { num } from "../src/formats/peaklist_formats.ts"
import type { InlineSpectrum } from "../src/model.ts"

function ms2Spectrum(): InlineSpectrum {
  return {
    defaultArrayLength: 3,
    mz: Float64Array.from([100.5, 200.25, 300.125]),
    intensity: Float64Array.from([10, 20.5, 30]),
    id: "scan=42",
    params: [{ accession: "MS:1000511", value: 2 }],
    scans: [{ params: [{ accession: "MS:1000016", value: 5.5, unitAccession: "UO:0000031" }], windows: [] }],
    precursors: [{
      isolationWindow: null, activation: null,
      selectedIons: [{ params: [{ accession: "MS:1000744", value: 445.25 }, { accession: "MS:1000041", value: 2 }] }],
    }],
  } as unknown as InlineSpectrum
}

const decoded = () => decodeToken(encodeSpectrum(ms2Spectrum(), { lossless: true }))

test("the format is inferred from the suffix", () => {
  for (const [name, expected] of [["run.mzML", "mzml"], ["x.MGF", "mgf"], ["a.ms2", "ms2"], ["b.mzml.gz", "mzml"]]) {
    assert.equal(formatForPath(name!), expected)
  }
  assert.throws(() => formatForPath("spectrum.txt"), /known suffixes: \.mgf, \.ms2, \.mzml/)
})

test("numbers are written the way CPython's repr does", () => {
  // JavaScript would give 0.00001, 4.568343001665198e-7 and 100000000000000000000.
  assert.equal(num(1e-5), "1e-05")
  assert.equal(num(4.568343001665198e-7), "4.568343001665198e-07")
  assert.equal(num(1e-4), "0.0001")
  assert.equal(num(1e15), "1000000000000000.0")
  assert.equal(num(1e16), "1e+16")
  assert.equal(num(100), "100.0")
  assert.equal(num(0), "0.0")
  assert.equal(num(-0), "-0.0")
  assert.equal(num(1 / 3), "0.3333333333333333")
})

test("mgf round-trips peaks and the precursor", () => {
  const result = writeMgf(decoded())
  assert.match(result.text, /PEPMASS=445.25/)
  assert.match(result.text, /CHARGE=2\+/)
  assert.match(result.text, /RTINSECONDS=330.0/)
  const back = readMgf(result.text)
  assert.equal(back.length, 1)
  assert.deepEqual(Array.from(back[0]!.mz as Float64Array), [100.5, 200.25, 300.125])
  const ion = back[0]!.precursors![0]!.selectedIons![0]!.params!
  assert.equal(ion[0]!.value, 445.25)
  assert.equal(ion[1]!.value, 2)
})

test("ms2 round-trips peaks and the precursor", () => {
  const result = writeMs2(decoded())
  assert.match(result.text, /\nS\t42\t42\t445.25/)
  assert.match(result.text, /\nZ\t2\t/)
  const back = readMs2(result.text)
  assert.equal(back.length, 1)
  assert.equal(back[0]!.precursors![0]!.selectedIons![0]!.params![0]!.value, 445.25)
})

test("peak-list formats report what they drop", () => {
  const spectrum = ms2Spectrum() as unknown as Record<string, unknown>
  spectrum.acquisition = { instrument: { id: "IC1" } }
  const result = writeMgf(decodeToken(encodeSpectrum(spectrum as unknown as InlineSpectrum, { lossless: true })))
  assert.equal(result.lossless, false)
  assert.match(result.summary(), /^Not represented by MGF:/)
  assert.ok(result.omitted.some(m => m.includes("acquisition")))
})

test("an MS1 spectrum is written without PEPMASS and reported", () => {
  const spectrum = {
    defaultArrayLength: 2,
    mz: Float64Array.from([100, 200]),
    intensity: Float64Array.from([1, 2]),
    params: [{ accession: "MS:1000511", value: 1 }],
  } as unknown as InlineSpectrum
  const result = writeMgf(decodeToken(encodeSpectrum(spectrum, { lossless: true })))
  assert.ok(!result.text.includes("PEPMASS"))
  assert.match(result.text, /BEGIN IONS/)
  assert.ok(result.issues.some(i => i.code === "no_precursor"))
})

test("mzML is a complete document and reports a synthesized id", () => {
  const spectrum = {
    defaultArrayLength: 1, mz: Float64Array.from([100]), intensity: Float64Array.from([1]),
  } as unknown as InlineSpectrum
  const result = writeMzml(decodeToken(encodeSpectrum(spectrum, { lossless: true })))
  for (const required of ["cvList", "fileDescription", "softwareList", "instrumentConfigurationList",
                          "dataProcessingList", "run", "spectrumList"]) {
    assert.match(result.text, new RegExp(`<${required}`), `mzML must contain ${required}`)
  }
  assert.ok(result.issues.some(i => i.code === "synthesized_id"))
})

test("colliding identifiers become unique XML ids", () => {
  const spectrum = {
    defaultArrayLength: 1, mz: Float64Array.from([100]), intensity: Float64Array.from([1]), id: "scan=1",
    source: { id: "SHARED", name: "run.raw" },
    acquisition: { instrument: { id: "IC1", software: { id: "SHARED", version: "1" } } },
  } as unknown as InlineSpectrum
  const result = writeMzml(decodeToken(encodeSpectrum(spectrum, { lossless: true })))
  const ids = [...result.text.matchAll(/\sid="([^"]+)"/g)].map(m => m[1])
  assert.equal(ids.length, new Set(ids).size, `duplicate xs:ID in ${ids.join(", ")}`)
  assert.ok(result.issues.some(i => i.code === "id_deduplicated"))
})

test("a Windows file URI is repaired", () => {
  const spectrum = {
    defaultArrayLength: 1, mz: Float64Array.from([100]), intensity: Float64Array.from([1]),
    source: { id: "s", location: "file://F:/data/Exp01" },
  } as unknown as InlineSpectrum
  const result = writeMzml(decodeToken(encodeSpectrum(spectrum, { lossless: true })))
  assert.match(result.text, /location="file:\/\/\/F:\/data\/Exp01"/)
  assert.ok(result.issues.some(i => i.code === "location_uri_normalized"))
})

test("write dispatches every declared format", () => {
  for (const format of FORMATS) {
    const result = write(decoded(), format)
    assert.equal(result.format, format)
    assert.ok(result.text.trim().length)
  }
  assert.throws(() => write(decoded(), "mzxml" as never), /unknown output format/)
})

test("malformed peak lists are rejected with a line number", () => {
  assert.throws(() => readMgf("BEGIN IONS\n100 1\n"), /unterminated/)
  assert.throws(() => readMgf("END IONS\n"), /END IONS without BEGIN IONS/)
  assert.throws(() => readMgf("BEGIN IONS\nTITLE=x\nnot a peak\nEND IONS\n"), /line 3/)
})

test("reading mzML without a DOM says what to use instead", async () => {
  const { readMzml } = await import("../src/formats/mzml_reader.ts")
  assert.throws(() => readMzml("<mzML/>"), /DOMParser|spectrl CLI/)
})

test("a scan-level instrument alone still sets the run's required default", () => {
  const spectrum = ms2Spectrum()
  ;(spectrum.scans![0] as { acquisition?: unknown }).acquisition = { instrument: { id: "IC1" } }
  const text = writeMzml(decodeToken(encodeSpectrum(spectrum, { lossless: true }))).text
  assert.match(text, /<run [^>]*defaultInstrumentConfigurationRef="IC1"/)
})
