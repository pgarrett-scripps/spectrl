/** Convert one spectrum between a spectrl token and common spectrum files.
 *
 * mzML is the interchange format: it carries everything a token does, and a
 * token written to mzML and read back is the same spectrum. MGF and MS2 hold a
 * precursor and peaks, so writing to them drops most of a token's context.
 * Nothing is dropped silently: every writer returns a ConversionResult listing
 * what the target could not represent.
 *
 * Reading a multi-spectrum file yields every spectrum and the caller chooses.
 * Requiring a single-spectrum file would be the wrong trade, since ordinary
 * runs hold thousands. */

import type { DecodedSpectrum, InlineSpectrum } from "../model.js"
import { writeMzml, type WriteMzmlOptions } from "./mzml.js"
import { listMzmlSpectra, readMzml, type ReadMzmlOptions, type SpectrumSummary } from "./mzml_reader.js"
import { readMgf, readMs2, writeMgf, writeMs2 } from "./peaklist_formats.js"
import { ConversionResult } from "./report.js"

export { ConversionResult, listMzmlSpectra, readMgf, readMs2, readMzml, writeMgf, writeMs2, writeMzml }
export type { ConversionIssue, Severity } from "./report.js"
export type { ReadMzmlOptions, SpectrumSummary, WriteMzmlOptions }

export const FORMATS = ["mzml", "mgf", "ms2"] as const
export type SpectrumFormat = (typeof FORMATS)[number]

const SUFFIXES: Record<string, SpectrumFormat> = { mzml: "mzml", mgf: "mgf", ms2: "ms2" }

/** The format a filename implies, ignoring a trailing .gz. */
export function formatForPath(path: string): SpectrumFormat {
  let name = path.split(/[\\/]/).pop()!.toLowerCase()
  if (name.endsWith(".gz")) name = name.slice(0, -3)
  const suffix = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1) : ""
  const format = SUFFIXES[suffix]
  if (!format) {
    throw Error(`cannot infer a spectrum format from ${JSON.stringify(path.split(/[\\/]/).pop())}; ` +
      `known suffixes: .mgf, .ms2, .mzml`)
  }
  return format
}

/** Write one decoded spectrum in the named format. */
export function write(spectrum: DecodedSpectrum, format: SpectrumFormat, opts: WriteMzmlOptions = {}): ConversionResult {
  if (format === "mzml") return writeMzml(spectrum, opts)
  if (format === "mgf") return writeMgf(spectrum)
  if (format === "ms2") return writeMs2(spectrum)
  throw Error(`unknown output format ${JSON.stringify(format)}; expected one of ${FORMATS.join(", ")}`)
}

export interface ReadTextOptions {
  index?: number
  id?: string
}

/** Read spectra from the text of any supported format. */
export function readText(text: string, format: SpectrumFormat, opts: ReadTextOptions = {}): InlineSpectrum[] {
  if (format === "mzml") return readMzml(text, opts as ReadMzmlOptions)
  const spectra = format === "mgf" ? readMgf(text) : readMs2(text)
  if (opts.id !== undefined) {
    const matched = spectra.filter(s => s.id === opts.id)
    if (!matched.length) throw Error(`no spectrum with id ${JSON.stringify(opts.id)}`)
    return matched.slice(0, 1)
  }
  if (opts.index !== undefined) {
    const picked = spectra[opts.index]
    if (!picked) throw Error(`this file holds ${spectra.length} spectra; index ${opts.index} is out of range`)
    return [picked]
  }
  return spectra
}

/** Every spectrum in a file, as a list a person can choose from. */
export function listSpectra(text: string, format: SpectrumFormat): SpectrumSummary[] {
  if (format === "mzml") return listMzmlSpectra(text)
  return readText(text, format).map((spectrum, index) => {
    const level = spectrum.params?.find(p => p.accession === "MS:1000511")?.value
    const ion = spectrum.precursors?.[0]?.selectedIons?.[0]?.params
      ?.find(p => p.accession === "MS:1000744")?.value
    const rt = spectrum.scans?.[0]?.params?.find(p => p.accession === "MS:1000016")?.value
    return {
      index,
      id: spectrum.id ?? `index=${index}`,
      msLevel: level == null ? null : Number(level),
      precursorMz: ion == null ? null : Number(ion),
      retentionSeconds: rt == null ? null : Number(rt),
      peaks: spectrum.defaultArrayLength,
    }
  })
}
