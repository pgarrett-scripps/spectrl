/** MGF and MS2: peak lists with a small precursor header.
 *
 * Both describe one fragmentation spectrum -- a precursor m/z, usually a
 * charge, sometimes a retention time, then peaks. Everything else a token holds
 * has nowhere to go, so the writers report it. Neither format has a
 * specification in the sense mzML does: MGF is what Mascot accepts and MS2 is
 * what its readers parse, so these emit the common subset tools agree on and
 * accept the variations seen in practice.
 *
 * Mirrors src/spectrl/formats/_peaklist_formats.py. */

import type { CvParam, DecodedSpectrum, InlineSpectrum } from "../model.js"
import { ConversionResult } from "./report.js"

export const SELECTED_ION_MZ = "MS:1000744"
export const CHARGE_STATE = "MS:1000041"
export const PEAK_INTENSITY = "MS:1000042"
export const SCAN_START_TIME = "MS:1000016"
export const MS_LEVEL = "MS:1000511"
const UO_SECOND = "UO:0000010"
const UO_MINUTE = "UO:0000031"
const PROTON = 1.00727646677

type Precursor = { mz: number, charge: number | null, intensity: number | null }

function find(params: CvParam[] | undefined, accession: string): unknown {
  for (const p of params ?? []) if (p.accession === accession) return p.value
  return null
}

function precursorOf(spectrum: DecodedSpectrum): Precursor | null {
  for (const precursor of spectrum.precursors ?? []) {
    for (const ion of precursor.selectedIons ?? []) {
      const mz = find(ion.params, SELECTED_ION_MZ)
      if (mz != null) {
        const charge = find(ion.params, CHARGE_STATE)
        const intensity = find(ion.params, PEAK_INTENSITY)
        return {
          mz: Number(mz),
          charge: charge == null ? null : Number(charge),
          intensity: intensity == null ? null : Number(intensity),
        }
      }
    }
  }
  return null
}

/** Scan start time in seconds; mzML records minutes as often as seconds. */
function retentionSeconds(spectrum: DecodedSpectrum): number | null {
  for (const scan of spectrum.scans ?? []) {
    for (const p of scan.params ?? []) {
      if (p.accession === SCAN_START_TIME && p.value != null) {
        const value = Number(p.value)
        return p.unitAccession === UO_MINUTE ? value * 60 : value
      }
    }
  }
  return null
}

/** Report what a precursor-plus-peaks format cannot represent. */
function inventory(spectrum: DecodedSpectrum, result: ConversionResult): void {
  const checks: [unknown, string, string][] = [
    [spectrum.acquisition, "acquisition", "acquisition context (instrument and components)"],
    [spectrum.processing, "processing", "processing history"],
    [spectrum.source, "source", "source file metadata"],
    [spectrum.products, "products", "product ion selection"],
    [spectrum.extensions, "extensions", "spectrum extensions"],
    [spectrum.arrayExtensions, "array_extensions", "array extensions"],
    [spectrum.cvVersions, "cv_versions", "ontology version provenance"],
    [spectrum.userParams, "user_params", "spectrum user parameters"],
  ]
  for (const [value, path, description] of checks) {
    const present = Array.isArray(value) ? value.length > 0 : value && Object.keys(value).length > 0
    if (present) result.add("dropped", path, description)
  }
  const extra = Object.keys(spectrum.extraArrays ?? {})
  if (extra.length) result.add("dropped", "extra_arrays", `additional arrays (${extra.sort().join(", ")})`)
  if (spectrum.charge != null) result.add("dropped", "charge", "per-peak charge array")
  if ((spectrum.scans ?? []).some(s => s.windows?.length)) result.add("dropped", "scans.windows", "scan windows")
  const extras = [...new Set((spectrum.params ?? []).map(p => p.accession))].filter(a => a !== MS_LEVEL).sort()
  if (extras.length) {
    result.add("dropped", "params", `${extras.length} spectrum CV parameter(s), including ${extras[0]}`)
  }
}

/** Shortest round-trippable form, matching CPython's repr(float).
 *
 * Both languages print the shortest digits that round-trip, but they disagree
 * on when to switch to scientific notation and how to spell the exponent.
 * CPython goes exponential once the decimal point would sit at or before the
 * fourth leading zero, or past the sixteenth digit, and always writes at least
 * two exponent digits: 1e-05, not 0.00001; 4.5e-07, not 4.5e-7. JavaScript
 * switches at 1e-7 and pads nothing, so the two writers would otherwise emit
 * different text for the same value. */
