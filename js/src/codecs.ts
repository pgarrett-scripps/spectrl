/** Array codecs keyed by compression CV accession tail. */

import {
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
  TYPE_INT32,
} from "./cv.js";
import { decodeLinear, decodePic, decodeSlof, encodeLinear, encodePic, encodeSlof } from "./numpress.js";
import { zlibCompress, zlibDecompress } from "./zlibp.js";
import { DEFAULT_NUMLIN_FP, DEFAULT_NUMSLOF_FP, TYPE_FLOAT64 } from "./format.js";

export interface ZstdBackend {
  compress(data: Uint8Array, level: number): Uint8Array;
  decompress(data: Uint8Array): Uint8Array;
}

let zstdBackend: ZstdBackend | undefined;

/** Register the optional synchronous zstd implementation used by the zstd subpath. */
export function registerZstdBackend(backend: ZstdBackend): void {
  zstdBackend = backend;
}

function requireZstdBackend(): ZstdBackend {
  if (zstdBackend === undefined) {
    throw new Error(
      "zstd support is not installed; call installZstd() from '@spectrl-ms/spectrl/zstd' before encoding or decoding zstd arrays",
    );
  }
  return zstdBackend;
}

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

function byteShuffle(raw: Uint8Array, itemSize: number): Uint8Array {
  const n = raw.length / itemSize;
  const out = new Uint8Array(raw.length);
  for (let byte = 0; byte < itemSize; byte++) {
    for (let i = 0; i < n; i++) out[byte * n + i] = raw[i * itemSize + byte]!;
  }
  return out;
}

function byteUnshuffle(shuffled: Uint8Array, itemSize: number): Uint8Array {
  if (shuffled.length % itemSize !== 0) throw new Error(`shuffled array blob length is not a multiple of ${itemSize}`);
  const n = shuffled.length / itemSize;
  const out = new Uint8Array(shuffled.length);
  for (let byte = 0; byte < itemSize; byte++) {
    for (let i = 0; i < n; i++) out[i * itemSize + byte] = shuffled[byte * n + i]!;
  }
  return out;
}

function zstdFrameContentSize(blob: Uint8Array): number | null {
  if (blob.length < 5 || blob[0] !== 0x28 || blob[1] !== 0xb5 || blob[2] !== 0x2f || blob[3] !== 0xfd) {
    throw new Error("invalid zstd frame magic");
  }
  const descriptor = blob[4]!;
  const singleSegment = (descriptor & 0x20) !== 0;
  const dictSize = [0, 1, 2, 4][descriptor & 0x03]!;
  const sizeFlag = descriptor >>> 6;
  const sizeBytes = sizeFlag === 0 ? (singleSegment ? 1 : 0) : sizeFlag === 1 ? 2 : sizeFlag === 2 ? 4 : 8;
  let offset = 5 + (singleSegment ? 0 : 1) + dictSize;
  if (offset + sizeBytes > blob.length) throw new Error("truncated zstd frame header");
  let size = 0n;
  for (let i = 0; i < sizeBytes; i++) size |= BigInt(blob[offset + i]!) << BigInt(i * 8);
  if (sizeBytes === 2) size += 256n;
  if (size > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("zstd frame content size is too large");
  offset += sizeBytes;
  let lastBlock = false;
  while (!lastBlock) {
    if (offset + 3 > blob.length) throw new Error("truncated zstd block header");
    const header = blob[offset]! | (blob[offset + 1]! << 8) | (blob[offset + 2]! << 16);
    offset += 3;
    lastBlock = (header & 1) !== 0;
    const blockType = (header >>> 1) & 0x03;
    if (blockType === 3) throw new Error("reserved zstd block type");
    const blockSize = header >>> 3;
    offset += blockType === 1 ? 1 : blockSize;
    if (offset > blob.length) throw new Error("truncated zstd block");
  }
  if ((descriptor & 0x04) !== 0) offset += 4;
  if (offset !== blob.length) throw new Error("trailing data after zstd frame");
  return sizeBytes === 0 ? null : Number(size);
}

export function zstdDecodeBounded(blob: Uint8Array, maxBytes?: number): Uint8Array {
  const declared = zstdFrameContentSize(blob);
  if (maxBytes !== undefined && (declared === null || declared > maxBytes)) {
    throw new Error(declared === null ? "zstd frame omits its content size" : `zstd output exceeds the ${maxBytes}-byte limit`);
  }
  const raw = requireZstdBackend().decompress(blob);
  if (maxBytes !== undefined && raw.length > maxBytes) throw new Error(`zstd output exceeds the ${maxBytes}-byte limit`);
  if (declared !== null && raw.length !== declared) throw new Error("zstd frame content size mismatch");
  return raw;
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
    case COMP_ZSTD:
      return requireZstdBackend().compress(encodeRaw(data, typeTail), 3);
    case COMP_BYTE_SHUFFLED_ZSTD: {
      const itemSize = typeTail === TYPE_FLOAT32 || typeTail === TYPE_INT32 ? 4 : 8;
      return requireZstdBackend().compress(byteShuffle(encodeRaw(data, typeTail), itemSize), 3);
    }
    case COMP_NUMLIN_ZSTD:
      return requireZstdBackend().compress(encodeLinear(data as Float64Array, fp ?? DEFAULT_NUMLIN_FP), 3);
    case COMP_NUMSLOF_ZSTD:
      return requireZstdBackend().compress(
        encodeSlof(data as Float64Array, safeSlofFp(data as Float64Array, fp ?? DEFAULT_NUMSLOF_FP)),
        3,
      );
    case COMP_NUMPIC_ZSTD:
      return requireZstdBackend().compress(encodePic(data as Float64Array), 3);
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
    case COMP_ZSTD:
      return decodeRaw(zstdDecodeBounded(blob, maxBytes), typeTail);
    case COMP_BYTE_SHUFFLED_ZSTD: {
      const itemSize = typeTail === TYPE_FLOAT32 || typeTail === TYPE_INT32 ? 4 : 8;
      return decodeRaw(byteUnshuffle(zstdDecodeBounded(blob, maxBytes), itemSize), typeTail);
    }
    case COMP_NUMLIN_ZSTD:
      return decodeLinear(zstdDecodeBounded(blob, maxBytes));
    case COMP_NUMSLOF_ZSTD:
      return decodeSlof(zstdDecodeBounded(blob, maxBytes));
    case COMP_NUMPIC_ZSTD:
      return decodePic(zstdDecodeBounded(blob, maxBytes));
    default:
      throw new Error(`spectrl: no codec for compression tail ${compTail}`);
  }
}
