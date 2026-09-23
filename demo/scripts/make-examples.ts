/** Write the small example files the Convert page offers for download.
 *
 * The spectra are the demo's own examples, written with the library's format
 * writers so that what a visitor downloads is exactly what the converter can
 * read back. Run with `npm run examples`; the output is committed so the
 * static site needs no build step to serve it. */
import { writeFileSync } from "node:fs"
import { decodeToken, encodeSpectrum, write, type DecodedSpectrum } from "../../js/dist/index.js"
import { peptideMs2, smallMoleculeMs1 } from "../src/examples.js"

const decoded = (spectrum: ReturnType<typeof peptideMs2>): DecodedSpectrum =>
  decodeToken(encodeSpectrum(spectrum, { lossless: true, quiet: true }))

// One MS1 and two MS2 scans, so the mzML lists both levels and the MGF and
// MS2 files, which hold only fragmentation spectra, still hold two entries.
const spectra = [decoded(smallMoleculeMs1()), decoded(peptideMs2("PEPTIDER", 1042)), decoded(peptideMs2("LVNELTEFAK", 1043))]
const ms2Only = spectra.slice(1)

/** The mzML writer emits one spectrum per document. The documents share a
 * scaffold when the spectra carry no source or processing records, so the
 * spectrum elements can be collected into one spectrumList. */
function mergeMzml(docs: string[]): string {
  const pattern = /<spectrumList count="1"( [^>]*)?>\n?([\s\S]*?)<\/spectrumList>/
  const shells = docs.map(doc => doc.replace(pattern, "<spectrumList/>"))
  if (new Set(shells).size !== 1) throw Error("example spectra produced different mzML scaffolds")
  const elements = docs.map((doc, index) => {
    const match = pattern.exec(doc)
    if (!match) throw Error("mzML writer output did not contain a spectrumList")
    return match[2]!.trim().replace('index="0"', `index="${index}"`)
  })
  const [first] = docs
  const match = pattern.exec(first!)!
  return first!.replace(pattern,
    `<spectrumList count="${docs.length}"${match[1] ?? ""}>\n      ${elements.join("\n      ")}\n    </spectrumList>`)
}

const mzml = mergeMzml(spectra.map(s => write(s, "mzml").text))
const mgf = ms2Only.map(s => write(s, "mgf").text).join("\n")
// Every MS2 document starts with H lines; only the first set belongs in a file.
const ms2 = ms2Only.map((s, i) => {
  const text = write(s, "ms2").text
  return i === 0 ? text : text.split("\n").filter(line => !line.startsWith("H")).join("\n")
}).join("")

const files: Array<[string, string]> = [["example.mzML", mzml], ["example.mgf", mgf], ["example.ms2", ms2]]
for (const [name, text] of files) {
  writeFileSync(`examples/${name}`, text)
  console.log(`${name}: ${text.length} bytes`)
}
