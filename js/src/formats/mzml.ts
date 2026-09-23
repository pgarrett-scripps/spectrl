/** Write one decoded spectrum as a complete, valid mzML 1.1.0 document.
 *
 * Built as strings rather than through a DOM, so it runs unchanged in Node and
 * in a browser with no XML dependency. Mirrors src/spectrl/formats/_mzml.py;
 * the two are compared byte for byte by the format parity check.
 *
 * Three constraints the schema imposes that a token does not. mzML ids are
 * xs:ID and must be unique document-wide, while a token's identifiers are
 * unique only within their record kind. A single-spectrum document never
 * contains the precursor, so the reference is always external and needs a
 * source file to anchor it. And file://C:/path, which real files carry, is not
 * a valid URI. */

import type { ContextRecord, CvParam, DecodedSpectrum, UserParam } from "../model.js"
import { bytesToBase64 as base64 } from "./base64_bytes.js"
import { termName } from "./names.js"
import { num } from "./peaklist_formats.js"
import { ConversionResult } from "./report.js"

const WRITER_SOFTWARE = "spectrl_writer"
const WINDOWS_FILE_URI = /^(file:\/\/)(?=[A-Za-z]:)/

function escapeXml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}

function attrs(pairs: Record<string, string | undefined>): string {
  return Object.entries(pairs)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => ` ${k}="${escapeXml(v!)}"`)
    .join("")
}

/** Python writes a parameter value with str(), which for a float is repr().
 *
 * A whole-valued number is always an integer here, because canonical CBOR
 * encodes integral metadata as integers, so str() gives "2" and not "2.0". */
function scalar(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : num(value)
  return String(value)
}

function cvXml(param: CvParam, names?: Record<string, string>): string {
  const pairs: Record<string, string | undefined> = {
    cvRef: param.accession.split(":", 1)[0],
    accession: param.accession,
    name: termName(param.accession, names),
  }
  // Empty string is a value; only null or undefined marks a flag parameter.
  if (param.value != null) pairs.value = scalar(param.value)
  if (param.unitAccession) {
    pairs.unitAccession = param.unitAccession
    pairs.unitName = termName(param.unitAccession, names)
    pairs.unitCvRef = param.unitAccession.split(":", 1)[0]
  }
  return `<cvParam${attrs(pairs)}/>`
}

function userXml(param: UserParam, names?: Record<string, string>): string {
  const pairs: Record<string, string | undefined> = { name: param.name }
  // mzML has no native numeric type, so annotate to let a reader recover it.
  if (typeof param.value === "number") {
    pairs.type = Number.isInteger(param.value) ? "xsd:integer" : "xsd:double"
  }
  if (param.value != null) pairs.value = scalar(param.value)
  if (param.unitAccession) {
    pairs.unitAccession = param.unitAccession
    pairs.unitName = termName(param.unitAccession, names)
    pairs.unitCvRef = param.unitAccession.split(":", 1)[0]
  }
  return `<userParam${attrs(pairs)}/>`
}

function paramsXml(params: CvParam[] | undefined, userParams: UserParam[] | undefined,
                   names?: Record<string, string>): string {
  return [...(params ?? []).map(p => cvXml(p, names)), ...(userParams ?? []).map(p => userXml(p, names))].join("")
}

function recordParams(record: ContextRecord | undefined, names?: Record<string, string>): string {
  return paramsXml(record?.params, record?.userParams, names)
}

/** Collects the header lists mzML requires, inventing only what it must. */
class Scaffold {
  sources = new Map<string, string>()
  instruments = new Map<string, string>()
  software = new Map<string, string>()
  processing = new Map<string, string>()
  private taken = new Set<string>()
  private allocated = new Map<string, string>()

  constructor(readonly result: ConversionResult, readonly names?: Record<string, string>) {}

  xmlId(kind: string, key: string): string {
    const cacheKey = `${kind}\u0000${key}`
    const cached = this.allocated.get(cacheKey)
    if (cached) return cached
    let candidate = key.replace(/[^A-Za-z0-9_.-]/g, "_") || kind
    if (!/^[A-Za-z_]/.test(candidate)) candidate = `${kind}_${candidate}`
    if (candidate !== key) {
      this.result.add("id_normalized", `${kind}.id`,
        `${kind} id "${key}" is not a valid XML id; wrote "${candidate}"`, "info")
    }
    let unique = candidate, suffix = 2
    while (this.taken.has(unique)) unique = `${candidate}_${suffix++}`
    if (unique !== candidate) {
      this.result.add("id_deduplicated", `${kind}.id`,
        `${kind} id "${candidate}" is already used by another record; wrote "${unique}"`, "info")
    }
    this.taken.add(unique)
    this.allocated.set(cacheKey, unique)
    return unique
  }

