/**
 * MS-Numpress codecs (linear, slof, pic), ported faithfully from the reference
 * C++ implementation (Teleman et al., ms-numpress). Byte-compatible with
 * pynumpress / the Python reference impl, so tokens round-trip across languages.
 *
 * Notes on the port:
 * - The fixed point is stored big-endian in the first 8 bytes (linear, slof).
 * - encodeInt/decodeInt operate on UNSIGNED 32-bit integers via `>>> 0`.
 * - 32-bit nibble packing matches the reference exactly.
 */

const FLOOR = Math.floor;

/**
 * Throw a catchable error on negative input. slof computes log(v + 1), which
 * breaks for negatives; linear and pic rounding of negatives differs across
 * implementations (truncation vs floor / unsigned wrap), so byte-identity
 * would be lost. Callers fall back to a lossless codec for such arrays.
 */
function rejectNegatives(data: Float64Array, codec: string): void {
  for (const v of data) {
    if (v < 0) {
      throw new Error(
        `MS-Numpress ${codec} codec cannot encode negative values; use a lossless codec for arrays that may contain negatives.`,
      );
    }
  }
}

// ── fixed point (big-endian float64) ──────────────────────────────────────────

function encodeFixedPoint(fixedPoint: number, out: Uint8Array, offset: number): void {
  const dv = new DataView(out.buffer, out.byteOffset + offset, 8);
  dv.setFloat64(0, fixedPoint, false); // big-endian
}

function decodeFixedPoint(data: Uint8Array): number {
  const dv = new DataView(data.buffer, data.byteOffset, 8);
  return dv.getFloat64(0, false);
}

// ── variable-length signed int as half-bytes (nibbles) ───────────────────────

/** Append the nibble encoding of unsigned-32 `x` into `half` at `offset`; return nibbles written. */
function encodeInt(x: number, half: Uint8Array, offset: number): number {
  x = x >>> 0;
  const mask = 0xf0000000;
  const init = (x & mask) >>> 0;
  let l: number;

  if (init === 0) {
    l = 8;
    for (let i = 0; i < 8; i++) {
      const m = (mask >>> (4 * i)) >>> 0;
      if (((x & m) >>> 0) !== 0) {
        l = i;
        break;
      }
    }
    half[offset] = l;
    for (let i = l; i < 8; i++) half[offset + 1 + i - l] = (x >>> (4 * (i - l))) & 0xf;
    return 1 + 8 - l;
  } else if (init === (mask >>> 0)) {
    l = 7;
    for (let i = 0; i < 8; i++) {
      const m = (mask >>> (4 * i)) >>> 0;
      if (((x & m) >>> 0) !== m) {
        l = i;
        break;
      }
    }
    half[offset] = l + 8;
    for (let i = l; i < 8; i++) half[offset + 1 + i - l] = (x >>> (4 * (i - l))) & 0xf;
    return 1 + 8 - l;
  } else {
    half[offset] = 0;
    for (let i = 0; i < 8; i++) half[offset + 1 + i] = (x >>> (4 * i)) & 0xf;
    return 9;
  }
}

interface IntState {
  di: number;
  half: number;
}

/** Decode one nibble-packed unsigned-32 int from `data`, advancing `st`.
 * Throws on truncated input rather than reading past the end. */
function decodeInt(data: Uint8Array, st: IntState): number {
  if (st.di >= data.length) throw new Error("numpress: truncated input");
  let head: number;
  if (st.half === 0) {
    head = data[st.di]! >> 4;
  } else {
    head = data[st.di]! & 0xf;
    st.di++;
  }
  st.half = 1 - st.half;

  let res = 0;
  let n: number;
  if (head <= 8) {
    n = head;
  } else {
    n = head - 8;
    const mask = 0xf0000000;
    for (let i = 0; i < n; i++) res = (res | ((mask >>> (4 * i)) >>> 0)) >>> 0;
  }

  if (n === 8) return res >>> 0;

  for (let i = n; i < 8; i++) {
    if (st.di >= data.length) throw new Error("numpress: truncated input");
    let hb: number;
    if (st.half === 0) {
      hb = data[st.di]! >> 4;
    } else {
      hb = data[st.di]! & 0xf;
      st.di++;
    }
    res = (res | (hb << ((i - n) * 4))) >>> 0;
    st.half = 1 - st.half;
  }
  return res >>> 0;
}