export function num(value: number): string {
  if (!Number.isFinite(value)) throw Error(`cannot write a non-finite value: ${value}`)
  if (value === 0) return Object.is(value, -0) ? "-0.0" : "0.0"
  const parsed = /^(-?)(\d)(?:\.(\d+))?e([+-]\d+)$/.exec(value.toExponential())
  if (!parsed) throw Error(`unexpected number form: ${value}`)
  const [, sign, first, rest = "", exponentText] = parsed
  const exponent = Number(exponentText)
  const digits = first! + rest
  if (exponent <= -5 || exponent >= 16) {
    const mantissa = rest ? `${first}.${rest}` : first!
    const magnitude = String(Math.abs(exponent)).padStart(2, "0")
    return `${sign}${mantissa}e${exponent < 0 ? "-" : "+"}${magnitude}`
  }
  if (exponent >= 0) {
    if (digits.length <= exponent + 1) return `${sign}${digits.padEnd(exponent + 1, "0")}.0`
    return `${sign}${digits.slice(0, exponent + 1)}.${digits.slice(exponent + 1)}`
  }
  return `${sign}0.${"0".repeat(-exponent - 1)}${digits}`
}

function* peaks(spectrum: DecodedSpectrum): Generator<[number, number]> {
  const mz = spectrum.mz ?? []
  const intensity = spectrum.intensity ?? []
  const n = Math.min(mz.length, intensity.length)
  for (let i = 0; i < n; i++) yield [mz[i]!, intensity[i]!]
}

export function writeMgf(spectrum: DecodedSpectrum, opts: { title?: string } = {}): ConversionResult {
  const result = new ConversionResult("mgf")
  inventory(spectrum, result)
  const precursor = precursorOf(spectrum)
  const lines = ["BEGIN IONS", `TITLE=${opts.title || spectrum.id || "spectrl"}`]
  if (precursor === null) {
    result.add("no_precursor", "precursors",
      "no precursor ion, so no PEPMASS was written; most MGF readers expect one")
  } else {
    lines.push(`PEPMASS=${num(precursor.mz)}` + (precursor.intensity != null ? ` ${num(precursor.intensity)}` : ""))
    if (precursor.charge != null) {
      lines.push(`CHARGE=${Math.abs(precursor.charge)}${precursor.charge >= 0 ? "+" : "-"}`)
    }
  }
  const seconds = retentionSeconds(spectrum)
  if (seconds != null) lines.push(`RTINSECONDS=${num(seconds)}`)
  for (const [mz, intensity] of peaks(spectrum)) lines.push(`${num(mz)} ${num(intensity)}`)
  lines.push("END IONS")
  result.text = lines.join("\n") + "\n"
  return result
}

function scanNumber(id: string | null): number {
  if (id) {
    const match = /scan=(\d+)/.exec(id) ?? /(\d+)\s*$/.exec(id)
    if (match) return Number(match[1])
  }
  return 0
}

export function writeMs2(spectrum: DecodedSpectrum, opts: { scan?: number } = {}): ConversionResult {
  const result = new ConversionResult("ms2")
  inventory(spectrum, result)
  const precursor = precursorOf(spectrum)
  const number = opts.scan ?? scanNumber(spectrum.id)
  const lines = ["H\tCreationDate\t", "H\tExtractor\tspectrl"]
  if (precursor === null) {
    result.add("no_precursor", "precursors",
      "no precursor ion; the MS2 S line requires a precursor m/z, so 0 was written")
    lines.push(`S\t${number}\t${number}\t0`)
  } else {
    lines.push(`S\t${number}\t${number}\t${num(precursor.mz)}`)
    const seconds = retentionSeconds(spectrum)
    if (seconds != null) lines.push(`I\tRTime\t${num(seconds / 60)}`)
    if (precursor.charge != null) {
      const state = Math.abs(precursor.charge) || 1
      // The Z line's mass is the singly-protonated neutral mass.
      lines.push(`Z\t${state}\t${num(precursor.mz * state - (state - 1) * PROTON)}`)
    }
  }
  for (const [mz, intensity] of peaks(spectrum)) lines.push(`${num(mz)} ${num(intensity)}`)
  result.text = lines.join("\n") + "\n"
  return result
}

function spectrumFrom(
  mz: number[], intensity: number[],
  o: { id?: string | null, msLevel: number, precursor: Precursor | null, retentionSeconds: number | null },
): InlineSpectrum {
  const params: CvParam[] = [{ accession: MS_LEVEL, value: o.msLevel }]
  const scans = o.retentionSeconds == null ? [] : [{
    params: [{ accession: SCAN_START_TIME, value: o.retentionSeconds, unitAccession: UO_SECOND }],
    windows: [], userParams: [],
  }]
  const precursors = []
  if (o.precursor) {
    const ion: CvParam[] = [{ accession: SELECTED_ION_MZ, value: o.precursor.mz }]
    if (o.precursor.charge != null) ion.push({ accession: CHARGE_STATE, value: o.precursor.charge })
    if (o.precursor.intensity != null) ion.push({ accession: PEAK_INTENSITY, value: o.precursor.intensity })
    precursors.push({
      isolationWindow: null, activation: null,
      selectedIons: [{ params: ion, userParams: [] }],
    })
  }
  return {
    defaultArrayLength: mz.length,
    mz: Float64Array.from(mz),
    intensity: Float64Array.from(intensity),
    id: o.id ?? null,
    params, scans, precursors,
  } as InlineSpectrum
}

