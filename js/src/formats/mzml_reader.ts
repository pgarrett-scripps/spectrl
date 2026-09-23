/** Read spectra from an mzML document.
 *
 * Parsing uses DOMParser, which browsers provide and Node does not, because
 * the converter that needs this runs in a browser and the package carries no
 * XML dependency. Node callers have the Python CLI, which also handles the
 * multi-gigabyte files a tab should not be asked to hold.
 *
 * This reads what a spectrl token models: the spectrum's parameters, scans,
 * precursors, products and binary arrays, plus the run-level context that
 * references reach into. It is not a general mzML reader. */

import pako from "pako"

import type { CvParam, InlineSpectrum, UserParam } from "../model.js"
import { base64ToBytes } from "./base64_bytes.js"

const MZML_NS = "http://psi.hupo.org/ms/mzml"

const MZ_ARRAY = "MS:1000514"
const INTENSITY_ARRAY = "MS:1000515"
const CHARGE_ARRAY = "MS:1000516"
const FLOAT64 = "MS:1000523"
const FLOAT32 = "MS:1000521"
const INT32 = "MS:1000519"
const INT64 = "MS:1000522"
const ZLIB = "MS:1000574"
const NO_COMPRESSION = "MS:1000576"
// MS-Numpress linear, pic and slof, alone or followed by zlib.
const NUMPRESS = new Set(["MS:1002312", "MS:1002313", "MS:1002314", "MS:1002746", "MS:1002747", "MS:1002748"])
const NON_STANDARD = "MS:1000786"

function parseDocument(text: string): Document {
  const Parser = (globalThis as { DOMParser?: new () => DOMParser }).DOMParser
  if (!Parser) {
    throw Error(
      "reading mzML needs DOMParser, which this runtime does not provide. " +
      "Use the Python package or the spectrl CLI outside a browser.",
    )
  }
  const doc = new Parser().parseFromString(text, "application/xml")
  const failure = doc.getElementsByTagName("parsererror")[0]
  if (failure) throw Error(`mzML is not well-formed XML: ${failure.textContent?.slice(0, 200) ?? ""}`)
  return doc
}

function children(node: Element, name: string): Element[] {
  const out: Element[] = []
  for (const child of Array.from(node.children)) {
    if (child.localName === name) out.push(child)
  }
  return out
}

function allNamed(root: Document, name: string): Element[] {
  const namespaced = Array.from(root.getElementsByTagNameNS(MZML_NS, name))
  return namespaced.length ? namespaced : Array.from(root.getElementsByTagName(name))
}

/** A cvParam value carries no type in XML, so a numeric string becomes a
 * number and anything else stays text, matching the Python importer. */
function paramValue(raw: string | null): string | number | null {
  if (raw === null || raw === "") return null
  const value = Number(raw)
  if (!Number.isFinite(value) || raw.trim() === "") return raw
  return Number.isInteger(value) ? value : value
}

function readParams(node: Element, groups: Map<string, Element>): [CvParam[], UserParam[]] {
  const params: CvParam[] = []
  const userParams: UserParam[] = []
  for (const child of Array.from(node.children)) {
    if (child.localName === "referenceableParamGroupRef") {
      const group = groups.get(child.getAttribute("ref") ?? "")
      if (group) {
        const [p, u] = readParams(group, groups)
        params.push(...p)
        userParams.push(...u)
      }
      continue
    }
    if (child.localName === "cvParam") {
      const param: CvParam = { accession: child.getAttribute("accession") ?? "" }
      const value = paramValue(child.getAttribute("value"))
      if (value !== null) param.value = value
      const unit = child.getAttribute("unitAccession")
      if (unit) param.unitAccession = unit
      params.push(param)
      continue
    }
    if (child.localName === "userParam") {
      const param: UserParam = { name: child.getAttribute("name") ?? "" }
      const declared = child.getAttribute("type")
      const raw = child.getAttribute("value")
      if (raw !== null) {
        param.value = declared?.includes("int") || declared?.includes("double") || declared?.includes("float")
          ? Number(raw)
          : raw
      }
      const unit = child.getAttribute("unitAccession")
      if (unit) param.unitAccession = unit
      userParams.push(param)
    }
  }
  return [params, userParams]
}

