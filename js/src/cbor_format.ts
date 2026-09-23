/** V3 CBOR framing with strict validation and bounded array decoding. */
import { b64urlDecode, b64urlEncode } from "./base64url.js"
import { buildArrayBlobs, canonicalSort, validateArrays } from "./canonical.js"
import { canonicalize, cborDecode, cborEncode, validateCborDocument } from "./cbor.js"
import { SpectrlDecodeError } from "./errors.js"
import { tokenChecksum } from "./checksum.js"
import { buildHeaderMap, parseHeaderMap, shape, type Descriptor, type MsgMap, DESC_TYPE } from "./header.js"
import type { ArrayEncodingOption, DecodedSpectrum, InlineSpectrum } from "./model.js"
import { MAGIC } from "./token.js"
import { MAX_ARRAY_LENGTH, MAX_TOKEN_BYTES, TYPE_FLOAT64 } from "./format.js"
import { resolveDecodeLimits, UNLIMITED_DECODE_LIMITS, type DecodeLimits } from "./limits.js"
import { decodePipeline, descriptor, operation, operationKey, encodings } from "./pipeline.js"
import { validateExtensions, withoutUserParams } from "./context.js"
import { decodeTail } from "./cv.js"
import { compressPayload, decompressPayload, type PayloadCompression } from "./payload.js"

export function encodeCbor(spec: InlineSpectrum, lossless = false, dropUserParams = false,
  arrayEncodings?: Record<string, ArrayEncodingOption>, allowUnsafeLossyCustom = false, compression: PayloadCompression = "zlib"): string {
  if ("interp" in spec || "interpretation" in spec) throw Error("v3 does not accept identification fields")
  validateArrays(spec)
  const sorted = canonicalSort(dropUserParams ? withoutUserParams(spec) : spec)
  const { blobs, descriptors } = buildArrayBlobs(sorted, lossless, undefined, undefined, arrayEncodings, allowUnsafeLossyCustom, compression)
  const raw = cborEncode(canonicalize(buildHeaderMap(sorted, descriptors.map((d, i) => ({ ...d, data: blobs[i]! })))))
  if (raw.length > MAX_TOKEN_BYTES) throw Error("CBOR payload exceeds the size limit")
  validateCborDocument(raw)
  const token = framePayload(raw, compression)
  // Verify what we just produced against the wire ceilings only: a caller
  // encoding a legitimately huge spectrum is not the untrusted-input case the
  // default budgets exist for.
  readTokenDocument(token, UNLIMITED_DECODE_LIMITS)
  return token
}
export function framePayload(raw: Uint8Array, compression: PayloadCompression = "zlib"): string {
  const [mode, packed] = compressPayload(raw, compression, MAX_TOKEN_BYTES)
  const body = `${MAGIC}.${mode}.${b64urlEncode(packed)}`
  return `${body}.${tokenChecksum(body)}`
}
function asDecodeError(e: unknown, context: string): never {
  if (e instanceof SpectrlDecodeError) throw e
  throw new SpectrlDecodeError(`${context}: ${e instanceof Error ? e.message : String(e)}`)
}
function validateDescriptor(d: unknown, seen: Set<string>): asserts d is MsgMap {
  try {
    shape(d, [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11])
    for (const key of [0, 1, 2, 5, 7]) if (!d.has(key)) throw Error(`missing descriptor key ${key}`)
    if (![1000521, 1000523, 1000519].includes(d.get(0) as number)) throw Error("unsupported array data type")
    const tail = d.get(1)
    if (typeof tail !== "number" || !Number.isSafeInteger(tail) || tail < 0 || tail > 9999999) throw Error("invalid array type")
    if (!(d.get(5) instanceof Uint8Array)) throw Error("array data must be bytes")
    if (![0, 1].includes(d.get(7) as number)) throw Error("invalid fidelity")
    for (const key of [2]) {
      const raw = d.get(key)
      if (!Array.isArray(raw) || raw.length === 3 && raw[2] instanceof Map && !raw[2].size) throw Error("noncanonical operation descriptor")
      const op = descriptor(raw as any)
      const registry = encodings
      if (registry.has(operationKey(op))) {
        if (key === 2) {
          const [e] = operation(encodings, op)
          if (!e.types.includes(d.get(0) as number) || d.get(7) !== (e.lossless ? 0 : 1)) throw Error("encoding dtype or fidelity mismatch")
        }
      }
    }
    const name = d.get(4)
    if (d.has(4) && (typeof name !== "string" || !name.length)) throw Error("array name must be a non-empty string")
    if (tail === 1000786 && (typeof name !== "string" || !name.length || ["mz", "intensity", "charge"].includes(name))) throw Error("invalid array name")
    if (tail === 1000786 && /^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+(?![\s\S])/.test(name as string)) throw Error("non-standard array name must not be a CV accession")
    const identity = JSON.stringify([tail, tail === 1000786 ? name : ""])
    if (seen.has(identity)) throw Error("duplicate array descriptor")
    seen.add(identity)
    const parsed = parseHeaderMap(new Map<number, unknown>([[0, 0], [6, [d]]])).descriptors[0]!
    const representation = new Set([1000519, 1000521, 1000522, 1000523, 1000576, 1000574, 1002312, 1002313, 1002314, 1002746, 1002747, 1002748, 1003780, 1003781, 1003782, 1003783, 1003784, 1003785, tail])
    if (parsed.params?.some(p => /^MS:\d+$/.test(p.accession) && representation.has(Number(p.accession.slice(3))))) throw Error("array scientific parameters conflict with representation declarations")
    validateExtensions(parsed.extensions ?? {}, false)
  } catch (e) { asDecodeError(e, "invalid array descriptor") }
}
function validateHeaderShape(h: MsgMap) {
  try { shape(h, Array.from({ length: 13 }, (_, i) => i)) } catch (e) { asDecodeError(e, "unsupported spectrl header key") }
  for (const k of [2, 4, 5, 6, 7, 10]) if (h.has(k) && !Array.isArray(h.get(k))) throw new SpectrlDecodeError(`header key ${k} must be array`)
  if (!h.has(0)) throw new SpectrlDecodeError("missing defaultArrayLength")
  if (h.has(1) && typeof h.get(1) !== "string") throw new SpectrlDecodeError("id must be a string")
}
export function readTokenPayload(token: string, limits?: DecodeLimits): Uint8Array {
  const budget = resolveDecodeLimits(limits)
  if (typeof token !== "string" || token.length > Math.ceil(MAX_TOKEN_BYTES * 4 / 3) + MAGIC.length + 12) throw new SpectrlDecodeError("invalid token type or size")
  if (token.length > budget.maxTokenBytes) throw new SpectrlDecodeError("token exceeds maxTokenBytes")
  const prefix = `${MAGIC}.`
  if (!token.startsWith(prefix)) throw new SpectrlDecodeError(`Not a ${MAGIC} token`)
  const parts = token.slice(prefix.length).split(".")
  if (parts.length !== 3) throw new SpectrlDecodeError("a spectrl token has exactly five '.'-separated parts")
  const [mode, payload, stored] = parts as [string, string, string]
  if (!["r", "z", "b"].includes(mode)) throw new SpectrlDecodeError(`unsupported payload mode: ${mode}`)
  if (!/^[0-9a-f]{8}$/.test(stored)) throw new SpectrlDecodeError("spectrl token checksum must be eight lowercase hexadecimal characters")
  const expected = tokenChecksum(`${MAGIC}.${mode}.${payload}`)
  if (expected !== stored) throw new SpectrlDecodeError(`spectrl token checksum mismatch: stored=${stored}, computed=${expected}. Token may be corrupted.`)
  const packed = b64urlDecode(payload)
  if (packed.length > MAX_TOKEN_BYTES) throw new SpectrlDecodeError(`encoded payload exceeds ${MAX_TOKEN_BYTES} bytes`)
  try {
    return decompressPayload(packed, mode, MAX_TOKEN_BYTES)
  } catch (e) {
    asDecodeError(e, "invalid compressed CBOR payload")
  }
}

