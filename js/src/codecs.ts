/** Typed numeric words and byte shuffle helpers. */
import { TYPE_FLOAT32, TYPE_FLOAT64, TYPE_INT32 } from "./cv.js"

/** A decoded numeric array; the kind reflects the declared binary data type. */
export type NumArray = Float64Array | Float32Array | Int32Array;

// raw little-endian bytes of the declared binary data type (default float64)
export function encodeRaw(data: ArrayLike<number>, typeTail: number): Uint8Array {
  const n = data.length;
  if (typeTail === TYPE_INT32) {
    const out = new Uint8Array(n * 4);
    const dv = new DataView(out.buffer);
    for (let i = 0; i < n; i++) dv.setInt32(i * 4, Math.trunc(data[i]!), true);
    return out;
  }
  if (typeTail === TYPE_FLOAT32) {
    const out = new Uint8Array(n * 4);
    const dv = new DataView(out.buffer);
    for (let i = 0; i < n; i++) dv.setFloat32(i * 4, data[i]!, true);
    return out;
  }
  const out = new Uint8Array(n * 8);
  const dv = new DataView(out.buffer);
  for (let i = 0; i < n; i++) dv.setFloat64(i * 8, data[i]!, true);
  return out;
}

export function decodeRaw(raw: Uint8Array, typeTail: number): NumArray {
  if (typeTail !== TYPE_INT32 && typeTail !== TYPE_FLOAT32 && typeTail !== TYPE_FLOAT64) {
    throw new Error(`unsupported binary data type tail ${typeTail}`);
  }
  const itemSize = typeTail === TYPE_INT32 || typeTail === TYPE_FLOAT32 ? 4 : 8;
  if (raw.length % itemSize !== 0) {
    throw new Error(`raw array blob length ${raw.length} is not a multiple of the ${itemSize}-byte data type`);
  }
  const dv = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  if (typeTail === TYPE_INT32) {
    const n = raw.length >> 2;
    const out = new Int32Array(n);
    for (let i = 0; i < n; i++) out[i] = dv.getInt32(i * 4, true);
    return out;
  }
  if (typeTail === TYPE_FLOAT32) {
    const n = raw.length >> 2;
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = dv.getFloat32(i * 4, true);
    return out;
  }
  const n = raw.length >> 3;
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = dv.getFloat64(i * 8, true);
  return out;
}

export function byteShuffle(raw: Uint8Array, itemSize: number): Uint8Array {
  const n = raw.length / itemSize;
  const out = new Uint8Array(raw.length);
  for (let byte = 0; byte < itemSize; byte++) {
    for (let i = 0; i < n; i++) out[byte * n + i] = raw[i * itemSize + byte]!;
  }
  return out;
}

export function byteUnshuffle(shuffled: Uint8Array, itemSize: number): Uint8Array {
  if (shuffled.length % itemSize !== 0) throw new Error(`shuffled array blob length is not a multiple of ${itemSize}`);
  const n = shuffled.length / itemSize;
  const out = new Uint8Array(shuffled.length);
  for (let byte = 0; byte < itemSize; byte++) {
    for (let i = 0; i < n; i++) out[i * itemSize + byte] = shuffled[byte * n + i]!;
  }
  return out;
}
