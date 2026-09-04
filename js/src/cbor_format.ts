/**
 * spectrl.v1 CBOR container format (JS). Mirrors the Python `cbor_format`: a
 * single CBOR document carrying the header map plus array blobs embedded inline
 * as byte strings, with a required CRC-32/ISO-HDLC checksum over the ASCII text
 * before the checksum. Verification is independent of the CBOR library.
 */

import { b64urlDecode, b64urlEncode } from "./base64url.js";
import { buildArrayBlobs, canonicalSort, validateArrays } from "./canonical.js";
import { canonicalize, cborDecode, cborEncode, validateCborDocument } from "./cbor.js";
import { decodeArray, zstdDecodeBounded } from "./codecs.js";
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
  decodeTail,
  decodeUnitTail,
} from "./cv.js";
import { SpectrlDecodeError } from "./errors.js";
import { tokenChecksum } from "./checksum.js";
import {
  DESC_ARRAY,
  DESC_COMP,
  DESC_DATA,
  DESC_FP,
  DESC_NAME,
  DESC_TYPE,
  DESC_UNIT,
  buildHeaderMap,
  type Descriptor,
  type MsgMap,
  parseHeaderMap,
} from "./header.js";
import type { ArrayEncodingOption, DecodedSpectrum, InlineSpectrum } from "./model.js";
import { MAGIC } from "./token.js";
import { zlibDecompress } from "./zlibp.js";
import { MAX_ARRAY_LENGTH, MAX_BLOB_BYTES, MAX_SAFE_INTEGER, MAX_TOKEN_BYTES } from "./format.js";

/**
 * Drop free-text user params at spectrum and scan level.
 *
 * Header key 8 and scan-map key 2 are OPTIONAL and omitted when empty, so the
 * result is a conforming token that simply carries no vendor free-text.
 */
function withoutUserParams(spec: InlineSpectrum): InlineSpectrum {
  const scans = spec.scans?.map((s) => (s.userParams?.length ? { ...s, userParams: [] } : s));
  return { ...spec, userParams: [], ...(scans ? { scans } : {}) };
}

/** Encode an InlineSpectrum to a spectrl.v1 (CBOR) token string. */
export function encodeCbor(
  spec: InlineSpectrum,
  lossless = false,
  dropUserParams = false,
  arrayEncodings?: Record<string, ArrayEncodingOption>,
  allowUnsafeLossyCustom = false,
): string {
  validateArrays(spec);
  const sorted = canonicalSort(dropUserParams ? withoutUserParams(spec) : spec);

  const { blobs, descriptors } = buildArrayBlobs(
    sorted, lossless, undefined, undefined, arrayEncodings, allowUnsafeLossyCustom,
  );
  const descs: Descriptor[] = descriptors.map((d, i) => ({ ...d, data: blobs[i]! }));

  const doc = canonicalize(buildHeaderMap(sorted, descs));
  const raw = cborEncode(doc)
  if (raw.length > MAX_TOKEN_BYTES) throw new Error("CBOR payload exceeds the size limit")
  validateCborDocument(raw)
  const body = `${MAGIC}.${b64urlEncode(raw)}`
  return `${body}.${tokenChecksum(body)}`;
}

/** Hard ceiling on any single array blob's decompressed size (bytes). */

/** Rethrow anything that isn't already a SpectrlDecodeError as one. */
function asDecodeError(e: unknown, context: string): never {
  if (e instanceof SpectrlDecodeError) throw e;
  throw new SpectrlDecodeError(`${context}: ${e instanceof Error ? e.message : String(e)}`);
}