function group(node: Element | undefined, groups: Map<string, Element>) {
  if (!node) return null
  const [params, userParams] = readParams(node, groups)
  return { params, userParams }
}

function decodeBinary(node: Element, groups: Map<string, Element>): { accession: string, name: string | null, values: Float64Array } {
  const [params] = readParams(node, groups)
  const has = (accession: string) => params.some(p => p.accession === accession)
  const text = children(node, "binary")[0]?.textContent?.replace(/\s+/g, "") ?? ""
  let bytes = base64ToBytes(text)
  if (has(ZLIB)) bytes = inflate(bytes)
  else if (!has(NO_COMPRESSION) && bytes.length && !divides(bytes.length, params)) bytes = inflate(bytes)

  let values: Float64Array
  if (has(FLOAT32)) {
    const view = new Float32Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 4))
    values = Float64Array.from(view)
  } else if (has(INT32)) {
    const view = new Int32Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 4))
    values = Float64Array.from(view)
  } else if (has(INT64)) {
    const view = new BigInt64Array(bytes.buffer, bytes.byteOffset, Math.floor(bytes.byteLength / 8))
    values = Float64Array.from(Array.from(view, Number))
  } else {
    // float64 is the default and the only remaining declared width.
    const aligned = bytes.byteOffset % 8 === 0 ? bytes : Uint8Array.from(bytes)
    values = new Float64Array(aligned.buffer, aligned.byteOffset, Math.floor(aligned.byteLength / 8)).slice()
  }

  const other = params.find(p => NUMPRESS.has(p.accession))
  if (other) throw new Error(`numpress-compressed arrays (${other.accession}) are not supported; convert the file without numpress first`)
  const identity = params.find(p =>
    p.accession !== FLOAT32 && p.accession !== FLOAT64 && p.accession !== INT32 && p.accession !== INT64 &&
    p.accession !== ZLIB && p.accession !== NO_COMPRESSION)
  return {
    accession: identity?.accession ?? NON_STANDARD,
    name: identity?.accession === NON_STANDARD ? String(identity.value ?? "") : null,
    values,
  }
}

function divides(length: number, params: CvParam[]): boolean {
  const width = params.some(p => p.accession === FLOAT32 || p.accession === INT32) ? 4 : 8
  return length % width === 0
}

function inflate(bytes: Uint8Array): Uint8Array {
  // pako already ships for the token payload codec, so zlib-compressed mzML
  // arrays, which most real files use, cost no new dependency.
  return pako.inflate(bytes)
}

export interface ReadMzmlOptions {
  /** Zero-based index of the one spectrum to return. */
  index?: number
  /** Native id of the one spectrum to return. */
  id?: string
}

/** A spectrum's identity and headline numbers, without its arrays.
 *
 * The converter lists these so a person can choose one spectrum out of a run
 * without every peak array being built first. */
export interface SpectrumSummary {
  index: number
  id: string
  msLevel: number | null
  precursorMz: number | null
  retentionSeconds: number | null
  peaks: number
}

function scanTime(scans: Element[], groups: Map<string, Element>): number | null {
  for (const scan of scans) {
    const [params] = readParams(scan, groups)
    for (const p of params) {
      if (p.accession === "MS:1000016" && p.value != null) {
        const value = Number(p.value)
        return p.unitAccession === "UO:0000031" ? value * 60 : value
      }
    }
  }
  return null
}

