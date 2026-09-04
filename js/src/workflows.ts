/** Quality measurement and explicit share-budget selection for v1 tokens. */
import { canonicalSort, validateArrays } from "./canonical.js"
import { decodeCbor, encodeCbor } from "./cbor_format.js"
import { tokenBreakdown } from "./inspect.js"
import type { EncodeOptions } from "./index.js"
import type { InlineSpectrum } from "./model.js"
import { toFragment } from "./url.js"

type Options = Omit<EncodeOptions, "maxLen" | "quiet">
const userCount = (s: InlineSpectrum) => (s.userParams?.length ?? 0) + (s.scans ?? []).reduce((n, scan) => n + (scan.userParams?.length ?? 0), 0)
const encode = (s: InlineSpectrum, o: Options) => encodeCbor(s, o.lossless, o.dropUserParams, o.arrayEncodings, o.allowUnsafeLossyCustom)
const dtype = (a: ArrayLike<number>) => a instanceof Int32Array ? "int32" : a instanceof Float32Array ? "float32" : "float64"
const finite = (n: number) => Number.isFinite(n) ? n : null

/** Encode once and report errors against sorted source arrays. Zero references are counted separately. */
export function encodingReport(spec: InlineSpectrum, options: Options = {}) {
  const token = encode(spec, options)
  const decoded = decodeCbor(token)
  const source = canonicalSort(spec)
  const sourceArrays = Object.fromEntries<ArrayLike<number>>([
    ...(["mz", "intensity", "charge"] as const).filter(k => source[k] != null).map(k => [k, source[k]!] as [string, ArrayLike<number>]),
    ...Object.entries(source.extraArrays ?? {}).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0),
  ])
  const decodedArrays = { ...decoded.extraArrays, mz: decoded.mz, intensity: decoded.intensity, charge: decoded.charge }
  const parts = tokenBreakdown(token).filter(p => p.accession !== undefined)
  const arrays = Object.entries(sourceArrays).map(([key, a], index) => {
    const b = decodedArrays[key as keyof typeof decodedArrays] as ArrayLike<number>
    let maxAbsolute = 0
    let maxRelative = 0
    let meanRelative = 0
    let relativeCount = 0
    let zeros = 0
    let changedZeros = 0
    let exact = dtype(a) === dtype(b)
    for (const [i, value] of Array.from(a).entries()) {
      const error = Math.abs(b[i]! - value)
      maxAbsolute = Math.max(error, maxAbsolute)
      exact = exact && Object.is(value, b[i])
      if (value === 0) {
        zeros++
        if (error !== 0) changedZeros++
      } else {
        const relative = error / Math.abs(value)
        maxRelative = Math.max(relative, maxRelative)
        relativeCount++
        meanRelative += (relative - meanRelative) / relativeCount
      }
    }
    return {
      key, ...parts[index], sourceDtype: dtype(a), decodedDtype: dtype(b),
      rawBytes: a.length * (dtype(a) === "float64" ? 8 : 4), exact,
      maxAbsoluteError: finite(maxAbsolute),
      maxRelativeError: relativeCount ? finite(maxRelative) : null,
      meanRelativeError: relativeCount ? finite(meanRelative) : null,
      zeroReferenceValues: zeros, changedZeroValues: changedZeros,
      ...(key === "mz" ? {
        maxErrorPpm: relativeCount ? finite(maxRelative * 1e6) : null,
        meanErrorPpm: relativeCount ? finite(meanRelative * 1e6) : null,
      } : {}),
    }
  })
  return {
    token, tokenBytes: token.length, peakCount: source.defaultArrayLength,
    rawArrayBytes: arrays.reduce((n, a) => n + a.rawBytes, 0), arrays,
    omittedUserParams: options.dropUserParams ? userCount(source) : 0,
    allArraysExact: arrays.every(a => a.exact),
  }
}

/** Select the most intense peaks with deterministic ties and preserve every parallel array. */
export function topN(spec: InlineSpectrum, n: number): InlineSpectrum {
  validateArrays(spec)
  if (!Number.isSafeInteger(n) || n < 0) throw new Error("n must be a non-negative integer")
  if (spec.intensity == null || n >= spec.defaultArrayLength) return spec
  const intensity = spec.intensity
  const secondary = (i: number) => spec.mz?.[i] ?? i
  const indices = Array.from({ length: spec.defaultArrayLength }, (_, i) => i)
    .sort((a, b) => intensity[b]! - intensity[a]! || secondary(a) - secondary(b) || a - b)
    .slice(0, n).sort((a, b) => secondary(a) - secondary(b) || a - b)
  const pick = (a: ArrayLike<number> | null | undefined) => a == null ? a : Float64Array.from(indices, i => a[i]!)
  const extras = Object.fromEntries(Object.entries(spec.extraArrays ?? {}).map(([key, a]) => {
    const values = indices.map(i => a[i]!)
    return [key, a instanceof Int32Array ? Int32Array.from(values) : a instanceof Float32Array ? Float32Array.from(values) : Float64Array.from(values)]
  }))
  return { ...spec, defaultArrayLength: n, mz: pick(spec.mz), intensity: pick(intensity), charge: pick(spec.charge), extraArrays: extras }
}

export interface BudgetOptions extends Options {
  baseUrl?: string
  allowPeakTrimming?: boolean
  minPeaks?: number
}

/** Return a fitting candidate. Compression is not monotonic, so maximum retained count is not guaranteed. */
export function fitToBudget(spec: InlineSpectrum, maxBytes: number, options: BudgetOptions = {}) {
  validateArrays(spec)
  if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) throw new Error("maxBytes must be a positive integer")
  const minimum = options.minPeaks ?? 1
  if (!Number.isSafeInteger(minimum) || minimum < 0) throw new Error("minPeaks must be a non-negative integer")
  const original = spec.defaultArrayLength
  const candidate = (n: number) => {
    const spectrum = n === original ? spec : topN(spec, n)
    const token = encode(spectrum, options)
    const carrier = options.baseUrl === undefined ? token : toFragment(token, options.baseUrl)
    return { spectrum, token, carrier, carrierBytes: new TextEncoder().encode(carrier).length }
  }
  let best = candidate(original)
  if (best.carrierBytes > maxBytes) {
    if (!options.allowPeakTrimming) throw new Error("spectrum exceeds the share budget, enable peak trimming explicitly or change the budget")
    if (spec.intensity == null) throw new Error("peak trimming requires an intensity array")
    let low = Math.min(minimum, original)
    let high = original
    best = candidate(low)
    if (best.carrierBytes > maxBytes) throw new Error("metadata and minimum peaks exceed the share budget")
    while (high - low > 1) {
      const mid = Math.floor((low + high) / 2)
      const trial = candidate(mid)
      if (trial.carrierBytes <= maxBytes) {
        best = trial
        low = mid
      } else high = mid
    }
  }
  if (options.dropUserParams) best.spectrum = {
    ...best.spectrum, userParams: [], scans: best.spectrum.scans?.map(scan => ({ ...scan, userParams: [] })),
  }
  return { ...best, maxBytes, originalPeaks: original, keptPeaks: best.spectrum.defaultArrayLength,
    droppedPeaks: original - best.spectrum.defaultArrayLength,
    omittedUserParams: options.dropUserParams ? userCount(spec) : 0 }
}
