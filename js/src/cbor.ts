/**
 * CBOR for spectrl.v3: standard encode/decode via the cbor-x library, plus a raw
 * validation pass that rejects duplicate map keys, over-deep nesting, and
 * trailing bytes before the library ever parses the document.
 */

import { Encoder } from "cbor-x";
import { MAX_CBOR_DEPTH, MAX_CBOR_ITEMS } from "./format.js";

// Plain, standard CBOR: no cbor-x record extension, Maps stay Maps (not objects),
// and typed arrays encode as byte strings (no tag). variableMapSize emits minimal
// map headers so they match `mapHeader` below.
const codec = new Encoder({
  useRecords: false,
  mapsAsObjects: false,
  tagUint8Array: false,
  variableMapSize: true,
});
const utf8 = new TextDecoder("utf-8", { fatal: true })

export function cborEncode(value: unknown): Uint8Array {
  return canonicalNumbers(new Uint8Array(codec.encode(value)));
}

/** Canonical numeric values without rounding or touching blob bytes.
 * cbor-x has no shortest-exact-float option (including binary16).
 */
function canonicalNumbers(bytes: Uint8Array): Uint8Array {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const float32 = new DataView(new ArrayBuffer(4));
  let read = 0, write = 0;
  while (read < bytes.length) {
    const start = read;
    const initial = bytes[read++]!;
    const major = initial >> 5, ai = initial & 31;
    const width = ai < 24 ? 0 : ai === 24 ? 1 : ai === 25 ? 2 : ai === 26 ? 4 : ai === 27 ? 8 : 0;
    if (initial === 0xfb) {
      const value = view.getFloat64(read);
      read += 8;
      // cbor-x emits safe integers outside its uint32 range as float64.
      // Use the integer representation, as Python does, including for map keys.
      if (Number.isSafeInteger(value)) {
        const major = value < 0 ? 0x20 : 0;
        const argument = value < 0 ? -1 - value : value;
        if (argument < 24) bytes[write++] = major | argument;
        else if (argument <= 0xff) {
          bytes[write++] = major | 24; bytes[write++] = argument;
        } else if (argument <= 0xffff) {
          bytes[write++] = major | 25; view.setUint16(write, argument); write += 2;
        } else if (argument <= 0xffffffff) {
          bytes[write++] = major | 26; view.setUint32(write, argument); write += 4;
        } else {
          bytes[write++] = major | 27; view.setBigUint64(write, BigInt(argument)); write += 8;
        }
        continue;
      }
      if (Number.isFinite(value) && Object.is(Math.fround(value), value)) {
        float32.setFloat32(0, value);
        const bits = float32.getUint32(0);
        const sign = (bits >>> 16) & 0x8000;
        const exponent = ((bits >>> 23) & 255) - 127;
        const fraction = bits & 0x7fffff;
        let half: number | undefined;
        if (value === 0) half = sign;
        else if (exponent >= -14 && exponent <= 15 && (fraction & 0x1fff) === 0) {
          half = sign | ((exponent + 15) << 10) | (fraction >>> 13);
        } else if (exponent >= -24 && exponent < -14) {
          const subnormal = (fraction | 0x800000) / 2 ** (-exponent - 1);
          if (Number.isInteger(subnormal)) half = sign | subnormal;
        }
        if (half !== undefined) {
          bytes[write++] = 0xf9;
          view.setUint16(write, half);
          write += 2;
        } else {
          bytes[write++] = 0xfa;
          view.setFloat32(write, value);
          write += 4;
        }
        continue;
      }
    } else {
      let length = ai;
      if (major === 2 || major === 3) {
        if (width) {
          length = 0;
          for (let i = 0; i < width; i++) length = length * 256 + bytes[read + i]!;
        }
      }
      read += width;
      // Containers are visited sequentially; strings and binary arrays are opaque.
      if (major === 2 || major === 3) read += length;
    }
    bytes.copyWithin(write, start, read);
    write += read - start;
  }
  return write === bytes.length ? bytes : bytes.slice(0, write);
}

function compareEncodedKeys(a: Uint8Array, b: Uint8Array): number {
  // Canonical key order (matches Python cbor2 canonical=True): shorter encoded
  // key first, then bytewise lexicographic. For this format's key space
  // (small ints and short strings) this coincides with RFC 8949 §4.2.
  if (a.length !== b.length) return a.length - b.length;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return a[i]! - b[i]!;
  }
  return 0;
}

/** Recursively sort every Map's entries into canonical key order, so the
 * emitted document satisfies the deterministic-encoding requirement of §8. */
export function canonicalize(value: unknown): unknown {
  if (value instanceof Map) {
    const entries = [...value.entries()].map(
      ([k, v]) => [k, canonicalize(v), cborEncode(k)] as [unknown, unknown, Uint8Array],
    );
    entries.sort((x, y) => compareEncodedKeys(x[2], y[2]));
    return new Map(entries.map(([k, v]) => [k, v]));
  }
  if (Array.isArray(value)) return value.map(canonicalize);
  return value;
}