// little-endian 32-bit write using arithmetic (safe for values up to 2^32-1)
function writeU32LE(out: number[], v: number): void {
  v = v >>> 0 === v ? v : ((v % 0x100000000) + 0x100000000) % 0x100000000;
  out.push(v & 0xff, (FLOOR(v / 256) & 0xff) >>> 0, (FLOOR(v / 65536) & 0xff) >>> 0, (FLOOR(v / 16777216) & 0xff) >>> 0);
}

function readU32LE(data: Uint8Array, off: number): number {
  return data[off]! + data[off + 1]! * 256 + data[off + 2]! * 65536 + data[off + 3]! * 16777216;
}

// ── linear ────────────────────────────────────────────────────────────────────

export function validateLinearDomain(data: ArrayLike<number>, fp: number): void {
  if (!Number.isFinite(fp) || fp <= 0) throw new Error("Numpress linear fixed point must be finite and positive")
  let previous = 0
  let before = 0
  for (const [i, item] of Array.from(data).entries()) {
    const value = Math.floor(item * fp + 0.5)
    if (!Number.isSafeInteger(value) || value < 0 || value > Math.floor(Number.MAX_SAFE_INTEGER / 4)) {
      throw new Error("Numpress linear scaled values exceed the safe numeric range")
    }
    if (i < 2 && value > 0xffffffff) throw new Error("Numpress linear initial values exceed uint32, use a lossless codec or a smaller fixed point")
    const residual = value - 2 * previous + before
    if (i >= 2 && (residual < -2147483648 || residual > 2147483647)) {
      throw new Error("Numpress linear prediction residual exceeds int32, use a lossless codec")
    }
    before = previous
    previous = value
  }
}

export function validatePicDomain(data: ArrayLike<number>): void {
  for (const value of Array.from(data)) {
    if (!Number.isInteger(value) || value < 0 || value > 0xffffffff) {
      throw new Error("Numpress PIC requires whole numbers in the uint32 range")
    }
  }
}

export function encodeLinear(data: Float64Array, fixedPoint: number): Uint8Array {
  rejectNegatives(data, "linear")
  validateLinearDomain(data, fixedPoint)
  const fp = new Uint8Array(8);
  encodeFixedPoint(fixedPoint, fp, 0);
  const out: number[] = Array.from(fp);

  const n = data.length;
  if (n === 0) return Uint8Array.from(out);

  let i1 = FLOOR(data[0]! * fixedPoint + 0.5);
  writeU32LE(out, i1);
  if (n === 1) return Uint8Array.from(out);

  let i2 = FLOOR(data[1]! * fixedPoint + 0.5);
  writeU32LE(out, i2);

  const halfBytes = new Uint8Array(16);
  let halfByteCount = 0;

  for (let i = 2; i < n; i++) {
    const i0 = i1;
    i1 = i2;
    i2 = FLOOR(data[i]! * fixedPoint + 0.5);
    const extrapol = i1 + (i1 - i0);
    const diff = (i2 - extrapol) | 0; // 32-bit signed
    halfByteCount += encodeInt(diff >>> 0, halfBytes, halfByteCount);

    for (let hbi = 1; hbi < halfByteCount; hbi += 2) {
      out.push(((halfBytes[hbi - 1]! << 4) | (halfBytes[hbi]! & 0xf)) & 0xff);
    }
    if (halfByteCount % 2 !== 0) {
      halfBytes[0] = halfBytes[halfByteCount - 1]!;
      halfByteCount = 1;
    } else {
      halfByteCount = 0;
    }
  }
  if (halfByteCount === 1) out.push((halfBytes[0]! << 4) & 0xff);

  return Uint8Array.from(out);
}

