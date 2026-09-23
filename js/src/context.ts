/** Selected-spectrum context and namespaced extension contracts. */
import type { ContextRecord, Extensions, InlineSpectrum } from "./model.js"
import { encodeParamMap, decodeParamMap, encodeUserParams, decodeUserParams, type MsgMap } from "./header.js"
export const fields = ["params", "userParams", "id", "name", "version", "location", "externalIds", "spectrumRef", "instrument", "components", "kind", "order", "software", "operation", "revision", "parameters", "sourceParams"] as const
const allowed: Record<string, string[]> = {
  source: ["params", "userParams", "id", "name", "location", "externalIds", "spectrumRef"], acquisition: ["instrument"],
  instrument: ["params", "userParams", "id", "name", "components", "software"], component: ["params", "userParams", "kind", "order"],
  software: ["params", "userParams", "id", "name", "version"], processing: ["params", "userParams", "software", "operation", "revision", "parameters", "sourceParams"],
}
export function toWire(value: unknown): unknown {
  if (value instanceof Map) return new Map([...value].map(([k, v]) => [k, toWire(v)]))
  if (Array.isArray(value)) return value.map(toWire)
  if (value && typeof value === "object" && !(value instanceof Uint8Array)) return new Map(Object.entries(value).map(([k, v]) => [k, toWire(v)]))
  return value
}
export function fromWire(value: unknown): any {
  if (value instanceof Map) {
    if ([...value.keys()].some(k => typeof k !== "string")) return new Map([...value].map(([k, v]) => [k, fromWire(v)]))
    return Object.fromEntries([...value].map(([k, v]) => [k, fromWire(v)]))
  }
  if (Array.isArray(value)) return value.map(fromWire)
  return value
}
/** A plain object with string keys: not null, an array, a Map, a typed array,
 * or any other exotic object that merely reports `typeof "object"`. */
function isStringKeyedObject(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value) || value instanceof Map || ArrayBuffer.isView(value)) return false
  const proto = Object.getPrototypeOf(value)
  if (proto !== Object.prototype && proto !== null) return false
  return Reflect.ownKeys(value).every(k => typeof k === "string")
}