export function cborDecode(bytes: Uint8Array): unknown {
  return safeIntegerValues(codec.decode(bytes));
}

// cbor-x returns 64-bit CBOR integers as bigint. Convert only after checking the
// exact range; its int64AsNumber option truncates large negative integers in 1.6.4.
function safeIntegerValues(value: any): any {
  if (typeof value === "bigint") {
    if (value < BigInt(Number.MIN_SAFE_INTEGER) || value > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw Error("CBOR integer exceeds the safe integer range")
    }
    return Number(value)
  }
  if (value instanceof Map) return new Map([...value].map(([k, v]) => [safeIntegerValues(k), safeIntegerValues(v)]))
  if (Array.isArray(value)) return value.map(safeIntegerValues)
  return value
}

function keyIdentity(key: unknown): string {
  if (key === null) return "null";
  const t = typeof key;
  if (t === "number" || t === "string" || t === "boolean" || t === "bigint") return `${t}:${String(key)}`;
  throw new Error("CBOR map keys must be primitive values");
}

function validateItem(buf: Uint8Array, start: number, depth: number, budget: { value: number }): number {
  if (depth > MAX_CBOR_DEPTH) throw new Error(`CBOR nesting exceeds ${MAX_CBOR_DEPTH}`);
  if (start >= buf.length) throw new Error("truncated CBOR item");
  if (++budget.value > MAX_CBOR_ITEMS) throw new Error(`CBOR item count exceeds ${MAX_CBOR_ITEMS}`);

  const ib = buf[start]!;
  const mt = ib >> 5;
  const ai = ib & 0x1f;
  let pos = start + 1;
  let arg = 0;
  let width = 0;
  if (ai < 24) arg = ai;
  else if (ai === 24) width = 1;
  else if (ai === 25) width = 2;
  else if (ai === 26) width = 4;
  else if (ai === 27) width = 8;
  else throw new Error("indefinite-length and reserved CBOR items are not supported");
  if (pos + width > buf.length) throw new Error("truncated CBOR length");
  for (let i = 0; i < width; i++) {
    arg = arg * 256 + buf[pos + i]!;
    if (mt !== 7 && !Number.isSafeInteger(arg)) {
      throw new Error("CBOR argument exceeds JavaScript's safe integer range");
    }
  }
  pos += width;

  if (mt === 0 || mt === 1) {
    if (!Number.isSafeInteger(mt === 1 ? -1 - arg : arg)) throw new Error("CBOR integer exceeds the safe integer range")
    return pos
  }
  if (mt === 7) {
    if (![20, 21, 22, 25, 26, 27].includes(ai)) throw new Error("unsupported CBOR simple value")
    if (ai >= 25) {
      const value = cborDecode(buf.subarray(start, pos)) as number
      if (!Number.isFinite(value)) throw new Error("CBOR numbers must be finite")
      // Section 1 requires writers to encode every mathematically integral safe
      // value as a CBOR integer, both signs of zero included. Enforcing that on
      // read keeps one wire form per value. It also lets this reader reject
      // `3.0` where an integer is required, which it could not otherwise do:
      // after parsing, JavaScript cannot tell 3.0 from 3.
      if (Number.isSafeInteger(value)) throw new Error("integral values within the safe integer range must be CBOR integers")
    }
    return pos
  }
  if (mt === 2 || mt === 3) {
    const end = pos + arg;
    if (end > buf.length) throw new Error("truncated CBOR string");
    if (mt === 3) utf8.decode(buf.subarray(pos, end))
    return end;
  }
  if (mt === 4) {
    if (arg > MAX_CBOR_ITEMS) throw new Error("CBOR array is too large");
    for (let i = 0; i < arg; i++) pos = validateItem(buf, pos, depth + 1, budget);
    return pos;
  }
  if (mt === 5) {
    if (arg > MAX_CBOR_ITEMS) throw new Error("CBOR map is too large");
    const seen = new Set<string>();
    for (let i = 0; i < arg; i++) {
      const keyStart = pos;
      if (pos >= buf.length || ![0, 1, 3].includes(buf[pos]! >> 5)) throw new Error("CBOR map keys must be integers or text")
      pos = validateItem(buf, pos, depth + 1, budget);
      const identity = keyIdentity(cborDecode(buf.subarray(keyStart, pos)));
      if (seen.has(identity)) throw new Error(`duplicate CBOR map key ${identity}`);
      seen.add(identity);
      pos = validateItem(buf, pos, depth + 1, budget);
    }
    return pos;
  }
  if (mt === 6) throw new Error("CBOR tags are not supported")
  throw new Error(`invalid CBOR major type ${mt}`);
}

/** Validate raw structure before cbor-x can collapse duplicate keys. */
export function validateCborDocument(bytes: Uint8Array): void {
  const end = validateItem(bytes, 0, 0, { value: 0 });
  if (end !== bytes.length) throw new Error("trailing bytes after the CBOR document");
}
