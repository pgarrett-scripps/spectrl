/** Two-column peak-list import and export. No metadata is inferred. */
import { MAX_ARRAY_LENGTH } from "./format.js"
import { validateArrays } from "./canonical.js"
import type { InlineSpectrum } from "./model.js"

const NUMBER = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/
export type PeakDelimiter = "," | "\t" | " "

export function parsePeakList(text: string, delimiter?: PeakDelimiter): InlineSpectrum {
  if (delimiter !== undefined && ![",", "\t", " "].includes(delimiter)) throw new Error("invalid delimiter")
  const mz: number[] = []
  const intensity: number[] = []
  let first = true
  let chosen = delimiter
  for (const [index, raw] of text.replace(/^\uFEFF/, "").split(/\r\n|\n|\r/).entries()) {
    const line = raw.trim()
    if (!line || line.startsWith("#")) continue
    chosen ??= line.includes(",") ? "," : line.includes("\t") ? "\t" : " "
    const row = (chosen === " " ? line.split(/\s+/) : line.split(chosen)).map(value => {
      const trimmed = value.trim()
      return /^"[^"]*"$/.test(trimmed) ? trimmed.slice(1, -1) : trimmed
    })
    if (first && row.length === 2 && ["mz", "m/z"].includes(row[0]!.toLowerCase()) && row[1]!.toLowerCase() === "intensity") {
      first = false
      continue
    }
    first = false
    if (row.length !== 2 || row.some(v => !NUMBER.test(v))) throw new Error(`line ${index + 1}: expected exactly two numeric columns: m/z and intensity`)
    const x = Number(row[0])
    const y = Number(row[1])
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0) throw new Error(`line ${index + 1}: require finite values and non-negative m/z`)
    mz.push(x)
    intensity.push(y)
    if (mz.length > MAX_ARRAY_LENGTH) throw new Error(`peak list exceeds the ${MAX_ARRAY_LENGTH} peak limit`)
  }
  if (!mz.length) throw new Error("peak list contains no peaks")
  return { defaultArrayLength: mz.length, mz, intensity }
}

/** Export only m/z and intensity. Other arrays and metadata are not included. */
export function formatPeakList(spec: InlineSpectrum, delimiter: PeakDelimiter = "\t"): string {
  validateArrays(spec)
  if (![",", "\t", " "].includes(delimiter)) throw new Error("invalid delimiter")
  if (spec.mz == null || spec.intensity == null) throw new Error("peak-list export requires m/z and intensity arrays")
  const number = (x: number) => Object.is(x, -0) ? "-0" : String(x)
  return ["mz" + delimiter + "intensity", ...Array.from(spec.mz, (mz, i) => number(mz) + delimiter + number(spec.intensity![i]!))].join("\n") + "\n"
}