  location(value: string): string {
    const fixed = value.replace(WINDOWS_FILE_URI, "$1/")
    if (fixed !== value) {
      this.result.add("location_uri_normalized", "source.location",
        `source location "${value}" is not a valid URI; wrote "${fixed}"`, "info")
    }
    return fixed
  }

  source(record: ContextRecord | null | undefined): Record<string, string | undefined> {
    if (!record) return {}
    const out: Record<string, string | undefined> = {}
    if (record.spectrumRef) out.externalSpectrumID = record.spectrumRef
    if (record.id) {
      const key = this.xmlId("sourceFile", record.id)
      if (!this.sources.has(key)) {
        const pairs: Record<string, string | undefined> = { id: key, name: record.name }
        if (record.location) pairs.location = this.location(record.location)
        // mzML has no element for these, so they become userParams.
        const external = (record.externalIds ?? [])
          .map(v => `<userParam${attrs({ name: "spectrl:external_id", value: v })}/>`).join("")
        this.sources.set(key, `<sourceFile${attrs(pairs)}>${recordParams(record, this.names)}${external}</sourceFile>`)
      }
      out.sourceFileRef = key
    } else if (record.externalIds?.length) {
      this.result.add("external_ids_without_source", "source.external_ids",
        "source external identifiers need a source file to attach to")
    }
    return out
  }

  /** A sourceFile id for references that point outside this document. */
  externalAnchor(): string {
    const key = this.xmlId("sourceFile", "spectrl_origin")
    if (!this.sources.has(key)) {
      this.sources.set(key, `<sourceFile${attrs({ id: key, name: "unknown", location: "file:///" })}>` +
        `<userParam${attrs({ name: "spectrl:synthesized", value: "origin of an external spectrum reference" })}/>` +
        `</sourceFile>`)
      this.result.add("synthesized_source_file", "precursor.sourceFileRef",
        "a placeholder sourceFile was written to anchor an external precursor reference", "info")
    }
    return key
  }

  softwareRef(record: ContextRecord | null | undefined, version: string): string {
    if (!record) {
      const writer = this.xmlId("software", WRITER_SOFTWARE)
      if (!this.software.has(writer)) {
        this.software.set(writer, `<software${attrs({ id: writer, version })}>` +
          `<userParam${attrs({ name: "spectrl:synthesized", value: "processing record carried no software context" })}/>` +
          `</software>`)
      }
      return writer
    }
    const key = this.xmlId("software", record.id ?? `software${this.software.size}`)
    if (!this.software.has(key)) {
      this.software.set(key,
        `<software${attrs({ id: key, version: String(record.version ?? "") })}>${recordParams(record, this.names)}</software>`)
    }
    return key
  }

  acquisition(record: ContextRecord | null | undefined, version: string): string | null {
    const value = record?.instrument
    if (!value) return null
    const key = this.xmlId("instrumentConfiguration", value.id ?? `instrument${this.instruments.size}`)
    if (!this.instruments.has(key)) {
      const components = value.components ?? []
      const componentXml = components.length
        ? `<componentList${attrs({ count: String(components.length) })}>` +
          components.map(c => `<${c.kind}${attrs({ order: String(c.order ?? 1) })}>` +
            `${recordParams(c, this.names)}</${c.kind}>`).join("") + `</componentList>`
        : ""
      const softwareXml = value.software
        ? `<softwareRef${attrs({ ref: this.softwareRef(value.software, version) })}/>` : ""
      this.instruments.set(key, `<instrumentConfiguration${attrs({ id: key })}>` +
        `${recordParams(value, this.names)}${componentXml}${softwareXml}</instrumentConfiguration>`)
    }
    return key
  }

