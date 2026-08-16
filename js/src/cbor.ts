/**
 * CBOR for spectrl2: standard encode/decode via the cbor-x library, plus a raw
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

export function cborEncode(value: unknown): Uint8Array {
  return new Uint8Array(codec.encode(value));
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
  return codec.decode(bytes);
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

  if (mt === 0 || mt === 1 || mt === 7) return pos;
  if (mt === 2 || mt === 3) {
    const end = pos + arg;
    if (end > buf.length) throw new Error("truncated CBOR string");
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
      pos = validateItem(buf, pos, depth + 1, budget);
      const identity = keyIdentity(cborDecode(buf.subarray(keyStart, pos)));
      if (seen.has(identity)) throw new Error(`duplicate CBOR map key ${identity}`);
      seen.add(identity);
      pos = validateItem(buf, pos, depth + 1, budget);
    }
    return pos;
  }
  if (mt === 6) return validateItem(buf, pos, depth + 1, budget);
  throw new Error(`invalid CBOR major type ${mt}`);
}

/** Validate raw structure before cbor-x can collapse duplicate keys. */
export function validateCborDocument(bytes: Uint8Array): void {
  const end = validateItem(bytes, 0, 0, { value: 0 });
  if (end !== bytes.length) throw new Error("trailing bytes after the CBOR document");
}