function peakLine(line: string, number: number, where: string): [number, number] {
  const parts = line.split(/\s+/).filter(Boolean)
  if (parts.length < 2) throw Error(`${where} line ${number}: expected 'mz intensity', got ${JSON.stringify(line)}`)
  const mz = Number(parts[0]), intensity = Number(parts[1])
  if (!Number.isFinite(mz) || !Number.isFinite(intensity)) {
    throw Error(`${where} line ${number}: peak values must be finite numbers, got ${JSON.stringify(line)}`)
  }
  return [mz, intensity]
}

/** MGF writes 2+, +2, or 2; a list like "2+ and 3+" is genuinely ambiguous. */
function parseCharge(text: string): number | null {
  const token = text.trim().split(/\s+/)[0] ?? ""
  const match = /^([+-]?\d+)([+-]?)$/.exec(token)
  if (!match) return null
  const value = Math.abs(Number(match[1]))
  return match[2] === "-" ? -value : value
}

export function readMgf(text: string): InlineSpectrum[] {
  const spectra: InlineSpectrum[] = []
  let header: Record<string, string> = {}
  let mz: number[] = [], intensity: number[] = []
  let inside = false
  let number = 0
  for (const raw of text.split(/\r\n|\r|\n/)) {
    number++
    const line = raw.trim()
    if (!line || "#;!".includes(line[0]!)) continue
    const upper = line.toUpperCase()
    if (upper === "BEGIN IONS") {
      if (inside) throw Error(`MGF line ${number}: BEGIN IONS inside an open block`)
      inside = true; header = {}; mz = []; intensity = []
      continue
    }
    if (upper === "END IONS") {
      if (!inside) throw Error(`MGF line ${number}: END IONS without BEGIN IONS`)
      spectra.push(fromMgfBlock(header, mz, intensity))
      inside = false
      continue
    }
    if (!inside) continue // Parameters before the first block configure search, not peaks.
    if (line.includes("=") && !/^\d/.test(line)) {
      const at = line.indexOf("=")
      header[line.slice(0, at).trim().toUpperCase()] = line.slice(at + 1).trim()
      continue
    }
    const [a, b] = peakLine(line, number, "MGF")
    mz.push(a); intensity.push(b)
  }
  if (inside) throw Error("MGF ended inside an unterminated BEGIN IONS block")
  return spectra
}

function fromMgfBlock(header: Record<string, string>, mz: number[], intensity: number[]): InlineSpectrum {
  let precursor: Precursor | null = null
  if (header.PEPMASS) {
    const parts = header.PEPMASS.split(/\s+/).filter(Boolean)
    precursor = {
      mz: Number(parts[0]),
      charge: header.CHARGE ? parseCharge(header.CHARGE) : null,
      intensity: parts.length > 1 ? Number(parts[1]) : null,
    }
  }
  const rt = header.RTINSECONDS ? Number(header.RTINSECONDS.split(/\s+/)[0]) : null
  // MGF describes fragmentation, so a block without a precursor is still read
  // as MS2 rather than guessed at.
  return spectrumFrom(mz, intensity, { id: header.TITLE ?? null, msLevel: 2, precursor, retentionSeconds: rt })
}

export function readMs2(text: string): InlineSpectrum[] {
  const spectra: InlineSpectrum[] = []
  let current: { scan: string, precursor: Precursor | null, rtime: number | null } | null = null
  let mz: number[] = [], intensity: number[] = []
  let number = 0
  const flush = () => {
    if (current) {
      spectra.push(spectrumFrom(mz, intensity, {
        id: current.scan ? `scan=${current.scan}` : null,
        msLevel: 2, precursor: current.precursor, retentionSeconds: current.rtime,
      }))
    }
  }
  for (const raw of text.split(/\r\n|\r|\n/)) {
    number++
    const line = raw.replace(/\s+$/, "")
    if (!line) continue
    const kind = line[0]!
    if (kind === "H") continue
    if (kind === "S") {
      flush()
      const parts = line.split(/\s+/).filter(Boolean)
      if (parts.length < 4) throw Error(`MS2 line ${number}: S line needs scan, scan and precursor m/z`)
      const precursorMz = Number(parts[3])
      if (Number.isNaN(precursorMz)) throw Error(`MS2 line ${number}: precursor m/z is not a number: ${JSON.stringify(parts[3])}`)
      current = { scan: parts[1]!, precursor: precursorMz ? { mz: precursorMz, charge: null, intensity: null } : null, rtime: null }
      mz = []; intensity = []
      continue
    }
    if (!current) continue
    if (kind === "I") {
      const parts = line.split(/\s+/).filter(Boolean)
      if (parts.length >= 3 && parts[1]!.toUpperCase() === "RTIME") current.rtime = Number(parts[2]) * 60
      continue
    }
    if (kind === "Z") {
      const parts = line.split(/\s+/).filter(Boolean)
      if (parts.length >= 2 && current.precursor) current.precursor.charge = Math.trunc(Number(parts[1]))
      continue
    }
    if (kind === "D") continue
    const [a, b] = peakLine(line, number, "MS2")
    mz.push(a); intensity.push(b)
  }
  flush()
  return spectra
}
