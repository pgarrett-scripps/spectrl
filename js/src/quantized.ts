/** A shared quantized-word representation for linear and log1p mappings. */
import { expm1 as deterministicExpm1, log1p as deterministicLog1p } from "./deterministic.js"
import { byteShuffle, byteUnshuffle, type NumArray } from "./codecs.js"
import type { Parameters } from "./pipeline.js"
import { deltaShuffleWords, deltaUnshuffleWords } from "./delta.js"
import { DEFAULT_INTENSITY_SCALE, DEFAULT_MZ_PPM } from "./format.js"

export function validateQuantized(p: Parameters): void {
  if (Object.keys(p).some(k => !["scale", "width", "log", "delta"].includes(k)) || !("scale" in p) || !("width" in p)) throw Error("quantized encoding requires scale and width")
  if (typeof p.scale !== "number" || !Number.isFinite(p.scale) || p.scale <= 0) throw Error("quantization scale must be finite and positive")
  if (![1, 2, 4, 8].includes(p.width as number)) throw Error("quantized word width must be 1, 2, 4, or 8")
  for (const key of ["log", "delta"]) if (key in p && typeof p[key] !== "boolean") throw Error("quantized log and delta parameters must be booleans")
}
function indices(a: NumArray, p: Parameters): Float64Array {
  return Float64Array.from(a, value => {
    if (!Number.isFinite(value) || value < 0) throw Error("quantization requires finite nonnegative values")
    const q = Math.round((p.log ? deterministicLog1p(value) : value) * (p.scale as number))
    if (!Number.isSafeInteger(q)) throw Error("quantized index exceeds the safe integer range")
    return q
  })
}
export function quantizedParameters(a: NumArray, scale: number, log = false, delta = false): Parameters {
  const p: Parameters = { scale, ...(log ? { log: true } : {}), ...(delta ? { delta: true } : {}) }
  let maximum = 0
  for (const q of indices(a, p)) maximum = Math.max(maximum, q)
  p.width = [1, 2, 4, 8].find(w => maximum < 2 ** (8 * w))!
  return p
}
// log1p is nearly linear below 1, so a fixed scale zeroes small peaks of
// normalized spectra. When the smallest positive value m is below 1, the scale
// grows to scale * (m + 1) / (2 * m), which bounds every positive value by the
// relative error the fixed scale already allows at 1.
export function intensityParameters(a: NumArray, scale = DEFAULT_INTENSITY_SCALE): Parameters {
  let minimum = Infinity
  for (const value of a) if (value > 0) minimum = Math.min(minimum, value)
  if (minimum < 1) {
    const refined = scale / 2 * (minimum + 1) / minimum
    if (!Number.isFinite(refined) || refined > 2 ** 53 - 1) throw Error("intensity scale is outside the supported range")
    scale = Math.max(scale, Math.ceil(refined))
  }
  return quantizedParameters(a, scale, true)
}
export function ppmParameters(a: NumArray, ppm = DEFAULT_MZ_PPM): Parameters {
  if (typeof ppm !== "number" || !Number.isFinite(ppm) || ppm <= 0) throw Error("ppm must be finite and positive")
  let minimum = Infinity
  for (const value of a) {
    if (!Number.isFinite(value) || value < 0) throw Error("ppm quantization requires finite nonnegative values")
    if (value > 0) minimum = Math.min(minimum, value)
  }
  if (minimum === Infinity) minimum = 1
  const relative = ppm * 1e-6
  // Calibrate at the smallest positive value and reserve a numerical margin.
  const logStep = deterministicLog1p(relative * (1 - 1e-7) * (minimum / (minimum + 1)))
  const scale = Math.ceil(0.5 / logStep)
  if (!(logStep > 0) || !Number.isSafeInteger(scale) || scale <= 0) throw Error("ppm scale is outside the supported range")
  const p = quantizedParameters(a, scale, true, true)
  const q = indices(a, p)
  for (const [i, value] of a.entries()) {
    const recovered = deterministicExpm1(q[i]! / scale)
    if (Math.abs(value - recovered) > value * relative) throw Error("quantized reconstruction exceeds the ppm bound")
  }
  return p
}
export function encodeQuantized(a: NumArray, _type: number, p: Parameters): Uint8Array {
  const q = indices(a, p)
  const width = p.width as number
  const raw = new Uint8Array(q.length * width)
  const view = new DataView(raw.buffer)
  for (const [i, value] of q.entries()) {
    if (value >= 2 ** (width * 8)) throw Error("quantized index exceeds its word width")
    if (width === 1) view.setUint8(i, value)
    else if (width === 2) view.setUint16(i * 2, value, true)
    else if (width === 4) view.setUint32(i * 4, value, true)
    else view.setBigUint64(i * 8, BigInt(value), true)
  }
  const blob = p.delta ? deltaShuffleWords(raw, width) : byteShuffle(raw, width)
  const recovered = decodeQuantized(blob, _type, q.length, p)
  const halfStep = 0.5 / (p.scale as number)
  for (const [i, value] of a.entries()) {
    const bound = p.log ? (value + 1) * deterministicExpm1(halfStep) : halfStep
    if (Math.abs(value - recovered[i]!) > bound) throw Error("quantized reconstruction exceeds the rounding bound")
  }
  return blob
}
export function decodeQuantized(blob: Uint8Array, _type: number, count: number, p: Parameters): Float64Array {
  const width = p.width as number
  if (blob.length !== count * width) throw Error("quantized byte count mismatch")
  const raw = p.delta ? deltaUnshuffleWords(blob, width) : byteUnshuffle(blob, width)
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength)
  return Float64Array.from({ length: count }, (_, i) => {
    const q = width === 1 ? view.getUint8(i) : width === 2 ? view.getUint16(i * 2, true)
      : width === 4 ? view.getUint32(i * 4, true) : Number(view.getBigUint64(i * 8, true))
    if (!Number.isSafeInteger(q)) throw Error("quantized index exceeds the safe integer range")
    const scaled = q / (p.scale as number)
    // The shared expm1, not the platform's, so the same token decodes to the
    // same bits everywhere. See src/deterministic.ts.
    const value = p.log ? deterministicExpm1(scaled) : scaled
    if (!Number.isFinite(value)) throw Error("quantized reconstruction is not finite")
    return value
  })
}
