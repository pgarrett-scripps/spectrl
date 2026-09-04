/** Canonical form: m/z-ascending sort, array-blob assembly, validation. */

import { encodeArray } from "./codecs.js"
import { validateLinearDomain, validatePicDomain } from "./numpress.js"
import {
  ARRAY_CHARGE,
  ARRAY_INTENSITY,
  ARRAY_MZ,
  ARRAY_NON_STANDARD,
  COMP_BYTE_SHUFFLED_ZSTD,
  COMP_NUMLIN_ZLIB,
  COMP_NUMLIN_ZSTD,
  COMP_NUMPIC_ZLIB,
  COMP_NUMPIC_ZSTD,
  COMP_NUMSLOF_ZLIB,
  COMP_NUMSLOF_ZSTD,
  COMP_ZLIB,
  COMP_ZSTD,
  TYPE_FLOAT32,
  TYPE_FLOAT64,
  TYPE_INT32,
  accessionTail,
} from "./cv.js";
import { DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, safeSlofFp } from "./codecs.js";
import type { Descriptor } from "./header.js";
import type { ArrayEncoding, ArrayEncodingOption, InlineSpectrum } from "./model.js";
import {
  EXTRA_NUMLIN_ARRAY_TAILS,
  EXTRA_NUMPIC_ARRAY_TAILS,
  EXTRA_NUMSLOF_ARRAY_TAILS,
  ION_MOBILITY_ARRAY_TAILS,
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
const CODEC_NAMES = new Map<string, number>([
  ["zlib", COMP_ZLIB],
  ["zstd", COMP_ZSTD],
  ["byte-shuffled-zstd", COMP_BYTE_SHUFFLED_ZSTD],
  ["numlin-zlib", COMP_NUMLIN_ZLIB],
  ["numlin-zstd", COMP_NUMLIN_ZSTD],
  ["numslof-zlib", COMP_NUMSLOF_ZLIB],
  ["numslof-zstd", COMP_NUMSLOF_ZSTD],
  ["numpic-zlib", COMP_NUMPIC_ZLIB],
  ["numpic-zstd", COMP_NUMPIC_ZSTD],
]);
const LOSSY_CODECS = new Set([
  COMP_NUMLIN_ZLIB,
  COMP_NUMLIN_ZSTD,
  COMP_NUMSLOF_ZLIB,
  COMP_NUMSLOF_ZSTD,
  COMP_NUMPIC_ZLIB,
  COMP_NUMPIC_ZSTD,
]);
const LINEAR_EXTRA_ARRAYS = new Set([...EXTRA_NUMLIN_ARRAY_TAILS, ...ION_MOBILITY_ARRAY_TAILS]);
const SLOF_EXTRA_ARRAYS = EXTRA_NUMSLOF_ARRAY_TAILS;
const PIC_EXTRA_ARRAYS = EXTRA_NUMPIC_ARRAY_TAILS;

function parseEncoding(value?: ArrayEncodingOption): ArrayEncoding {
  if (value === undefined) return { codec: "auto" };
  if (typeof value === "string" || typeof value === "number") return { codec: value };
  return value;
}

function codecTail(codec: ArrayEncoding["codec"]): number | null {
  if (codec === undefined || codec === "auto") return null;
  if (typeof codec === "number") return codec;
  if (MS_ACCESSION_RE.test(codec)) return accessionTail(codec);
  const tail = CODEC_NAMES.get(codec);
  if (tail === undefined) throw new Error(`unknown array codec '${codec}'`);
  return tail;
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

export function toF64(arr: Float64Array | number[] | null | undefined): Float64Array | null {
  if (arr === null || arr === undefined) return null;
  return arr instanceof Float64Array ? arr : Float64Array.from(arr);
}

/** Return a copy of `spec` with peaks sorted m/z-ascending (stable), parallel arrays permuted. */
export function canonicalSort(spec: InlineSpectrum): InlineSpectrum {
  const mz = toF64(spec.mz);
  if (mz === null || mz.length === 0) return spec;
  const intensity = toF64(spec.intensity);
  const charge = toF64(spec.charge);

  const order = Array.from(mz.keys()).sort((a, b) => {
    const d = mz[a]! - mz[b]!;
    return d !== 0 ? d : a - b; // stable
  });

  const pick = (src: Float64Array | null): Float64Array | null => {
    if (src === null) return null;
    const out = new Float64Array(order.length);
    for (let i = 0; i < order.length; i++) out[i] = src[order[i]!]!;
    return out;
  };

  let extraArrays = spec.extraArrays;
  if (extraArrays) {
    extraArrays = Object.fromEntries(Object.entries(extraArrays).map(([k, v]) => [k, reorderExtra(v, order)]));
  }

  return {
    ...spec,
    mz: pick(mz)!,
    intensity: pick(intensity) ?? undefined,
    charge: pick(charge) ?? undefined,
    extraArrays,
  };
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
  spec: InlineSpectrum,
  lossless: boolean,
  mzFp = DEFAULT_NUMLIN_FP,
  intFp = DEFAULT_NUMSLOF_FP,
  arrayEncodings?: Record<string, ArrayEncodingOption>,
  allowUnsafeLossyCustom = false,
): { blobs: Uint8Array[]; descriptors: Omit<Descriptor, "seg">[] } {
  const blobs: Uint8Array[] = [];
  const descriptors: Omit<Descriptor, "seg">[] = [];
  const encodings = normalizeEncodingKeys(arrayEncodings ?? {});

  const validKeys = new Set(["mz", "intensity", "charge", ...Object.keys(spec.extraArrays ?? {})]);
  const unknownKeys = Object.keys(encodings).filter((key) => !validKeys.has(key));
  if (unknownKeys.length) throw new Error(`arrayEncodings contains unknown array key(s): ${unknownKeys.sort().join(", ")}`);

  const resolve = (
    key: string,
    array: ArrayLike<number>,
    defaultComp: number,
    defaultFixedPoint: number | null,
    defaultType = TYPE_FLOAT64,
  ): { comp: number; fp: number | null; type: number } => {
    const setting = parseEncoding(encodings[key]);
    let selected = codecTail(setting.codec)
    const automatic = selected === null
    if (selected === null) {
      selected = defaultComp
      if (setting.fixedPoint === undefined) {
        try {
          if (selected === COMP_NUMLIN_ZLIB || selected === COMP_NUMLIN_ZSTD) validateLinearDomain(array, defaultFixedPoint!)
          if (selected === COMP_NUMPIC_ZLIB || selected === COMP_NUMPIC_ZSTD) validatePicDomain(array)
        } catch {
          return { comp: COMP_ZLIB, fp: null, type: typeTailOf(array as ExtraArray) }
        }
      }
    }
    if (lossless && LOSSY_CODECS.has(selected)) {
      throw new Error(`array '${key}' requests a lossy codec while lossless is true`);
    }
    const fpCodecs = new Set([COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD]);
    if (!fpCodecs.has(selected) && setting.fixedPoint !== undefined) {
      throw new Error(`array '${key}' sets fixedPoint for a codec that takes no fixed point`);
    }
    if (setting.fixedPoint !== undefined &&
        (!Number.isSafeInteger(setting.fixedPoint) || setting.fixedPoint <= 0 || setting.fixedPoint > MAX_SAFE_INTEGER)) {
      throw new Error(`array '${key}' fixedPoint must be a positive whole number`);
    }
    const linear = new Set([COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD]);
    const slof = new Set([COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD]);
    const pic = new Set([COMP_NUMPIC_ZLIB, COMP_NUMPIC_ZSTD]);
    let allowed = new Set<number>();
    if (key === "mz") allowed = linear;
    else if (key === "intensity") allowed = new Set([...linear, ...slof]);
    else if (key === "charge") allowed = pic;
    else if (key.startsWith("MS:") && LINEAR_EXTRA_ARRAYS.has(accessionTail(key))) allowed = linear;
    else if (key.startsWith("MS:") && SLOF_EXTRA_ARRAYS.has(accessionTail(key))) allowed = new Set([...linear, ...slof]);
    else if (key.startsWith("MS:") && PIC_EXTRA_ARRAYS.has(accessionTail(key))) allowed = pic;
    const semanticUnknown = key !== "mz" && key !== "intensity" && key !== "charge"
      && (!key.startsWith("MS:") || !LINEAR_EXTRA_ARRAYS.has(accessionTail(key))
        && !SLOF_EXTRA_ARRAYS.has(accessionTail(key)) && !PIC_EXTRA_ARRAYS.has(accessionTail(key)));
    if (LOSSY_CODECS.has(selected) && !allowed.has(selected) && !(semanticUnknown && allowUnsafeLossyCustom)) {
      throw new Error(`array '${key}' is not compatible with codec '${String(setting.codec)}'`);
    }
    if (LOSSY_CODECS.has(selected) && hasNegative(array)) {
      throw new Error(`array '${key}' contains negative values and cannot use codec '${String(setting.codec)}'`);
    }
    if (pic.has(selected)) {
      for (let i = 0; i < array.length; i++) {
        if (!Number.isInteger(array[i])) throw new Error(`array '${key}' contains fractional values and cannot use a positive-integer codec`);
      }
    }
    let fp: number | null = null;
    if (selected === COMP_NUMLIN_ZLIB || selected === COMP_NUMLIN_ZSTD) fp = setting.fixedPoint ?? (automatic ? defaultFixedPoint : mzFp)
    if (selected === COMP_NUMSLOF_ZLIB || selected === COMP_NUMSLOF_ZSTD) {
      const desired = setting.fixedPoint ?? (automatic ? defaultFixedPoint! : intFp)
      const safe = safeSlofFp(Float64Array.from(array), desired);
      if (setting.fixedPoint !== undefined && safe !== desired) {
        throw new Error(`array '${key}' fixedPoint ${desired} would overflow the SLOF representation`);
      }
      fp = safe;
    }
    return { comp: selected, fp, type: LOSSY_CODECS.has(selected) ? TYPE_FLOAT64 : defaultType };
  };

  const add = (
    array: ArrayLike<number>,
    arrayTail: number,
    compTail: number,
    fp: number | null,
    typeTail = TYPE_FLOAT64,
    name?: string,
    unit?: string,
  ): void => {
    blobs.push(encodeArray(array, compTail, fp, typeTail));
    const desc: Omit<Descriptor, "seg"> = { type: typeTail, array: arrayTail, comp: compTail };
    if (fp !== null) desc.fp = fp;
    if (name !== undefined) desc.name = name;
    if (unit !== undefined) desc.unit = unit;
    descriptors.push(desc);
  };

  const mz = toF64(spec.mz);
  if (mz !== null) {
    const selected = resolve("mz", mz, lossless ? COMP_ZLIB : COMP_NUMLIN_ZLIB, lossless ? null : mzFp);
    add(mz, ARRAY_MZ, selected.comp, selected.fp, selected.type, undefined, spec.arrayUnits?.mz ?? spec.arrayUnits?.["MS:1000514"]);
  }

  // The slof codec computes log(v + 1) and cannot represent negative values
  // (baseline-subtracted data may contain them), so fall back to lossless
  // zlib when the array contains any negative value.
  const intensity = toF64(spec.intensity);
  if (intensity !== null) {
    const useZlib = lossless || hasNegative(intensity);
    // Clamp the slof fixed point here so the descriptor records the fp the
    // blob actually uses (large intensities force a smaller fp).
    const selected = resolve(
      "intensity",
      intensity,
      useZlib ? COMP_ZLIB : COMP_NUMSLOF_ZLIB,
      useZlib ? null : safeSlofFp(intensity, intFp),
    );
    add(intensity, ARRAY_INTENSITY, selected.comp, selected.fp, selected.type, undefined, spec.arrayUnits?.intensity ?? spec.arrayUnits?.["MS:1000515"]);
  }

  // The PIC integer codec only handles non-negative values; charge arrays may
  // carry negative sentinels (e.g. unassigned/singleton), so fall back to
  // lossless zlib when the array contains any negative value.
  const charge = toF64(spec.charge);
  if (charge !== null) {
    const selected = resolve("charge", charge, lossless || hasNegative(charge) ? COMP_ZLIB : COMP_NUMPIC_ZLIB, null);
    add(charge, ARRAY_CHARGE, selected.comp, selected.fp, selected.type, undefined, spec.arrayUnits?.charge ?? spec.arrayUnits?.["MS:1000516"]);
  }

  // Known PSI-MS arrays receive conservative semantic defaults. Unknown arrays
  // stay lossless. Explicit per-array settings always take precedence.
  if (spec.extraArrays) {
    for (const key of Object.keys(spec.extraArrays).sort()) {
      const v = spec.extraArrays[key]!;
      const { arrayTail, name } = extraKeyToArray(key);
      const nativeType = typeTailOf(v);
      let defaultComp = COMP_ZLIB;
      let defaultFixedPoint: number | null = null;
      let defaultType = nativeType;
      if (!lossless && LINEAR_EXTRA_ARRAYS.has(arrayTail) && !hasNegative(v)) {
        defaultComp = COMP_NUMLIN_ZLIB;
        defaultFixedPoint = DEFAULT_NUMLIN_FP;
        defaultType = TYPE_FLOAT64;
      } else if (!lossless && SLOF_EXTRA_ARRAYS.has(arrayTail) && !hasNegative(v)) {
        defaultComp = COMP_NUMSLOF_ZLIB;
        defaultFixedPoint = safeSlofFp(Float64Array.from(v), DEFAULT_NUMSLOF_FP);
        defaultType = TYPE_FLOAT64;
      } else if (!lossless && PIC_EXTRA_ARRAYS.has(arrayTail) && !hasNegative(v)) {
        defaultComp = COMP_NUMPIC_ZLIB;
        defaultType = TYPE_FLOAT64;
      }
      const selected = resolve(key, v, defaultComp, defaultFixedPoint, defaultType);
      add(v, arrayTail, selected.comp, selected.fp, selected.type, name, spec.arrayUnits?.[key]);
    }
  }

  return { blobs, descriptors };
}