function validateDescriptor(d: unknown, seen: Set<string>): asserts d is MsgMap {
  if (!(d instanceof Map)) throw new SpectrlDecodeError("array descriptor must be a map");
  for (const key of [DESC_TYPE, DESC_ARRAY, DESC_COMP, DESC_DATA]) {
    if (!d.has(key)) throw new SpectrlDecodeError(`array descriptor is missing required key ${key}`);
  }
  const type = d.get(DESC_TYPE);
  const array = d.get(DESC_ARRAY);
  const comp = d.get(DESC_COMP);
  if (![type, array, comp].every((v) => typeof v === "number" && Number.isSafeInteger(v))) {
    throw new SpectrlDecodeError("array descriptor type, array, and comp must be integers");
  }
  if (![TYPE_FLOAT64, TYPE_FLOAT32, TYPE_INT32].includes(type as number)) {
    throw new SpectrlDecodeError(`unsupported array data type ${String(type)}`);
  }
  const supported = [
    COMP_NUMLIN_ZLIB,
    COMP_NUMLIN_ZSTD,
    COMP_NUMSLOF_ZLIB,
    COMP_NUMSLOF_ZSTD,
    COMP_NUMPIC_ZLIB,
    COMP_NUMPIC_ZSTD,
    COMP_ZLIB,
    COMP_ZSTD,
    COMP_BYTE_SHUFFLED_ZSTD,
  ];
  if (!supported.includes(comp as number)) {
    throw new SpectrlDecodeError(`unsupported compression codec ${String(comp)}`);
  }
  const rawCodecs = [COMP_ZLIB, COMP_ZSTD, COMP_BYTE_SHUFFLED_ZSTD];
  if (!rawCodecs.includes(comp as number) && type !== TYPE_FLOAT64) {
    throw new SpectrlDecodeError("Numpress descriptors must declare float64");
  }
  const fpCodecs = [COMP_NUMLIN_ZLIB, COMP_NUMLIN_ZSTD, COMP_NUMSLOF_ZLIB, COMP_NUMSLOF_ZSTD];
  if (d.has(DESC_FP) &&
      (typeof d.get(DESC_FP) !== "number" || !Number.isSafeInteger(d.get(DESC_FP)) ||
       (d.get(DESC_FP) as number) <= 0 || (d.get(DESC_FP) as number) > MAX_SAFE_INTEGER)) {
    throw new SpectrlDecodeError("array descriptor fp must be a positive integer");
  }
  if (fpCodecs.includes(comp as number) && !d.has(DESC_FP)) {
    throw new SpectrlDecodeError("Numpress linear and slof descriptors require fp");
  }
  if ((comp === COMP_NUMPIC_ZLIB || comp === COMP_NUMPIC_ZSTD || rawCodecs.includes(comp as number)) && d.has(DESC_FP)) {
    throw new SpectrlDecodeError("array descriptor fp is not valid for this codec");
  }
  if (!(d.get(DESC_DATA) instanceof Uint8Array)) {
    throw new SpectrlDecodeError("array descriptor data must be a byte string");
  }
  const name = d.get(DESC_NAME);
  if (array === ARRAY_NON_STANDARD) {
    if (typeof name !== "string" || name.length === 0) {
      throw new SpectrlDecodeError("a non-standard array requires a non-empty name");
    }
  } else if (name !== undefined) {
    throw new SpectrlDecodeError("a standard array descriptor must not carry a name");
  }
  if (d.has(DESC_UNIT)) {
    try {
      const raw = d.get(DESC_UNIT);
      const valid = (typeof raw === "number" && Number.isSafeInteger(raw) && raw >= 0)
        || (typeof raw === "string" && /^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$/.test(raw))
        || (Array.isArray(raw) && raw.length === 2 && typeof raw[0] === "string"
          && /^[A-Za-z][A-Za-z0-9]*$/.test(raw[0]) && typeof raw[1] === "number"
          && Number.isSafeInteger(raw[1]) && raw[1] >= 0);
      if (!valid) throw new Error("bad unit form");
      decodeUnitTail(raw as number | [string, number] | string);
    } catch {
      throw new SpectrlDecodeError("array descriptor unit must be a valid CV unit accession");
    }
  }
  const identity = `${String(array)}\u0000${name === undefined ? "" : String(name)}`;
  if (seen.has(identity)) throw new SpectrlDecodeError(`duplicate array descriptor ${identity}`);
  seen.add(identity);
}

