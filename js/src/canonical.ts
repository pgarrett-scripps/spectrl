/** Canonical form: m/z-ascending sort, array-blob assembly, validation. */

import type { NumArray } from "./codecs.js"
import { descriptor, encodingNames, encodings, operation, encodePipeline, type Operation } from "./pipeline.js"
import { checkArrayMutation } from "./context.js"
import {
  ARRAY_CHARGE,
  ARRAY_INTENSITY,
  ARRAY_MZ,
  ARRAY_NON_STANDARD,
  TYPE_FLOAT32,
  TYPE_FLOAT64,
  TYPE_INT32,
  accessionTail,
} from "./cv.js";
import { ppmParameters, quantizedParameters } from "./quantized.js"
import { DEFAULT_INTENSITY_SCALE, DEFAULT_MZ_PPM } from "./format.js"
import type { Descriptor } from "./header.js";
import type { ArrayEncoding, ArrayEncodingOption, InlineSpectrum } from "./model.js";
import {
  MAX_ARRAY_LENGTH,
  MAX_SAFE_INTEGER,
} from "./format.js";

type ExtraArray = Float64Array | Float32Array | Int32Array | number[];

const MS_ACCESSION_RE = /^MS:\d{7}$/;
const ANY_ACCESSION_RE = /^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$/;
const CORE_ARRAY_ALIASES = new Map([
  ["MS:1000514", "mz"],
  ["MS:1000515", "intensity"],
  ["MS:1000516", "charge"],
]);
function parseEncoding(value?: ArrayEncodingOption): ArrayEncoding {
  if (value === undefined || value === "auto") return {}
  if (typeof value === "object" && !Array.isArray(value) && "encoding" in value) {
    if (Object.keys(value).some(k => k !== "encoding")) throw Error("only encoding is accepted in an array override")
    return value as ArrayEncoding
  }
  return { encoding: value as import("./pipeline.js").OperationOption }
}

/** Map an extra-array key to (arrayTail, name): accession keys → standard tail; else MS:1000786. */
function extraKeyToArray(key: string): { arrayTail: number; name?: string } {
  if (!key) throw new Error("non-standard array name must not be empty")
  const core = CORE_ARRAY_ALIASES.get(key)
  if (core !== undefined) throw new Error(`core array accession ${key} must use the dedicated '${core}' field`);
  if (key === "MS:1000786") {
    throw new Error("MS:1000786 is represented by a free-text extra-array name, not used as the key itself");
  }
  if (key === "mz" || key === "intensity" || key === "charge") {
    throw new Error(`non-standard array name '${key}' is reserved for a core array`);
  }
  if (MS_ACCESSION_RE.test(key)) return { arrayTail: accessionTail(key) };
  if (ANY_ACCESSION_RE.test(key)) {
    throw new Error(`standard binary-array accessions must be seven-digit PSI-MS accessions, got '${key}'`);
  }
  return { arrayTail: ARRAY_NON_STANDARD, name: key };
}

function normalizeEncodingKeys(encodings: Record<string, ArrayEncodingOption>): Record<string, ArrayEncodingOption> {
  const normalized: Record<string, ArrayEncodingOption> = Object.create(null)
  const original: Record<string, string> = Object.create(null)
  for (const [key, value] of Object.entries(encodings)) {
    const canonical = CORE_ARRAY_ALIASES.get(key) ?? key;
    if (Object.prototype.hasOwnProperty.call(normalized, canonical)) {
      throw new Error(`arrayEncodings contains conflicting aliases '${original[canonical]}' and '${key}' for '${canonical}'`);
    }
    normalized[canonical] = value;
    original[canonical] = key;
  }
  return normalized;
}

/** Binary data-type tail preserving a JS typed array's kind (default float64). */
function typeTailOf(v: ExtraArray): number {
  if (v instanceof Int32Array) return TYPE_INT32;
  if (v instanceof Float32Array) return TYPE_FLOAT32;
  return TYPE_FLOAT64;
}

/** Reorder an extra array by `order`, preserving its typed-array kind. */
function reorderExtra(v: ExtraArray, order: number[]): ExtraArray {
  if (v.length !== order.length) return v;
  const Ctor = (v as { constructor: unknown }).constructor as new (n: number) => ExtraArray;
  const out = Array.isArray(v) ? new Array<number>(order.length) : new Ctor(order.length);
  for (let i = 0; i < order.length; i++) (out as number[])[i] = (v as ArrayLike<number>)[order[i]!]!;
  return out as ExtraArray;
}