export function encodeRecord(value: ContextRecord, kind: string): MsgMap {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some(k => !allowed[kind]!.includes(k))) throw Error(`invalid ${kind} record`)
  const out: MsgMap = new Map()
  for (const [key, val] of Object.entries(value)) {
    if (val == null) continue
    let encoded: unknown = val
    if (key === "params" || key === "sourceParams") encoded = encodeParamMap(val)
    else if (key === "userParams") encoded = encodeUserParams(val)
    else if (key === "instrument" || key === "software") encoded = encodeRecord(val, key)
    else if (key === "components") {
      if (!Array.isArray(val)) throw Error("components must be an array")
      encoded = val.map(x => encodeRecord(x, "component"))
    } else if (key === "externalIds") {
      if (!Array.isArray(val) || val.some(x => typeof x !== "string" || !x.length)) throw Error("externalIds require nonempty strings")
    } else if (key === "order" || key === "revision") {
      if (!Number.isSafeInteger(val) || val < (key === "order" ? 0 : 1)) throw Error("order must be nonnegative and revision positive")
    } else if (key === "parameters") {
      // A byte string is `typeof "object"` and is neither an Array nor a Map,
      // so it slipped through an earlier shape check and was accepted as a
      // parameter map. Require a plain object with string keys, as section 7 does.
      if (!isStringKeyedObject(val)) throw Error("parameters require a string-keyed object")
      encoded = toWire(val)
    } else if (typeof val !== "string") throw Error(`${key} must be a string`)
    if (key === "kind" && !["source", "analyzer", "detector"].includes(val)) throw Error("invalid component kind")
    out.set(fields.indexOf(key as typeof fields[number]), encoded)
  }
  return out
}
export function decodeRecord(value: unknown, kind: string): ContextRecord {
  if (!(value instanceof Map)) throw Error(`invalid ${kind} record`)
  const out: Record<string, unknown> = {}
  for (const [k, v] of value) {
    if (!Number.isInteger(k) || k < 0 || k >= fields.length) throw Error(`invalid ${kind} field`)
    const key = fields[k]!
    let decoded = v
    if (key === "params" || key === "sourceParams") decoded = decodeParamMap(v)
    else if (key === "userParams") decoded = decodeUserParams(v)
    else if (key === "instrument" || key === "software") decoded = decodeRecord(v, key)
    else if (key === "components") {
      if (!Array.isArray(v)) throw Error("components must be an array")
      decoded = v.map(x => decodeRecord(x, "component"))
    } else if (key === "parameters") decoded = fromWire(v)
    out[key] = decoded
  }
  encodeRecord(out, kind)
  return out
}
const namespace = /^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+$/
const extensions = new Map<string, (data: unknown) => void>()
export function registerExtension(id: string, validate: (data: unknown) => void, revision = 1) {
  if (!namespace.test(id) || !Number.isSafeInteger(revision) || revision < 1 || typeof validate !== "function") throw Error("invalid extension registration")
  const key = JSON.stringify([id, revision])
  if (extensions.has(key)) throw Error("extension already registered")
  extensions.set(key, validate)
}
export function validateExtensions(value: Extensions, requireSupported = true) {
  if (!value || typeof value !== "object" || Array.isArray(value) || value instanceof Map) throw Error("extensions must be a map")
  for (const [id, r] of Object.entries(value)) {
    if (!namespace.test(id) || !r || typeof r !== "object" || Object.keys(r).sort().join() !== "data,required,revision" || !Number.isSafeInteger(r.revision) || r.revision < 1 || typeof r.required !== "boolean") throw Error("invalid extension record")
    const validate = extensions.get(JSON.stringify([id, r.revision]))
    if (validate) validate(r.data)
    else if (r.required && requireSupported) throw Error(`unsupported required extension ${id}@${r.revision}`)
  }
}
export function checkArrayMutation(spec: InlineSpectrum) {
  if (Object.keys(spec.extensions ?? {}).length || Object.values(spec.arrayExtensions ?? {}).some(x => Object.keys(x).length)) throw Error("array mutation requires explicitly removing or updating extensions first")
}
export function recordChange(spec: InlineSpectrum, operation: string, parameters: Record<string, unknown>) {
  const summaries = new Set(["MS:1000285", "MS:1000504", "MS:1000505", "MS:1000527", "MS:1000528"])
  const sourceParams = (spec.params ?? []).filter(p => summaries.has(p.accession))
  return { params: (spec.params ?? []).filter(p => !summaries.has(p.accession)), processing: [...spec.processing ?? [], { operation, revision: 1, parameters, ...(sourceParams.length ? { sourceParams } : {}) }] }
}
export function withoutUserParams(spec: InlineSpectrum): InlineSpectrum {
  let count = 0
  const strip = (value: any, opaque = false): any => {
    if (opaque || value == null || typeof value !== "object" || ArrayBuffer.isView(value)) return value
    if (Array.isArray(value)) return value.map(v => strip(v))
    return Object.fromEntries(Object.entries(value).map(([k, v]) => {
      if (k === "userParams") { count += (v as unknown[]).length
        return [k, []]
      }
      if (k === "arrayUserParams") { count += Object.values(v as Record<string, unknown[]>).reduce((n, xs) => n + xs.length, 0)
        return [k, {}]
      }
      return [k, strip(v, ["extensions", "arrayExtensions", "parameters"].includes(k))]
    }))
  }
  const out = strip(spec) as InlineSpectrum
  if (count) out.processing = [...out.processing ?? [], { operation: "spectrl:metadata-omission", revision: 1, parameters: { userParamsRemoved: count } }]
  return out
}