export function decodeLinear(data: Uint8Array): Float64Array {
  const dataSize = data.length;
  if (dataSize === 8) return new Float64Array(0);
  if (dataSize < 8) throw new Error("numpress linear: truncated (no fixed point)");

  const fixedPoint = decodeFixedPoint(data);
  if (dataSize < 12) throw new Error("numpress linear: truncated (no first value)");

  const result: number[] = [];
  let i1 = readU32LE(data, 8);
  result.push(i1 / fixedPoint);
  if (dataSize === 12) return Float64Array.from(result);
  if (dataSize < 16) throw new Error("numpress linear: truncated (no second value)");

  let i2 = readU32LE(data, 12);
  result.push(i2 / fixedPoint);

  const st: IntState = { di: 16, half: 0 };
  while (st.di < dataSize) {
    if (st.di === dataSize - 1 && st.half === 1 && (data[st.di]! & 0xf) === 0) break;
    const i0 = i1;
    i1 = i2;
    const diff = decodeInt(data, st) | 0; // signed
    const extrapol = i1 + (i1 - i0);
    const y = extrapol + diff;
    result.push(y / fixedPoint);
    i2 = y;
  }
  return Float64Array.from(result);
}

// ── slof (short logged float) ─────────────────────────────────────────────────

export function encodeSlof(data: Float64Array, fixedPoint: number): Uint8Array {
  rejectNegatives(data, "slof");
  const out = new Uint8Array(8 + data.length * 2);
  encodeFixedPoint(fixedPoint, out, 0);
  let ri = 8;
  for (let i = 0; i < data.length; i++) {
    const x = FLOOR(Math.log(data[i]! + 1) * fixedPoint + 0.5) & 0xffff;
    out[ri++] = x & 0xff;
    out[ri++] = (x >> 8) & 0xff;
  }
  return out;
}

export function decodeSlof(data: Uint8Array): Float64Array {
  if (data.length < 8 || data.length % 2 !== 0) throw new Error("numpress slof: truncated (no fixed point)")
  const fixedPoint = decodeFixedPoint(data);
  const result = new Float64Array((data.length - 8) >> 1);
  let ri = 0;
  for (let i = 8; i + 1 < data.length; i += 2) {
    const x = (data[i]! | (data[i + 1]! << 8)) & 0xffff;
    result[ri++] = Math.exp(x / fixedPoint) - 1;
  }
  return result;
}

// ── pic (positive integer) ────────────────────────────────────────────────────

export function encodePic(data: Float64Array): Uint8Array {
  rejectNegatives(data, "pic")
  validatePicDomain(data)
  const out: number[] = [];
  const halfBytes = new Uint8Array(16);
  let halfByteCount = 0;
  for (let i = 0; i < data.length; i++) {
    const x = (FLOOR(data[i]! + 0.5) >>> 0) as number;
    halfByteCount += encodeInt(x, halfBytes, halfByteCount);
    for (let hbi = 1; hbi < halfByteCount; hbi += 2) {
      out.push(((halfBytes[hbi - 1]! << 4) | (halfBytes[hbi]! & 0xf)) & 0xff);
    }
    if (halfByteCount % 2 !== 0) {
      halfBytes[0] = halfBytes[halfByteCount - 1]!;
      halfByteCount = 1;
    } else {
      halfByteCount = 0;
    }
  }
  if (halfByteCount === 1) out.push((halfBytes[0]! << 4) & 0xff);
  return Uint8Array.from(out);
}

export function decodePic(data: Uint8Array): Float64Array {
  const dataSize = data.length;
  const result: number[] = [];
  const st: IntState = { di: 0, half: 0 };
  while (st.di < dataSize) {
    if (st.di === dataSize - 1 && st.half === 1 && (data[st.di]! & 0xf) === 0) break;
    result.push(decodeInt(data, st));
  }
  return Float64Array.from(result);
}