export function readTokenDocument(token: string, limits?: DecodeLimits): { doc: MsgMap, decoded: DecodedSpectrum } {
  const budget = resolveDecodeLimits(limits)
  const raw = readTokenPayload(token, limits)
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
  if (n > budget.maxPeaks) throw new SpectrlDecodeError("declared peak count exceeds maxPeaks")
  decoded.checksum = token.slice(token.lastIndexOf(".") + 1)
  decoded.formatVersion = 3

  const descriptors = h.get(6) ?? []
  if (!Array.isArray(descriptors)) throw new SpectrlDecodeError("binaryDataArrayList must be an array")
  if (descriptors.length > budget.maxArrays) throw new SpectrlDecodeError("array count exceeds maxArrays")
  const seen = new Set<string>()
  let decodedBytes = 0
  for (const descriptor of descriptors) {
    validateDescriptor(descriptor, seen)
    decodedBytes += n * (descriptor.get(DESC_TYPE) === TYPE_FLOAT64 ? 8 : 4)
    if (decodedBytes > budget.maxDecodedBytes) throw new SpectrlDecodeError("decoded array bytes exceed maxDecodedBytes")
  }
  return { doc: h, decoded }
}

export function decodeCbor(token: string, limits?: DecodeLimits): DecodedSpectrum {
  const { doc, decoded } = readTokenDocument(token, limits)
  try {
    validateExtensions(decoded.extensions ?? {})
    for (const d of parseHeaderMap(doc).descriptors) {
      validateExtensions(d.extensions ?? {})
      const arr = decodePipeline(d.data!, d.type, decoded.defaultArrayLength, d.encoding, d.fidelity)
      for (const v of arr) if (!Number.isFinite(v) || d.array === 1000514 && v < 0) throw Error("invalid array value")
      const key = d.array === 1000514 ? "mz" : d.array === 1000515 ? "intensity" : d.array === 1000516 ? "charge" : d.array === 1000786 ? d.name! : decodeTail(d.array)
      if (["mz", "intensity", "charge"].includes(key) && d.array !== 1000786) decoded[key as "mz" | "intensity" | "charge"] = arr
      else Object.defineProperty(decoded.extraArrays, key, { value: arr, enumerable: true, configurable: true, writable: true })
      const put = (target: object, value: unknown) => Object.defineProperty(target, key, { value, enumerable: true, configurable: true, writable: true })
      if (d.unit) put(decoded.arrayUnits, d.unit)
      if (d.name !== undefined) put(decoded.arrayNames!, d.name)
      if (d.params?.length) put(decoded.arrayParams!, d.params)
      if (d.userParams?.length) put(decoded.arrayUserParams!, d.userParams)
      const processing = [...d.processing ?? []]
      if (d.fidelity === 1) processing.push({ operation: "spectrl:lossy-encoding", revision: 1, parameters: { encoding: d.encoding } })
      if (processing.length) put(decoded.arrayProcessing!, processing)
      if (Object.keys(d.extensions ?? {}).length) put(decoded.arrayExtensions!, d.extensions)
    }
  } catch (e) { asDecodeError(e, "malformed array blob or required extension") }
  return decoded
}
