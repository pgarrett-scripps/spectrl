/**
 * Rounded floating-point words for v3 encoding 4.
 *
 * Each value keeps its sign, exponent and leading `bits` mantissa bits. The
 * rounding works on the unsigned integer view of the IEEE 754 bits, so it uses
 * integer operations only and matches the Python writer word for word. float64
 * words below 2^53 (shift of at least 11) stay in Number arithmetic; wider
 * words use BigInt.
 */
import { byteShuffle, byteUnshuffle, type NumArray } from "./codecs.js"
import { TYPE_FLOAT32, TYPE_FLOAT64 } from "./cv.js"
import type { Parameters } from "./pipeline.js"

type Word = number | bigint
// word >= 2^exponent without converting Number words to BigInt.
const atLeast = (word: Word, exponent: number) =>
  typeof word === "number" ? word >= 2 ** exponent : word >= 1n << BigInt(exponent)

export function validateRounded(p: Parameters): void {
  const keys = Object.keys(p)
  if (keys.length !== 2 || !("bits" in p) || !("width" in p)) throw Error("rounded encoding requires exactly bits and width")
  if (typeof p.bits !== "number" || !Number.isInteger(p.bits) || p.bits < 0 || p.bits > 52) throw Error("rounded mantissa bits must be an integer from 0 to 52")
  if (![1, 2, 4, 8].includes(p.width as number)) throw Error("rounded word width must be 1, 2, 4, or 8")
}

function format(type: number, bits: number, width: number): [shift: number, size: number] {
  if (type !== TYPE_FLOAT32 && type !== TYPE_FLOAT64) throw Error("rounded encoding requires float32 or float64")
  const [mantissa, size] = type === TYPE_FLOAT32 ? [23, 4] : [52, 8]
  if (bits > mantissa) throw Error("rounded mantissa bits exceed the declared type")
  if (width > size) throw Error("rounded word width exceeds the declared type")
  return [mantissa - bits, size]
}

/** Rounded unsigned words: (u + 2^(d-1)) >> d, computed as (u >> d) + bit d-1 of u. */
export function roundedWords(a: ArrayLike<number>, type: number, bits: number): Word[] {
  const [shift, size] = format(type, bits, 1)
  const view = new DataView(new ArrayBuffer(8))
  const out: Word[] = new Array(a.length)
  for (let i = 0; i < a.length; i++) {
    const value = a[i]!
    if (!Number.isFinite(value)) throw Error("rounded encoding requires finite values")
    if (size === 4) {
      view.setFloat32(0, value, true)
      const u = view.getUint32(0, true)
      out[i] = shift === 0 ? u : (u >>> shift) + ((u >>> (shift - 1)) & 1)
      continue
    }
    view.setFloat64(0, value, true)
    const lo = view.getUint32(0, true), hi = view.getUint32(4, true)
    if (shift >= 11) {
      const q = shift >= 32 ? hi >>> (shift - 32) : hi * 2 ** (32 - shift) + (lo >>> shift)
      const r = shift - 1 >= 32 ? (hi >>> (shift - 33)) & 1 : (lo >>> (shift - 1)) & 1
      out[i] = q + r
    } else {
      const u = (BigInt(hi) << 32n) | BigInt(lo)
      out[i] = shift === 0 ? u : (u >> BigInt(shift)) + ((u >> BigInt(shift - 1)) & 1n)
    }
  }
  return out
}

/** Choose the smallest word width that holds every rounded word. */
export function roundedParameters(a: ArrayLike<number>, type: number, bits: number): Parameters {
  const [, size] = format(type, bits, 1)
  const words = roundedWords(a, type, bits)
  return { bits, width: [1, 2, 4, 8].find(w => w === size || !words.some(word => atLeast(word, 8 * w)))! }
}

function reconstruct(word: Word, type: number, shift: number, size: number, view: DataView): number {
  if (shift && atLeast(word, 8 * size - shift)) throw Error("rounded word exceeds the declared type")
  let value: number
  if (size === 4) {
    view.setUint32(0, Number(word) * 2 ** shift, true)
    value = view.getFloat32(0, true)
  } else if (shift >= 11) {
    const w = Number(word)
    let hi: number, lo: number
    if (shift >= 32) { hi = w * 2 ** (shift - 32); lo = 0 }
    else { hi = Math.floor(w / 2 ** (32 - shift)); lo = (w - hi * 2 ** (32 - shift)) * 2 ** shift }
    view.setUint32(0, lo, true)
    view.setUint32(4, hi, true)
    value = view.getFloat64(0, true)
  } else {
    view.setBigUint64(0, BigInt(word) << BigInt(shift) & 0xFFFFFFFFFFFFFFFFn, true)
    value = view.getFloat64(0, true)
  }
  if (!Number.isFinite(value)) throw Error("rounded reconstruction is not finite")
  return value
}

export function encodeRounded(a: NumArray, type: number, p: Parameters): Uint8Array {
  const width = p.width as number
  const [shift, size] = format(type, p.bits as number, width)
  const words = roundedWords(a, type, p.bits as number)
  const raw = new Uint8Array(words.length * width)
  const out = new DataView(raw.buffer)
  const scratch = new DataView(new ArrayBuffer(8))
  for (const [i, word] of words.entries()) {
    if (atLeast(word, 8 * width)) throw Error("rounded word exceeds its word width")
    reconstruct(word, type, shift, size, scratch)
    if (width === 1) out.setUint8(i, Number(word))
    else if (width === 2) out.setUint16(i * 2, Number(word), true)
    else if (width === 4) out.setUint32(i * 4, Number(word), true)
    else out.setBigUint64(i * 8, BigInt(word), true)
  }
  return byteShuffle(raw, width)
}

export function decodeRounded(blob: Uint8Array, type: number, count: number, p: Parameters): NumArray {
  const width = p.width as number
  const [shift, size] = format(type, p.bits as number, width)
  if (blob.length !== count * width) throw Error("rounded byte count mismatch")
  const raw = byteUnshuffle(blob, width)
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength)
  const scratch = new DataView(new ArrayBuffer(8))
  const out = size === 4 ? new Float32Array(count) : new Float64Array(count)
  for (let i = 0; i < count; i++) {
    const word: Word = width === 1 ? view.getUint8(i) : width === 2 ? view.getUint16(i * 2, true)
      : width === 4 ? view.getUint32(i * 4, true) : view.getBigUint64(i * 8, true)
    out[i] = reconstruct(word, type, shift, size, scratch)
  }
  return out
}