/** List every spectrum in the document, without decoding any arrays. */
export function listMzmlSpectra(text: string): SpectrumSummary[] {
  const doc = parseDocument(text)
  const groups = referenceGroups(doc)
  return allNamed(doc, "spectrum").map((node, index) => {
    const [params] = readParams(node, groups)
    const level = params.find(p => p.accession === "MS:1000511")?.value
    const scanList = children(node, "scanList")[0]
    let precursorMz: number | null = null
    for (const list of children(node, "precursorList")) {
      for (const entry of children(list, "precursor")) {
        for (const ions of children(entry, "selectedIonList")) {
          for (const ion of children(ions, "selectedIon")) {
            const [ionParams] = readParams(ion, groups)
            const mz = ionParams.find(p => p.accession === "MS:1000744")?.value
            if (mz != null && precursorMz === null) precursorMz = Number(mz)
          }
        }
      }
    }
    return {
      index,
      id: node.getAttribute("id") ?? `index=${index}`,
      msLevel: level == null ? null : Number(level),
      precursorMz,
      retentionSeconds: scanList ? scanTime(children(scanList, "scan"), groups) : null,
      peaks: Number(node.getAttribute("defaultArrayLength") ?? 0),
    }
  })
}

function referenceGroups(doc: Document): Map<string, Element> {
  const groups = new Map<string, Element>()
  for (const node of allNamed(doc, "referenceableParamGroup")) {
    groups.set(node.getAttribute("id") ?? "", node)
  }
  return groups
}

/** Read spectra from an mzML document, optionally selecting just one. */
export function readMzml(text: string, opts: ReadMzmlOptions = {}): InlineSpectrum[] {
  const doc = parseDocument(text)
  const groups = referenceGroups(doc)
  let nodes = allNamed(doc, "spectrum")
  if (opts.id !== undefined) {
    nodes = nodes.filter(n => n.getAttribute("id") === opts.id)
    if (!nodes.length) throw Error(`no spectrum with id ${JSON.stringify(opts.id)}`)
  } else if (opts.index !== undefined) {
    const picked = nodes[opts.index]
    if (!picked) throw Error(`spectrum index ${opts.index} is out of range (${nodes.length} spectra)`)
    nodes = [picked]
  }
  return nodes.map(node => readSpectrum(node, groups))
}

function readSpectrum(node: Element, groups: Map<string, Element>): InlineSpectrum {
  const [params, userParams] = readParams(node, groups)

  const scans = []
  for (const list of children(node, "scanList")) {
    for (const scan of children(list, "scan")) {
      const [scanParams, scanUser] = readParams(scan, groups)
      const windows = []
      for (const wl of children(scan, "scanWindowList")) {
        for (const window of children(wl, "scanWindow")) windows.push(group(window, groups)!)
      }
      scans.push({ params: scanParams, userParams: scanUser, windows })
    }
  }

  const precursors = []
  for (const list of children(node, "precursorList")) {
    for (const entry of children(list, "precursor")) {
      const ions = []
      for (const il of children(entry, "selectedIonList")) {
        for (const ion of children(il, "selectedIon")) ions.push(group(ion, groups)!)
      }
      const reference = entry.getAttribute("spectrumRef") ?? entry.getAttribute("externalSpectrumID")
      precursors.push({
        isolationWindow: group(children(entry, "isolationWindow")[0], groups),
        selectedIons: ions,
        activation: group(children(entry, "activation")[0], groups),
        ...(reference ? { source: { spectrumRef: reference } } : {}),
      })
    }
  }

  const products = []
  for (const list of children(node, "productList")) {
    for (const entry of children(list, "product")) {
      products.push({ isolationWindow: group(children(entry, "isolationWindow")[0], groups) })
    }
  }

  const spectrum: Record<string, unknown> = {
    defaultArrayLength: Number(node.getAttribute("defaultArrayLength") ?? 0),
    id: node.getAttribute("id"),
    params, userParams, scans, precursors, products,
    extraArrays: {} as Record<string, Float64Array>,
  }
  for (const list of children(node, "binaryDataArrayList")) {
    for (const array of children(list, "binaryDataArray")) {
      const { accession, name, values } = decodeBinary(array, groups)
      if (accession === MZ_ARRAY) spectrum.mz = values
      else if (accession === INTENSITY_ARRAY) spectrum.intensity = values
      else if (accession === CHARGE_ARRAY) spectrum.charge = values
      else (spectrum.extraArrays as Record<string, Float64Array>)[name || accession] = values
    }
  }
  return spectrum as unknown as InlineSpectrum
}