  processingRef(records: ContextRecord[] | undefined, version: string): string {
    const key = this.xmlId("dataProcessing", `processing${this.processing.size}`)
    const list = records ?? []
    const methods = list.map((record, order) => {
      // The benchmark writer refused these and stripped the lossy record with
      // them. They are the provenance a recipient most needs.
      let extra = ""
      if (record.operation) {
        extra += `<userParam${attrs({ name: "spectrl:operation", value: String(record.operation) })}/>`
        if (record.revision != null) {
          extra += `<userParam${attrs({ name: "spectrl:operation_revision", value: String(record.revision) })}/>`
        }
        this.result.add("operation_as_user_param", "processing.operation",
          `processing operation ${record.operation} written as a userParam; mzML has no controlled term for it`,
          "info")
      }
      return `<processingMethod${attrs({ order: String(order), softwareRef: this.softwareRef(record.software, version) })}>` +
        `${recordParams(record, this.names)}${extra}</processingMethod>`
    })
    if (!list.length) {
      methods.push(`<processingMethod${attrs({ order: "0", softwareRef: this.softwareRef(null, version) })}/>`)
    }
    this.processing.set(key, `<dataProcessing${attrs({ id: key })}>${methods.join("")}</dataProcessing>`)
    return key
  }
}

const PACKAGE_VERSION = "3.0.0"

/** One binaryDataArray per array, base64 of little-endian float64 words.
 *
 * mzML carries reconstructed values, so the arrays are written as decoded, not
 * as the token's encoded words. */
function binaryArrays(spectrum: DecodedSpectrum, scaffold: Scaffold, names: Record<string, string> | undefined,
                      version: string): string {
  // The per-array maps are keyed the way a caller addresses an array -- "mz"
  // for a core array, the extra-array key otherwise -- not by accession.
  const arrays: { accession: string, values: ArrayLike<number>, name?: string, key: string }[] = []
  for (const [key, accession] of [["mz", "MS:1000514"], ["intensity", "MS:1000515"], ["charge", "MS:1000516"]] as const) {
    const values = spectrum[key]
    if (values != null) arrays.push({ accession, values, name: spectrum.arrayNames?.[key], key })
  }
  for (const [key, values] of Object.entries(spectrum.extraArrays ?? {})) {
    const accession = key.includes(":") ? key : "MS:1000786"
    arrays.push({ accession, values, name: key.includes(":") ? spectrum.arrayNames?.[key] : key, key })
  }

  const parts = arrays.map(({ accession, values, name, key }) => {
    const words = new Float64Array(values.length)
    for (let i = 0; i < values.length; i++) words[i] = values[i]!
    const encoded = base64(new Uint8Array(words.buffer, words.byteOffset, words.byteLength))
    const unit = spectrum.arrayUnits?.[key]
    const identity: CvParam = {
      accession,
      value: accession === "MS:1000786" ? (name ?? null) : null,
      unitAccession: unit,
    }
    const records = spectrum.arrayProcessing?.[key]
    const ref = records?.length ? { dataProcessingRef: scaffold.processingRef(records, version) } : {}
    return `<binaryDataArray${attrs({ encodedLength: String(encoded.length), ...ref })}>` +
      cvXml({ accession: "MS:1000523" }, names) +
      cvXml({ accession: "MS:1000576" }, names) +
      cvXml(identity, names) +
      (spectrum.arrayParams?.[key] ?? []).map(p => cvXml(p, names)).join("") +
      (spectrum.arrayUserParams?.[key] ?? []).map(p => userXml(p, names)).join("") +
      `<binary>${encoded}</binary></binaryDataArray>`
  })
  return `<binaryDataArrayList${attrs({ count: String(arrays.length) })}>${parts.join("")}</binaryDataArrayList>`
}

export interface WriteMzmlOptions {
  /** CV term names for accessions outside the set spectrl defines. */
  names?: Record<string, string>
  /** Indent the output. Off by default, matching a compact interchange file. */
  indent?: boolean
}

/** Write one decoded spectrum as a complete mzML 1.1.0 document.
 *
 * Nothing is refused. An absent spectrum id is synthesized, because mzML
 * requires one; extensions, which have no mzML element, are reported. */