export function toF64(arr: ExtraArray | null | undefined): Float64Array | null {
  if (arr === null || arr === undefined) return null;
  return arr instanceof Float64Array ? arr : Float64Array.from(arr);
}

/** Return a copy of `spec` with peaks sorted m/z-ascending (stable), parallel arrays permuted. */
export function canonicalSort(spec: InlineSpectrum): InlineSpectrum {
  const mz = spec.mz
  if (mz == null || !mz.length) return spec
  const order = Array.from(mz.keys()).sort((a, b) => mz[a]! - mz[b]! || a - b)
  if (order.every((x, i) => x === i)) return spec
  checkArrayMutation(spec)
  const pick = (v: ExtraArray | null | undefined) => v == null ? v : reorderExtra(v, order)
  return { ...spec, mz: pick(mz), intensity: pick(spec.intensity), charge: pick(spec.charge),
    extraArrays: Object.fromEntries(Object.entries(spec.extraArrays ?? {}).map(([k, v]) => [k, reorderExtra(v, order)])) }
}

export function validateArrays(spec: InlineSpectrum): void {
  const n = spec.defaultArrayLength;
  if (!Number.isSafeInteger(n) || n < 0 || n > MAX_ARRAY_LENGTH) {
    throw new Error(`defaultArrayLength must be an integer between 0 and ${MAX_ARRAY_LENGTH}`);
  }
  for (const [name, arr] of [
    ["mz", toF64(spec.mz)],
    ["intensity", toF64(spec.intensity)],
    ["charge", toF64(spec.charge)],
  ] as const) {
    if (arr === null) continue;
    if (arr.length !== n) {
      throw new Error(`Array '${name}' has ${arr.length} values, but defaultArrayLength is ${n}; all peak arrays must have the same length.`);
    }
    for (const v of arr) {
      if (!Number.isFinite(v)) throw new Error(`Array '${name}' contains NaN or Inf values, not allowed in canonical form.`);
    }
  }
  for (const [k, v] of Object.entries(spec.extraArrays ?? {})) {
    if (v.length !== n) {
      throw new Error(`Array '${k}' has ${v.length} values, but defaultArrayLength is ${n}; all peak arrays must have the same length.`);
    }
  }
  // Float extra arrays must also be finite; integer arrays are always finite.
  for (const [k, v] of Object.entries(spec.extraArrays ?? {})) {
    if (v instanceof Int32Array) continue;
    for (const x of v as ArrayLike<number> & Iterable<number>) {
      if (!Number.isFinite(x)) throw new Error(`Array '${k}' contains NaN or Inf values, not allowed in canonical form.`);
    }
  }
  const mz = toF64(spec.mz);
  if (mz !== null && hasNegative(mz)) {
    throw new Error("Array 'mz' contains negative values; m/z must be non-negative.");
  }
  const validUnitKeys = new Set(["mz", "intensity", "charge", ...Object.keys(spec.extraArrays ?? {})]);
  const seenUnitKeys = new Map<string, string>();
  for (const [rawKey, unit] of Object.entries(spec.arrayUnits ?? {})) {
    const key = CORE_ARRAY_ALIASES.get(rawKey) ?? rawKey;
    if (!validUnitKeys.has(key)) throw new Error(`arrayUnits contains unknown array key '${rawKey}'`);
    if (seenUnitKeys.has(key)) throw new Error(`arrayUnits contains conflicting aliases '${seenUnitKeys.get(key)}' and '${rawKey}'`);
    seenUnitKeys.set(key, rawKey);
    if (!ANY_ACCESSION_RE.test(unit)) throw new Error(`invalid unit accession '${unit}' for array '${key}'`);
  }
}

function hasNegative(arr: ArrayLike<number>): boolean {
  for (let i = 0; i < arr.length; i++) if (arr[i]! < 0) return true;
  return false;
}