function validateNumpressFp(d: MsgMap, maxBytes: number): void {
  const comp = d.get(DESC_COMP) as number;
  const linear = comp === COMP_NUMLIN_ZLIB || comp === COMP_NUMLIN_ZSTD;
  const slof = comp === COMP_NUMSLOF_ZLIB || comp === COMP_NUMSLOF_ZSTD;
  if (!linear && !slof) return;
  const raw = comp === COMP_NUMLIN_ZLIB || comp === COMP_NUMSLOF_ZLIB
    ? zlibDecompress(d.get(DESC_DATA) as Uint8Array, maxBytes)
    : zstdDecodeBounded(d.get(DESC_DATA) as Uint8Array, maxBytes);
  if (raw.length < 8) throw new SpectrlDecodeError("Numpress stream is missing its fixed point");
  const embedded = new DataView(raw.buffer, raw.byteOffset, 8).getFloat64(0, false);
  const declared = d.get(DESC_FP) as number;
  if (!Number.isFinite(embedded) || embedded <= 0 || embedded !== declared) {
    throw new SpectrlDecodeError(`Numpress fixed point mismatch: descriptor declares ${declared}, stream contains ${embedded}`);
  }
}

function validateHeaderShape(h: MsgMap): void {
  if (!h.has(0)) throw new SpectrlDecodeError("spectrl header is missing defaultArrayLength (key 0)");
  const checks: Array<[number, (v: unknown) => boolean, string]> = [
    [1, (v) => typeof v === "string", "string"],
    [2, (v) => v instanceof Map, "map"],
    [3, (v) => v instanceof Map, "map"],
    [4, Array.isArray, "array"],
    [5, Array.isArray, "array"],
    [6, Array.isArray, "array"],
    [7, (v) => typeof v === "string", "string"],
    [8, Array.isArray, "array"],
  ];
  for (const [key, check, label] of checks) {
    if (h.has(key) && !check(h.get(key))) throw new SpectrlDecodeError(`spectrl header key ${key} must be ${label}`);
  }
}

/**
 * Decode a spectrl.v1 token, verifying the trailing CRC-32 checksum.
 * Throws SpectrlDecodeError on any malformed, corrupted, or unsupported input.
 */
export function readTokenDocument(token: string): { doc: MsgMap, decoded: DecodedSpectrum } {
  if (typeof token !== "string" || token.length > Math.ceil(MAX_TOKEN_BYTES * 4 / 3) + MAGIC.length + 10) throw new SpectrlDecodeError("invalid token type or size")
  const prefix = `${MAGIC}.`
  if (!token.startsWith(prefix)) throw new SpectrlDecodeError(`Not a ${MAGIC} token`);
  const parts = token.slice(prefix.length).split(".");
  if (parts.length !== 2) {
    throw new SpectrlDecodeError("a spectrl token has exactly four '.'-separated parts");
  }
  const payload = parts[0]!;
  const stored = parts[1]!;
  if (!/^[0-9a-f]{8}$/.test(stored)) {
    throw new SpectrlDecodeError("spectrl token checksum must be eight lowercase hexadecimal characters");
  }
  const expected = tokenChecksum(`${MAGIC}.${payload}`);
  if (expected !== stored) {
    throw new SpectrlDecodeError(
      `spectrl token checksum mismatch: stored=${stored}, computed=${expected}. Token may be corrupted.`,
    );
  }

  const raw = b64urlDecode(payload);
  if (raw.length > MAX_TOKEN_BYTES) throw new SpectrlDecodeError(`CBOR payload exceeds ${MAX_TOKEN_BYTES} bytes`);
  let doc: unknown;
  try {
    validateCborDocument(raw);
    doc = cborDecode(raw);
  } catch (e) {
    asDecodeError(e, "spectrl payload is not valid CBOR");
  }
  if (!(doc instanceof Map)) throw new SpectrlDecodeError("spectrl payload is not a CBOR map");
  const h = doc as MsgMap;
  validateHeaderShape(h);

  let decoded: DecodedSpectrum;
  try {
    decoded = parseHeaderMap(h).decoded;
  } catch (e) {
    asDecodeError(e, "malformed spectrl header");
  }
  const n = decoded.defaultArrayLength;
  if (typeof n !== "number" || !Number.isInteger(n) || n < 0 || n > MAX_ARRAY_LENGTH) {
    throw new SpectrlDecodeError(`invalid declared array length (key 0): ${String(n)}`);
  }
  decoded.checksum = stored;

  const descriptors = h.get(6) ?? []
  if (!Array.isArray(descriptors)) throw new SpectrlDecodeError("binaryDataArrayList must be an array")
  const seen = new Set<string>()
  for (const descriptor of descriptors) validateDescriptor(descriptor, seen)
  return { doc: h, decoded }
}