export function writeMzml(spectrum: DecodedSpectrum, opts: WriteMzmlOptions = {}): ConversionResult {
  const { names } = opts
  const result = new ConversionResult("mzml")
  const scaffold = new Scaffold(result, names)
  const version = PACKAGE_VERSION

  let spectrumId = spectrum.id
  if (!spectrumId) {
    spectrumId = "index=0"
    result.add("synthesized_id", "spectrum.id",
      "the token carried no spectrum id; mzML requires one, so 'index=0' was written", "info")
  }
  for (const [scope, value] of [["spectrum", spectrum.extensions], ["array", spectrum.arrayExtensions]] as const) {
    const keys = Object.keys(value ?? {})
    if (keys.length) {
      result.add("extensions_dropped", `${scope}.extensions`,
        `${scope}-level extensions (${keys.sort().join(", ")}) have no mzML representation`)
    }
  }
  if (Object.keys(spectrum.cvVersions ?? {}).length) {
    result.add("cv_versions_as_cv_list", "cv_versions",
      "ontology versions written onto the cvList entries they describe", "info")
  }

  let body = paramsXml(spectrum.params, spectrum.userParams, names)
  // Registered before the scan and precursor records so the sourceFileList
  // comes out in the same order as the Python writer's.
  const spectrumSource = scaffold.source(spectrum.source)

  if (spectrum.scans?.length || spectrum.scanCombination) {
    const scans = (spectrum.scans ?? []).map(scan => {
      const instrument = scaffold.acquisition(scan.acquisition, version)
      const windows = scan.windows?.length
        ? `<scanWindowList${attrs({ count: String(scan.windows.length) })}>` +
          scan.windows.map(w => `<scanWindow>${paramsXml(w.params, w.userParams, names)}</scanWindow>`).join("") +
          `</scanWindowList>`
        : ""
      const ref = scan.processing?.length ? { dataProcessingRef: scaffold.processingRef(scan.processing, version) } : {}
      return `<scan${attrs({ ...scaffold.source(scan.source), instrumentConfigurationRef: instrument ?? undefined, ...ref })}>` +
        `${paramsXml(scan.params, scan.userParams, names)}${windows}</scan>`
    })
    const combination = spectrum.scanCombination ? cvXml(spectrum.scanCombination, names) : ""
    body += `<scanList${attrs({ count: String(spectrum.scans?.length ?? 0) })}>${combination}${scans.join("")}</scanList>`
  }

  if (spectrum.precursors?.length) {
    const entries = spectrum.precursors.map(precursor => {
      const source = scaffold.source(precursor.source)
      if (source.externalSpectrumID && !source.sourceFileRef) source.sourceFileRef = scaffold.externalAnchor()
      const isolation = precursor.isolationWindow
        ? `<isolationWindow>${paramsXml(precursor.isolationWindow.params, precursor.isolationWindow.userParams, names)}</isolationWindow>` : ""
      const ions = precursor.selectedIons?.length
        ? `<selectedIonList${attrs({ count: String(precursor.selectedIons.length) })}>` +
          precursor.selectedIons.map(i => `<selectedIon>${paramsXml(i.params, i.userParams, names)}</selectedIon>`).join("") +
          `</selectedIonList>` : ""
      const activation = precursor.activation
        ? `<activation>${paramsXml(precursor.activation.params, precursor.activation.userParams, names)}</activation>` : ""
      return `<precursor${attrs(source)}>${isolation}${ions}${activation}</precursor>`
    })
    body += `<precursorList${attrs({ count: String(spectrum.precursors.length) })}>${entries.join("")}</precursorList>`
  }

  if (spectrum.products?.length) {
    const entries = spectrum.products.map(product => {
      const isolation = product.isolationWindow
        ? `<isolationWindow>${paramsXml(product.isolationWindow.params, product.isolationWindow.userParams, names)}</isolationWindow>` : ""
      return `<product>${isolation}</product>`
    })
    body += `<productList${attrs({ count: String(spectrum.products.length) })}>${entries.join("")}</productList>`
  }

  body += binaryArrays(spectrum, scaffold, names, version)

  // A scan-level instrument alone still needs the run's required default reference.
  const instrument = scaffold.acquisition(spectrum.acquisition, version) ?? scaffold.instruments.keys().next().value ?? null
  const processing = scaffold.processingRef(spectrum.processing, version)
  const spectrumXml =
    `<spectrum${attrs({ id: spectrumId, index: "0", defaultArrayLength: String(spectrum.defaultArrayLength), ...spectrumSource })}>` +
    `${body}</spectrum>`

  result.text = document(spectrumXml, spectrum, scaffold, instrument, processing, opts.indent ?? true)
  return result
}

