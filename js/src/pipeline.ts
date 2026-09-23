/** Versioned numeric array encodings for v3. */
import { byteShuffle, byteUnshuffle, decodeRaw, encodeRaw, type NumArray } from "./codecs.js"
import { deltaShuffle, deltaUnshuffle } from "./delta.js"
import { MAX_BLOB_BYTES } from "./format.js"
import { encodeQuantized, decodeQuantized, validateQuantized } from "./quantized.js"
import { encodeRounded, decodeRounded, validateRounded } from "./rounded.js"

export type Parameters = Record<string, unknown>
export type Operation = [number | string, number, Parameters?]
export type OperationOption = number | string | Operation | { id: number | string, revision?: number, parameters?: Parameters }
export interface Encoding {
  encode: (data: NumArray, type: number, params: Parameters) => Uint8Array
  decode: (bytes: Uint8Array, type: number, count: number, params: Parameters) => NumArray
  validate: (params: Parameters) => void
  lossless: boolean
  types: readonly number[]
}
export const encodingNames: Record<string, number> = { raw: 0, "byte-shuffle": 1, "modular-delta-shuffle": 2, quantized: 3, "rounded-float": 4 }
const namespace = /^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+$/
export function descriptor(value: OperationOption, names?: Record<string, number>): Operation {
  let tuple: unknown[]
  if (typeof value === "number" || typeof value === "string") tuple = [value, 1]
  else if (Array.isArray(value)) tuple = value
  else {
    if (!value || typeof value !== "object" || Object.keys(value).some(k => !["id", "revision", "parameters"].includes(k))) throw Error("invalid operation descriptor")
    tuple = [value.id, value.revision ?? 1, value.parameters ?? {}]
  }
  if (![2, 3].includes(tuple.length)) throw Error("operation requires identifier, revision, and optional parameters")
  let [id, revision, params = {}] = tuple
  if (names && typeof id === "string") id = names[id.replace(/^spectrl:/, "")] ?? id
  if (!(typeof id === "number" && Number.isSafeInteger(id) && id >= 0) && !(typeof id === "string" && namespace.test(id))) throw Error("invalid operation identifier")
  if (typeof revision !== "number" || !Number.isSafeInteger(revision) || revision < 1) throw Error("invalid operation revision")
  if (params instanceof Map) {
    if ([...params.keys()].some(k => typeof k !== "string")) throw Error("operation parameters require string keys")
    params = Object.fromEntries(params)
  }
  if (!params || typeof params !== "object" || Array.isArray(params) || params instanceof Uint8Array) throw Error("operation parameters must be a map")
  return Object.keys(params).length ? [id as number | string, revision, params as Parameters] : [id as number | string, revision]
}
export const encodings = new Map<string, Encoding>()
export const operationKey = (op: Operation) => JSON.stringify(op.slice(0, 2))
function register<T>(registry: Map<string, T>, id: string, impl: T, revision: number) {
  const desc = descriptor([id, revision])
  if (!namespace.test(id) || id.startsWith("spectrl:")) throw Error("custom registration requires a non-spectrl namespace")
  const key = operationKey(desc)
  if (registry.has(key)) throw Error("operation already registered")
  registry.set(key, impl)
}
export const registerEncoding = (id: string, impl: Encoding, revision = 1) => register(encodings, id, impl, revision)
export function operation<T extends { validate: (p: Parameters) => void }>(registry: Map<string, T>, desc: Operation): [T, Parameters] {
  const impl = registry.get(operationKey(desc))
  if (!impl) throw Error(`unsupported operation ${desc[0]} revision ${desc[1]}`)
  const params = desc[2] ?? {}
  impl.validate(params)
  return [impl, params]
}
const empty = (p: Parameters) => { if (Object.keys(p).length) throw Error("operation accepts no parameters") }
const width = (type: number) => type === 1000523 ? 8 : 4
for (const id of [0, 1, 2]) encodings.set(operationKey([id, 1]), {
  lossless: true, types: [1000521, 1000523, 1000519], validate: empty,
  encode: (a, t) => { const raw = encodeRaw(a, t)
    return id === 0 ? raw : id === 1 ? byteShuffle(raw, width(t)) : deltaShuffle(raw, width(t))
  },
  decode: (b, t, n) => decodeRaw(id === 0 ? b : id === 1 ? byteUnshuffle(b, width(t)) : deltaUnshuffle(b, width(t)), t),
})
encodings.set(operationKey([3, 1]), { encode: encodeQuantized, decode: decodeQuantized, validate: validateQuantized, lossless: false, types: [1000523] })
encodings.set(operationKey([4, 1]), { encode: encodeRounded, decode: decodeRounded, validate: validateRounded, lossless: false, types: [1000521, 1000523] })
export function encodePipeline(data: NumArray, type: number, enc: Operation) {
  const [e, params] = operation(encodings, enc)
  if (!e.types.includes(type)) throw Error("encoding does not support dtype")
  const blob = e.encode(data, type, params)
  if (!(blob instanceof Uint8Array) || blob.length > Math.min(MAX_BLOB_BYTES, 64 + 16 * data.length)) throw Error("encoding exceeds intermediate limit")
  return { blob, fidelity: e.lossless ? 0 : 1 }
}
export function decodePipeline(blob: Uint8Array, type: number, count: number, enc: Operation, fidelity: number): NumArray {
  const [e, params] = operation(encodings, enc)
  if (!e.types.includes(type) || fidelity !== (e.lossless ? 0 : 1)) throw Error("encoding dtype or fidelity mismatch")
  if (blob.length > Math.min(MAX_BLOB_BYTES, 64 + 16 * count)) throw Error("encoded byte limit exceeded")
  const out = e.decode(blob, type, count, params)
  if (out.length !== count || !(type === 1000523 ? out instanceof Float64Array : type === 1000521 ? out instanceof Float32Array : out instanceof Int32Array)) throw Error("decoded shape or dtype mismatch")
  return out
}
