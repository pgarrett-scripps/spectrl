/** Array codecs keyed by compression CV accession tail. */

import { COMP_NUMLIN_ZLIB, COMP_NUMPIC_ZLIB, COMP_NUMSLOF_ZLIB, COMP_ZLIB, TYPE_FLOAT32, TYPE_INT32 } from "./cv.js";
import { decodeLinear, decodePic, decodeSlof, encodeLinear, encodePic, encodeSlof } from "./numpress.js";
import { zlibCompress, zlibDecompress } from "./zlibp.js";
import { DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, TYPE_FLOAT64 } from "./format.js";

/** A decoded numeric array; the kind reflects the declared binary data type. */
export type NumArray = Float64Array | Float32Array | Int32Array;

/**
 * Fixed points are whole numbers: the two defaults are, and a clamped slof fp is
 * floored to one. Rounding a clamped fp DOWN is the safe direction -- the clamp
 * exists to keep `log(max + 1) * fp` under the uint16 ceiling, and a smaller fp
 * only pushes that product further below it -- and it lets the descriptor carry
 * fp as a CBOR integer (3 or 5 bytes) instead of a float64 (9).
 */
export { DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP } from "./format.js";
const SLOF_UINT16_MAX = 65535.0;

/** Mirror the Python `_safe_slof_fp`: keep `log(max+1) * fp` within uint16. */
export function safeSlofFp(data: Float64Array, desiredFp: number): number {
  let maxVal = data.length > 0 ? data[0]! : 1.0;
  for (let i = 1; i < data.length; i++) if (data[i]! > maxVal) maxVal = data[i]!;
  maxVal = Math.max(maxVal, 1.0);
  const maxFp = SLOF_UINT16_MAX / (Math.log(maxVal + 1) + 1e-9);
  return Math.max(1, Math.floor(Math.min(desiredFp, maxFp)));
}

// raw little-endian bytes of the declared binary data type (default float64)
function encodeRaw(data: ArrayLike<number>, typeTail: number): Uint8Array {
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

function decodeRaw(raw: Uint8Array, typeTail: number): NumArray {
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

/** Encode `data` with the codec identified by `compTail`; `fp` is the numpress scale factor.
 * `typeTail` is only used by the raw (zlib) codec to preserve the declared data type. */
export function encodeArray(
  data: ArrayLike<number>,
  compTail: number,
  fp: number | null,
  typeTail = 1000523,
): Uint8Array {
  switch (compTail) {
    case COMP_NUMLIN_ZLIB:
      return zlibCompress(encodeLinear(data as Float64Array, fp ?? DEFAULT_NUMLIN_FP));
    case COMP_NUMSLOF_ZLIB:
      // callers pass a pre-clamped fp (see buildArrayBlobs); the re-clamp here
      // is a no-op safety net so a raw call can't overflow uint16.
      return zlibCompress(encodeSlof(data as Float64Array, safeSlofFp(data as Float64Array, fp ?? DEFAULT_NUMSLOF_FP)));
    case COMP_NUMPIC_ZLIB:
      return zlibCompress(encodePic(data as Float64Array));
    case COMP_ZLIB:
      return zlibCompress(encodeRaw(data, typeTail));
    default:
      throw new Error(`spectrl: no codec for compression tail ${compTail}`);
  }
}

export function decodeArray(blob: Uint8Array, compTail: number, typeTail = 1000523, maxBytes?: number): NumArray {
  switch (compTail) {
    case COMP_NUMLIN_ZLIB:
      return decodeLinear(zlibDecompress(blob, maxBytes));
    case COMP_NUMSLOF_ZLIB:
      return decodeSlof(zlibDecompress(blob, maxBytes));
    case COMP_NUMPIC_ZLIB:
      return decodePic(zlibDecompress(blob, maxBytes));
    case COMP_ZLIB:
      return decodeRaw(zlibDecompress(blob, maxBytes), typeTail);
    default:
      throw new Error(`spectrl: no codec for compression tail ${compTail}`);
  }
}