/** Wrap the spectrum in the header lists mzML 1.1.0 requires. */
function document(spectrumXml: string, spectrum: DecodedSpectrum, scaffold: Scaffold,
                  instrument: string | null, processing: string, indent: boolean): string {
  const declared = spectrum.cvVersions ?? {}
  const entries: [string, string, string][] = [
    ["MS", "PSI Mass Spectrometry Ontology", "https://purl.obolibrary.org/obo/ms.obo"],
    ["UO", "Unit Ontology", "https://purl.obolibrary.org/obo/uo.obo"],
  ]
  for (const prefix of Object.keys(declared).sort()) {
    if (prefix !== "MS" && prefix !== "UO") entries.push([prefix, prefix, ""])
  }
  const cvList = `<cvList${attrs({ count: String(entries.length) })}>` +
    entries.map(([prefix, fullName, uri]) =>
      // The token's declared version is the one this document's accessions were
      // written under, so it is restored where mzML expects it.
      `<cv${attrs({ id: prefix, fullName, URI: uri, version: declared[prefix] })}/>`).join("") + `</cvList>`

  const sourceFiles = scaffold.sources.size
    ? `<sourceFileList${attrs({ count: String(scaffold.sources.size) })}>${[...scaffold.sources.values()].join("")}</sourceFileList>`
    : ""
  if (!scaffold.software.size) scaffold.softwareRef(null, PACKAGE_VERSION)
  if (!scaffold.instruments.size) {
    scaffold.instruments.set("instrument0", `<instrumentConfiguration${attrs({ id: "instrument0" })}/>`)
    instrument = "instrument0"
  }

  const raw = `<mzML${attrs({ xmlns: "http://psi.hupo.org/ms/mzml", version: "1.1.0" })}>` +
    cvList +
    `<fileDescription><fileContent/>${sourceFiles}</fileDescription>` +
    `<softwareList${attrs({ count: String(scaffold.software.size) })}>${[...scaffold.software.values()].join("")}</softwareList>` +
    `<instrumentConfigurationList${attrs({ count: String(scaffold.instruments.size) })}>${[...scaffold.instruments.values()].join("")}</instrumentConfigurationList>` +
    `<dataProcessingList${attrs({ count: String(scaffold.processing.size) })}>${[...scaffold.processing.values()].join("")}</dataProcessingList>` +
    `<run${attrs({ id: "spectrl", defaultInstrumentConfigurationRef: instrument ?? undefined })}>` +
    `<spectrumList${attrs({ count: "1", defaultDataProcessingRef: processing })}>${spectrumXml}</spectrumList>` +
    `</run></mzML>`
  const text = elementTreeSpacing(raw)
  return indent ? prettyXml(text) : `<?xml version="1.0" encoding="utf-8"?>${text}`
}

/** Put a space before every self-closing bracket, the way Python's
 * ElementTree writes them, so both implementations emit the same bytes.
 * Safe to apply to the whole document: `>` never appears in an attribute value
 * (it is escaped) nor in base64, so `/>` only ever ends a tag. */
function elementTreeSpacing(xml: string): string {
  // ElementTree collapses an element with no content to a self-closing tag,
  // so `<scan></scan>` is written `<scan />`. Collapsing a child never leaves
  // its parent empty, so one pass is enough.
  return xml
    .replace(/<([A-Za-z][\w.-]*)((?:\s[^<>]*)?)><\/\1>/g, "<$1$2 />")
    .replace(/([^\s])\/>/g, "$1 />")
}

/** Minimal pretty-printer, so the output stays readable without a DOM. */
function prettyXml(xml: string): string {
  const out: string[] = ['<?xml version="1.0" ?>']
  let depth = 0
  for (const token of xml.split(/(<[^>]+>)/).filter(t => t.trim())) {
    if (!token.startsWith("<")) {
      out[out.length - 1] += token
      continue
    }
    if (token.startsWith("</")) {
      depth--
      const previous = out[out.length - 1]!
      // Keep a text-only element on one line, as minidom does.
      if (!previous.trimStart().startsWith("</") && !previous.endsWith(">")) {
        out[out.length - 1] = previous + token
        continue
      }
      out.push("  ".repeat(depth) + token)
      continue
    }
    out.push("  ".repeat(depth) + token)
    if (!token.endsWith("/>")) depth++
  }
  return out.join("\n") + "\n"
}