export function decodeCbor(token: string): DecodedSpectrum {
  const { doc: h, decoded } = readTokenDocument(token)
  const n = decoded.defaultArrayLength

  // Bound decompression by the declared array length (float64 worst case plus
  // numpress framing slack) so a small token cannot expand without limit.
  const maxBytes = Math.min(64 + 16 * n, MAX_BLOB_BYTES);

  const rawDescs = h.get(6) ?? [];
  if (!Array.isArray(rawDescs)) throw new SpectrlDecodeError("binaryDataArrayList (key 6) must be an array");
  const descs = rawDescs as unknown[];
  const seenArrays = new Set<string>();
  for (const d of descs) {
    validateDescriptor(d, seenArrays);
    let arr: ReturnType<typeof decodeArray>;
    let tail: number;
    let name: string | undefined;
    let unit: string | undefined;
    try {
      validateNumpressFp(d, maxBytes);
      const comp = d.get(DESC_COMP) as number;
      const type = (d.get(DESC_TYPE) as number | undefined) ?? TYPE_FLOAT64;
      const blob = new Uint8Array(d.get(DESC_DATA) as Uint8Array);
      arr = decodeArray(blob, comp, type, maxBytes);
      tail = d.get(DESC_ARRAY) as number;
      name = d.get(DESC_NAME) as string | undefined;
      unit = d.has(DESC_UNIT)
        ? decodeUnitTail(d.get(DESC_UNIT) as number | [string, number] | string)
        : undefined;
    } catch (e) {
      asDecodeError(e, "malformed array blob");
    }
    if (arr.length !== n) {
      throw new SpectrlDecodeError(`array ${tail} decoded to ${arr.length} values, but the header declares ${n} (key 0)`);
    }
    for (const value of arr) {
      if (!Number.isFinite(value)) throw new SpectrlDecodeError(`array ${tail} contains NaN or infinite values`);
      if (tail === ARRAY_MZ && value < 0) throw new SpectrlDecodeError("m/z array contains negative values");
    }
    if (tail === ARRAY_MZ) decoded.mz = arr as Float64Array;
    else if (tail === ARRAY_INTENSITY) decoded.intensity = arr as Float64Array;
    else if (tail === ARRAY_CHARGE) decoded.charge = arr as Float64Array;
    else if (tail === ARRAY_NON_STANDARD) {
      Object.defineProperty(decoded.extraArrays, name ?? decodeTail(tail), { value: arr, enumerable: true, writable: true, configurable: true })
    } else {
      decoded.extraArrays[decodeTail(tail)] = arr;
    }
    if (unit !== undefined) {
      const key = tail === ARRAY_MZ ? "mz" : tail === ARRAY_INTENSITY ? "intensity" : tail === ARRAY_CHARGE ? "charge"
        : tail === ARRAY_NON_STANDARD ? (name ?? decodeTail(tail)) : decodeTail(tail);
      Object.defineProperty(decoded.arrayUnits, key, { value: unit, enumerable: true, writable: true, configurable: true })
    }
  }

  return decoded;
}
