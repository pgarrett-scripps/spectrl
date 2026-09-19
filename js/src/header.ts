/** Compact v3 header and array metadata. */
import { decodeParamKey, decodeTail, decodeUnitTail, encodeParamKey, encodeUnit } from "./cv.js"
import type { ContextFields, CvParam, DecodedSpectrum, InlineSpectrum, Precursor, Scan, UserParam, ContextRecord, Extensions } from "./model.js"
import { decodeRecord, encodeRecord, fromWire, toWire, validateExtensions } from "./context.js"
import { descriptor, type Operation } from "./pipeline.js"
export type MsgMap = Map<number | string, unknown>
export const DESC_TYPE = 0
export const DESC_ARRAY = 1
export const DESC_ENCODING = 2
export const DESC_NAME = 4
export const DESC_DATA = 5
export const DESC_UNIT = 6
export const DESC_FIDELITY = 7
export interface Descriptor {
  type: number
  array: number
  encoding: Operation
  fidelity: number
  name?: string
  unit?: string
  data?: Uint8Array
  params?: CvParam[]
  userParams?: UserParam[]
  processing?: ContextRecord[]
  extensions?: Extensions
}
const accession = /^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$/
function validateAccession(value: unknown): asserts value is string {
  if (typeof value !== "string" || !accession.test(value)) throw Error("invalid CV accession")
}
function scalar(value: unknown) {
  if (value == null || typeof value === "string") return
  if (typeof value === "number" && Number.isFinite(value) && (!Number.isInteger(value) || Number.isSafeInteger(value))) return
  throw Error("invalid parameter scalar")
}
export function encodeParamMap(params: CvParam[]): unknown[][] {
  if (!Array.isArray(params)) throw Error("CV parameters must be a list")
  return params.map(p => {
    validateAccession(p.accession)
    scalar(p.value)
    if (p.unitAccession != null) validateAccession(p.unitAccession)
    return [encodeParamKey(p.accession), p.unitAccession == null ? p.value ?? null : [p.value ?? null, encodeUnit(p.unitAccession)]]
  })
}
export function decodeParamMap(raw: unknown = []): CvParam[] {
  if (!Array.isArray(raw)) throw Error("CV parameters must be a list")
  return raw.map(pair => {
    if (!Array.isArray(pair) || pair.length !== 2) throw Error("CV parameter must have two items")
    const [key, val] = pair
    if (typeof key !== "string" && !(typeof key === "number" && Number.isSafeInteger(key) && key >= 0)) throw Error("invalid CV parameter key")
    const acc = decodeParamKey(key)
    validateAccession(acc)
    let value = val
    let unitAccession: string | undefined
    if (Array.isArray(val)) {
      if (val.length !== 2) throw Error("invalid value/unit pair")
      value = val[0]
      unitAccession = decodeUnitTail(val[1])
      validateAccession(unitAccession)
    }
    scalar(value)
    return { accession: acc, ...(value == null ? {} : { value }), ...(unitAccession ? { unitAccession } : {}) }
  })
}
export function encodeUserParams(params: UserParam[]): MsgMap[] {
  if (!Array.isArray(params)) throw Error("user parameters must be a list")
  return params.map(p => {
    if (typeof p.name !== "string" || !p.name.length) throw Error("user parameter name must be non-empty")
    scalar(p.value)
    const out: MsgMap = new Map([["n", p.name]])
    if (p.value != null) out.set("v", p.value)
    if (p.type != null) {
      if (typeof p.type !== "string") throw Error("user parameter type must be a string")
      out.set("t", p.type)
    }
    if (p.unitAccession != null) { validateAccession(p.unitAccession)
      out.set("u", encodeUnit(p.unitAccession))
    }
    return out
  })
}
export function decodeUserParams(raw: unknown = []): UserParam[] {
  if (!Array.isArray(raw)) throw Error("user parameters must be a list")
  return raw.map(m => {
    shape(m, ["n", "v", "t", "u"])
    const out = { name: m.get("n"), value: m.get("v") ?? null, type: m.get("t") ?? null, unitAccession: m.has("u") ? decodeUnitTail(m.get("u") as any) : null } as UserParam
    encodeUserParams([out])
    return out
  })
}
export function shape(m: unknown, keys: (string | number)[]): asserts m is MsgMap {
  if (!(m instanceof Map) || [...m.keys()].some(k => !keys.includes(k))) throw Error("invalid metadata map fields")
}
function groupEncode(value: { params: CvParam[], userParams?: UserParam[] }): MsgMap {
  const out: MsgMap = new Map([[0, encodeParamMap(value.params)]])
  if (value.userParams?.length) out.set(1, encodeUserParams(value.userParams))
  return out
}
function groupDecode(raw: unknown) {
  shape(raw, [0, 1])
  return { params: decodeParamMap(raw.get(0)), userParams: decodeUserParams(raw.get(1)) }
}
function putContext(out: MsgMap, value: ContextFields, start: number) {
  if (value.source != null) out.set(start, encodeRecord(value.source, "source"))
  if (value.acquisition != null) out.set(start + 1, encodeRecord(value.acquisition, "acquisition"))
  if (value.processing?.length) out.set(start + 2, value.processing.map(x => encodeRecord(x, "processing")))
}
function getContext(raw: MsgMap, start: number): ContextFields {
  const processing = raw.get(start + 2) ?? []
  if (!Array.isArray(processing)) throw Error("processing must be an array")
  return { source: raw.has(start) ? decodeRecord(raw.get(start), "source") : null,
    acquisition: raw.has(start + 1) ? decodeRecord(raw.get(start + 1), "acquisition") : null,
    processing: processing.map(x => decodeRecord(x, "processing")) }
}
function scanEncode(scan: Scan): MsgMap {
  const out: MsgMap = new Map([[0, encodeParamMap(scan.params)]])
  if (scan.windows?.length) out.set(1, scan.windows.map(groupEncode))
  if (scan.userParams?.length) out.set(2, encodeUserParams(scan.userParams))
  putContext(out, scan, 3)
  return out
}
function list(raw: unknown, fn: (x: any) => any): any[] {
  if (raw === undefined) return []
  if (!Array.isArray(raw)) throw Error("expected metadata array")
  return raw.map(fn)
}
function scanDecode(raw: unknown): Scan {
  shape(raw, [0, 1, 2, 3, 4, 5])
  return { params: decodeParamMap(raw.get(0)), windows: list(raw.get(1), groupDecode), userParams: decodeUserParams(raw.get(2)), ...getContext(raw, 3) }
}
function precursorEncode(value: Precursor): MsgMap {
  const out: MsgMap = new Map()
  if (value.isolationWindow) out.set(0, groupEncode(value.isolationWindow))
  if (value.selectedIons?.length) out.set(1, value.selectedIons.map(groupEncode))
  if (value.activation) out.set(2, groupEncode(value.activation))
  putContext(out, value, 3)
  return out
}
function precursorDecode(raw: unknown): Precursor {
  shape(raw, [0, 1, 2, 3, 4, 5])
  return { isolationWindow: raw.has(0) ? groupDecode(raw.get(0)) : null, selectedIons: list(raw.get(1), groupDecode), activation: raw.has(2) ? groupDecode(raw.get(2)) : null, ...getContext(raw, 3) }
}
export function buildHeaderMap(spec: InlineSpectrum, descriptors: Descriptor[]): MsgMap {
  const h: MsgMap = new Map([[0, spec.defaultArrayLength]])
  if (spec.id != null) h.set(1, spec.id)
  if (spec.params?.length) h.set(2, encodeParamMap(spec.params))
  if (spec.scans?.length || spec.scanCombination) {
    const scans: MsgMap = new Map([["s", (spec.scans ?? []).map(scanEncode)]])
    if (spec.scanCombination) scans.set("c", Number(spec.scanCombination.accession.split(":")[1]))
    h.set(3, scans)
  }
  if (spec.precursors?.length) h.set(4, spec.precursors.map(precursorEncode))
  if (spec.products?.length) h.set(5, spec.products.map(p => p.isolationWindow ? new Map([[0, groupEncode(p.isolationWindow)]]) : new Map()))
  h.set(6, descriptors.map(d => {
    const out: MsgMap = new Map([[0, d.type], [1, d.array], [2, toWire(d.encoding)], [5, d.data], [7, d.fidelity]])
    if (d.name !== undefined) out.set(4, d.name)
    if (d.unit !== undefined) out.set(6, encodeUnit(d.unit))
    if (d.params?.length) out.set(8, encodeParamMap(d.params))
    if (d.userParams?.length) out.set(9, encodeUserParams(d.userParams))
    if (d.processing?.length) out.set(10, d.processing.map(x => encodeRecord(x, "processing")))
    if (d.extensions && Object.keys(d.extensions).length) {
      validateExtensions(d.extensions, false)
      out.set(11, toWire(d.extensions))
    }
    return out
  }))
  if (spec.userParams?.length) h.set(7, encodeUserParams(spec.userParams))
  putContext(h, spec, 8)
  if (spec.extensions && Object.keys(spec.extensions).length) { validateExtensions(spec.extensions, false)
    h.set(11, toWire(spec.extensions))
  }
  return h
}
export function parseHeaderMap(h: MsgMap): { decoded: DecodedSpectrum, descriptors: Descriptor[] } {
  let scans: Scan[] = []
  let scanCombination: CvParam | null = null
  if (h.has(3)) {
    const raw = h.get(3)
    shape(raw, ["s", "c"])
    scans = list(raw.get("s"), scanDecode)
    if (raw.has("c")) {
      const c = raw.get("c")
      if (typeof c !== "number" || !Number.isSafeInteger(c) || c < 0 || c > 9999999) throw Error("invalid scan combination")
      scanCombination = { accession: decodeTail(c) }
    }
  }
  const extensions = fromWire(h.get(11) ?? new Map()) as Extensions
  validateExtensions(extensions, false)
  const decoded: DecodedSpectrum = {
    defaultArrayLength: h.get(0) as number, id: h.get(1) as string ?? null,
    mz: null, intensity: null, charge: null, params: decodeParamMap(h.get(2)), scans, scanCombination,
    precursors: list(h.get(4), precursorDecode), products: list(h.get(5), raw => { shape(raw, [0])
      return { isolationWindow: raw.has(0) ? groupDecode(raw.get(0)) : null }
    }), userParams: decodeUserParams(h.get(7)), ...getContext(h, 8), extensions,
    extraArrays: {}, arrayUnits: {}, arrayNames: {}, arrayParams: {}, arrayUserParams: {}, arrayProcessing: {}, arrayExtensions: {}, checksum: "", formatVersion: 3,
  }
  const descriptors: Descriptor[] = list(h.get(6), d => {
    shape(d, Array.from({ length: 12 }, (_, i) => i))
    return { type: d.get(0) as number, array: d.get(1) as number, encoding: descriptor(d.get(2) as any), fidelity: d.get(7) as number,
      data: d.get(5) as Uint8Array, name: d.get(4) as string | undefined, unit: d.has(6) ? decodeUnitTail(d.get(6) as any) : undefined,
      params: decodeParamMap(d.get(8)), userParams: decodeUserParams(d.get(9)), processing: list(d.get(10), x => decodeRecord(x, "processing")), extensions: fromWire(d.get(11) ?? new Map()),
    }
  })
  return { decoded, descriptors }
}