/** Encode all peak arrays. Returns blobs and matching descriptors (without `seg`). */
export function buildArrayBlobs(
  spec: InlineSpectrum, lossless: boolean, mzPpm = DEFAULT_MZ_PPM, intFp = DEFAULT_INTENSITY_SCALE,
  arrayEncodings?: Record<string, ArrayEncodingOption>, allowUnsafeLossyCustom = false,
): { blobs: Uint8Array[], descriptors: Descriptor[] } {
  for (const key of Object.keys(spec.extraArrays ?? {})) extraKeyToArray(key)
  const settings = normalizeEncodingKeys(arrayEncodings ?? {})
  const arrays: [string, ExtraArray | null | undefined][] = [
    ["mz", spec.mz], ["intensity", spec.intensity], ["charge", spec.charge],
    ...Object.entries(spec.extraArrays ?? {}).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0),
  ]
  const present = new Set(arrays.filter(([, a]) => a != null).map(([k]) => k))
  if (Object.keys(settings).some(k => !present.has(k))) throw Error("arrayEncodings contains unknown array key")
  for (const field of ["arrayNames", "arrayParams", "arrayUserParams", "arrayProcessing", "arrayExtensions"] as const) {
    if (Object.keys(spec[field] ?? {}).some(k => !present.has(k))) throw Error(`${field} contains an absent or noncanonical array key`)
  }
  for (const [key, name] of Object.entries(spec.arrayNames ?? {})) {
    if (typeof name !== "string" || !name.length) throw Error("array name must be a non-empty string")
    if (Object.prototype.hasOwnProperty.call(spec.extraArrays ?? {}, key) && extraKeyToArray(key).arrayTail === ARRAY_NON_STANDARD && name !== key) {
      throw Error("a non-standard array name must match its extraArrays key")
    }
  }
  const representation = new Set([1000519, 1000521, 1000522, 1000523, 1000576, 1000574, 1002312, 1002313, 1002314, 1002746, 1002747, 1002748, 1003780, 1003781, 1003782, 1003783, 1003784, 1003785])
  for (const [key, values] of Object.entries(spec.arrayParams ?? {})) {
    const identity = key === "mz" ? ARRAY_MZ : key === "intensity" ? ARRAY_INTENSITY : key === "charge" ? ARRAY_CHARGE : extraKeyToArray(key).arrayTail
    if (values.some(p => /^MS:\d+$/.test(p.accession) && (representation.has(accessionTail(p.accession)) || accessionTail(p.accession) === identity))) throw Error("array scientific parameters conflict with representation declarations")
  }
  const blobs: Uint8Array[] = []
  const descriptors: Descriptor[] = []
  for (const [key, input] of arrays) {
    if (input == null) continue
    const array = Array.isArray(input) ? Float64Array.from(input) : input
    const identity = key === "mz" ? { arrayTail: ARRAY_MZ } : key === "intensity" ? { arrayTail: ARRAY_INTENSITY } : key === "charge" ? { arrayTail: ARRAY_CHARGE } : extraKeyToArray(key)
    const tail = identity.arrayTail
    const setting = parseEncoding(settings[key])
    const automatic = setting.encoding === undefined
    let type = typeTailOf(array)
    let defaultEncoding: Operation = [key === "mz" ? 2 : key === "intensity" ? 1 : 0, 1]
    if (!lossless && ["mz", "intensity"].includes(key) && !(array instanceof Int32Array) && !hasNegative(array)) {
      try { defaultEncoding = [3, 1, key === "mz" ? ppmParameters(array, mzPpm) : quantizedParameters(array, intFp, true)] }
      catch { /* Unsupported numeric domains use the exact default. */ }
    }
    let encoding = descriptor(setting.encoding ?? defaultEncoding, encodingNames)
    const [implementation] = operation(encodings, encoding)
    if (!implementation.lossless) {
      if (lossless) throw Error("lossy encoding requested with lossless true")
      if (!["mz", "intensity"].includes(key) && !allowUnsafeLossyCustom) throw Error("custom lossy array requires explicit permission")
      if (!implementation.types.includes(type)) type = TYPE_FLOAT64
    }
    let result: { blob: Uint8Array, fidelity: number }
    try { result = encodePipeline(array, type, encoding) }
    catch (e) {
      if (!automatic) throw e
      type = typeTailOf(array)
      encoding = [key === "mz" ? 2 : key === "intensity" ? 1 : 0, 1]
      result = encodePipeline(array, type, encoding)
    }
    blobs.push(result.blob)
    descriptors.push({ type, array: tail, encoding, fidelity: result.fidelity,
      name: Object.prototype.hasOwnProperty.call(spec.arrayNames ?? {}, key) ? spec.arrayNames![key] : identity.name,
      unit: spec.arrayUnits?.[key] ?? spec.arrayUnits?.[`MS:${tail}`], params: spec.arrayParams?.[key],
      userParams: spec.arrayUserParams?.[key], processing: spec.arrayProcessing?.[key], extensions: spec.arrayExtensions?.[key],
    })
  }
  return { blobs, descriptors }
}
