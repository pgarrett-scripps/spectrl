/** Canonical form: m/z-ascending sort, array-blob assembly, validation. */

import { encodeArray } from "./codecs.js";
import {
  ARRAY_CHARGE,
  ARRAY_INTENSITY,
  ARRAY_MZ,
  ARRAY_NON_STANDARD,
  COMP_NUMLIN_ZLIB,
  COMP_NUMPIC_ZLIB,
  COMP_NUMSLOF_ZLIB,
  COMP_ZLIB,
  TYPE_FLOAT32,
  TYPE_FLOAT64,
  TYPE_INT32,
  accessionTail,
} from "./cv.js";
import { DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, safeSlofFp } from "./codecs.js";
import type { Descriptor } from "./header.js";
import type { InlineSpectrum } from "./model.js";
import { MAX_ARRAY_LENGTH } from "./format.js";

type ExtraArray = Float64Array | Float32Array | Int32Array | number[];

const ACCESSION_RE = /^[A-Za-z][A-Za-z0-9]*:\d+$/;

/** Map an extra-array key to (arrayTail, name): accession keys → standard tail; else MS:1000786. */
function extraKeyToArray(key: string): { arrayTail: number; name?: string } {
  return ACCESSION_RE.test(key) ? { arrayTail: accessionTail(key) } : { arrayTail: ARRAY_NON_STANDARD, name: key };
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
  const im = toF64(spec.ionMobility);

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
    ionMobility: pick(im) ?? undefined,
    extraArrays,
  };
}

export function validateArrays(spec: InlineSpectrum): void {
  const n = spec.defaultArrayLength;
  if (!Number.isSafeInteger(n) || n < 0 || n > MAX_ARRAY_LENGTH) {
    throw new Error(`defaultArrayLength must be an integer between 0 and ${MAX_ARRAY_LENGTH}`);
  }
  if ((spec.ionMobility == null) !== (spec.ionMobilityType == null)) {
    throw new Error("ionMobility and ionMobilityType must be provided together");
  }
  for (const [name, arr] of [
    ["mz", toF64(spec.mz)],
    ["intensity", toF64(spec.intensity)],
    ["charge", toF64(spec.charge)],
    ["ionMobility", toF64(spec.ionMobility)],
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
}

function hasNegative(arr: Float64Array): boolean {
  for (const v of arr) if (v < 0) return true;
  return false;
}

/** Encode all peak arrays. Returns blobs and matching descriptors (without `seg`). */
export function buildArrayBlobs(
  spec: InlineSpectrum,
  lossless: boolean,
  mzFp = DEFAULT_NUMLIN_FP,
  intFp = DEFAULT_NUMSLOF_FP,
): { blobs: Uint8Array[]; descriptors: Omit<Descriptor, "seg">[] } {
  const blobs: Uint8Array[] = [];
  const descriptors: Omit<Descriptor, "seg">[] = [];

  // A codec's canonical default fp, omitted from the descriptor when it is the
  // one in use: absent means "the default for this codec" (spec section 7.1).
  // The fp is also carried inside the numpress stream itself, so this costs no
  // information -- it only removes a value that was constant in nearly every
  // token (the slof clamp fires only for very high intensities).
  const defaultFp = new Map<number, number>([
    [COMP_NUMLIN_ZLIB, DEFAULT_NUMLIN_FP],
    [COMP_NUMSLOF_ZLIB, DEFAULT_NUMSLOF_FP],
  ]);

  const add = (
    array: ArrayLike<number>,
    arrayTail: number,
    compTail: number,
    fp: number | null,
    typeTail = TYPE_FLOAT64,
    name?: string,
  ): void => {
    blobs.push(encodeArray(array, compTail, fp, typeTail));
    const desc: Omit<Descriptor, "seg"> = { type: typeTail, array: arrayTail, comp: compTail };
    if (fp !== null && !lossless && fp !== defaultFp.get(compTail)) desc.fp = fp;
    if (name !== undefined) desc.name = name;
    descriptors.push(desc);
  };

  const mz = toF64(spec.mz);
  if (mz !== null) add(mz, ARRAY_MZ, lossless ? COMP_ZLIB : COMP_NUMLIN_ZLIB, lossless ? null : mzFp);

  // The slof codec computes log(v + 1) and cannot represent negative values
  // (baseline-subtracted data may contain them), so fall back to lossless
  // zlib when the array contains any negative value.
  const intensity = toF64(spec.intensity);
  if (intensity !== null) {
    const useZlib = lossless || hasNegative(intensity);
    // Clamp the slof fixed point here so the descriptor records the fp the
    // blob actually uses (large intensities force a smaller fp).
    add(intensity, ARRAY_INTENSITY, useZlib ? COMP_ZLIB : COMP_NUMSLOF_ZLIB, useZlib ? null : safeSlofFp(intensity, intFp));
  }

  // The PIC integer codec only handles non-negative values; charge arrays may
  // carry negative sentinels (e.g. unassigned/singleton), so fall back to
  // lossless zlib when the array contains any negative value.
  const charge = toF64(spec.charge);
  if (charge !== null) add(charge, ARRAY_CHARGE, lossless || hasNegative(charge) ? COMP_ZLIB : COMP_NUMPIC_ZLIB, null);

  // The linear codec's rounding differs between implementations for negative
  // values, so fall back to lossless zlib to keep byte-identity.
  const im = toF64(spec.ionMobility);
  if (im !== null && spec.ionMobilityType) {
    const useZlib = lossless || hasNegative(im);
    add(im, accessionTail(spec.ionMobilityType), useZlib ? COMP_ZLIB : COMP_NUMLIN_ZLIB, useZlib ? null : mzFp);
  }

  // Extra arrays: always raw + zlib (lossless), data type preserved, emitted in
  // sorted key order so the token (and its content hash) is deterministic.
  if (spec.extraArrays) {
    for (const key of Object.keys(spec.extraArrays).sort()) {
      const v = spec.extraArrays[key]!;
      const { arrayTail, name } = extraKeyToArray(key);
      add(v, arrayTail, COMP_ZLIB, null, typeTailOf(v), name);
    }
  }

  return { blobs, descriptors };
}
