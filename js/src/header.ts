/**
 * CBOR header build/parse for the spectrl integer-key registry.
 *
 * Top-level keys (mirror mzML <spectrum>):
 *   0 defaultArrayLength, 1 id, 2 spectrum params, 3 scanList,
 *   4 precursorList, 5 productList, 6 binaryDataArrayList, 7 interp,
 *   8 userParamList. The format version lives only in the token magic, and
 *   the checksum only in the trailing token part.
 */

import {
  decodeParamKey,
  decodeTail,
  decodeUnitTail,
  encodeParamKey,
  encodeUnit,
} from "./cv.js";
/** An integer/string-keyed map, as decoded from CBOR (mapsAsObjects: false). */
export type MsgMap = Map<number | string, unknown>;
import type {
  Activation,
  CvParam,
  DecodedSpectrum,
  InlineSpectrum,
  IsolationWindow,
  Precursor,
  Product,
  Scan,
  ScanWindow,
  SelectedIon,
  UserParam,
} from "./model.js";
import { FORMAT_VERSION } from "./token.js";
import { DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_FP, DESC_NAME, DESC_TYPE, DESC_UNIT } from "./format.js";
export { DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_FP, DESC_NAME, DESC_TYPE, DESC_UNIT } from "./format.js";

/**
 * Array-descriptor keys (header key 6). Integer-keyed like the header itself:
 * the names were a fixed vocabulary spelled out in full on every array of every
 * token, costing more than the values they labelled.
 */
const ACCESSION_RE = /^[A-Za-z][A-Za-z0-9]*:[A-Za-z0-9]+$/;

function validateAccession(accession: string): void {
  if (!ACCESSION_RE.test(accession)) throw new Error(`invalid CV accession ${JSON.stringify(accession)}`);
}

export interface Descriptor {
  type: number;
  array: number;
  comp: number;
  fp?: number;
  /** Free-text descriptor name; present only for non-standard (MS:1000786) arrays. */
  name?: string;
  unit?: string;
  /** This array's compressed blob, embedded inline in the CBOR document. */
  data?: Uint8Array;
}

// ── CvParam map ───────────────────────────────────────────────────────────────

function encodeParamMap(params: CvParam[]): MsgMap {
  const m: MsgMap = new Map();
  for (const p of params) {
    validateAccession(p.accession);
    if (p.unitAccession != null) validateAccession(p.unitAccession);
    if (p.value != null && typeof p.value !== "string" && typeof p.value !== "number") {
      throw new Error(`unsupported CV value type for ${p.accession}`);
    }
    const key = encodeParamKey(p.accession);
    if (m.has(key)) {
      throw new Error(`duplicate CV accession ${p.accession} in parameter list`);
    }
    let val: unknown;
    if (p.value === null || p.value === undefined) {
      val = null;
    } else if (p.unitAccession !== null && p.unitAccession !== undefined) {
      val = [p.value, encodeUnit(p.unitAccession)];
    } else {
      val = p.value;
    }
    m.set(key, val);
  }
  return m;
}

function decodeParamMap(m: MsgMap | undefined): CvParam[] {
  if (!m) return [];
  if (!(m instanceof Map)) throw new Error("CV parameter list must be a map");
  const out: CvParam[] = [];
  for (const [rawKey, rawVal] of m) {
    if (typeof rawKey !== "string" && (typeof rawKey !== "number" || !Number.isSafeInteger(rawKey) || rawKey < 0)) {
      throw new Error(`invalid CV parameter key ${String(rawKey)}`);
    }
    const accession = decodeParamKey(rawKey as number | string);
    validateAccession(accession);
    if (rawVal === null || rawVal === undefined) {
      out.push({ accession });
    } else if (Array.isArray(rawVal)) {
      if (rawVal.length !== 2) throw new Error(`CV parameter ${accession} value/unit pair must have two items`);
      out.push({
        accession,
        value: rawVal[0] as number | string,
        unitAccession: decodeUnitTail(rawVal[1] as number | [string, number]),
      });
    } else {
      out.push({ accession, value: rawVal as number | string });
    }
  }
  return out;
}

// ── userParams ────────────────────────────────────────────────────────────────

function encodeUserParam(u: UserParam): MsgMap {
  if (typeof u.name !== "string" || u.name.length === 0) throw new Error("user parameter name must be non-empty");
  if (u.unitAccession != null) validateAccession(u.unitAccession);
  const m: MsgMap = new Map();
  m.set("n", u.name);
  if (u.value !== null && u.value !== undefined) m.set("v", u.value);
  if (u.type !== null && u.type !== undefined) m.set("t", u.type);
  if (u.unitAccession !== null && u.unitAccession !== undefined) m.set("u", encodeUnit(u.unitAccession));
  return m;
}

function encodeUserParams(us: UserParam[]): MsgMap[] {
  return us.map(encodeUserParam);
}

function decodeUserParams(raw: MsgMap[] | undefined): UserParam[] {
  if (!raw) return [];
  if (!Array.isArray(raw)) throw new Error("user parameter list must be an array");
  return raw.map((m) => {
    if (!(m instanceof Map)) throw new Error("user parameter must be a map");
    const name = m.get("n");
    if (typeof name !== "string" || name.length === 0) throw new Error("user parameter name must be non-empty");
    return ({
    name,
    value: (m.get("v") as string | number | undefined) ?? null,
    type: (m.get("t") as string | undefined) ?? null,
    unitAccession: m.has("u") ? decodeUnitTail(m.get("u") as number | [string, number]) : null,
  });
  });
}

// ── scans / precursors / products ─────────────────────────────────────────────

function encodeScan(s: Scan): MsgMap {
  const d: MsgMap = new Map();
  d.set(0, encodeParamMap(s.params));
  if (s.windows && s.windows.length) d.set(1, s.windows.map((w) => encodeParamMap(w.params)));
  if (s.userParams && s.userParams.length) d.set(2, encodeUserParams(s.userParams));
  return d;
}

function decodeScan(d: MsgMap): Scan {
  const params = decodeParamMap(d.get(0) as MsgMap | undefined);
  const wins = (d.get(1) as MsgMap[] | undefined) ?? [];
  const windows: ScanWindow[] = wins.map((w) => ({ params: decodeParamMap(w) }));
  const userParams = decodeUserParams(d.get(2) as MsgMap[] | undefined);
  return { params, windows, userParams };
}

function encodePrecursor(p: Precursor): MsgMap {
  const d: MsgMap = new Map();
  if (p.isolationWindow) d.set(0, encodeParamMap(p.isolationWindow.params));
  if (p.selectedIons && p.selectedIons.length) d.set(1, p.selectedIons.map((si) => encodeParamMap(si.params)));
  if (p.activation) d.set(2, encodeParamMap(p.activation.params));
  return d;
}

function decodePrecursor(d: MsgMap): Precursor {
  const iw = d.has(0) ? ({ params: decodeParamMap(d.get(0) as MsgMap) } as IsolationWindow) : null;
  const sis = (d.get(1) as MsgMap[] | undefined) ?? [];
  const selectedIons: SelectedIon[] = sis.map((si) => ({ params: decodeParamMap(si) }));
  const activation: Activation | null = d.has(2) ? { params: decodeParamMap(d.get(2) as MsgMap) } : null;
  return { isolationWindow: iw, selectedIons, activation };
}

function encodeProduct(p: Product): MsgMap {
  const d: MsgMap = new Map();
  if (p.isolationWindow) d.set(0, encodeParamMap(p.isolationWindow.params));
  return d;
}

function decodeProduct(d: MsgMap): Product {
  const iw = d.has(0) ? ({ params: decodeParamMap(d.get(0) as MsgMap) } as IsolationWindow) : null;
  return { isolationWindow: iw };
}

// ── full header ───────────────────────────────────────────────────────────────

export function buildHeaderMap(spec: InlineSpectrum, descriptors: Descriptor[]): MsgMap {
  const h: MsgMap = new Map();
  h.set(0, spec.defaultArrayLength);
  if (spec.id !== null && spec.id !== undefined) h.set(1, spec.id);
  if (spec.params && spec.params.length) h.set(2, encodeParamMap(spec.params));

  const scans = spec.scans ?? [];
  if (scans.length || (spec.scanCombination !== null && spec.scanCombination !== undefined)) {
    const scanEntry: MsgMap = new Map();
    scanEntry.set("s", scans.map(encodeScan));
    if (spec.scanCombination) scanEntry.set("c", accessionTailOf(spec.scanCombination.accession));
    h.set(3, scanEntry);
  }
  if (spec.precursors && spec.precursors.length) h.set(4, spec.precursors.map(encodePrecursor));
  if (spec.products && spec.products.length) h.set(5, spec.products.map(encodeProduct));

  h.set(
    6,
    descriptors.map((d) => {
      const dm: MsgMap = new Map();
      dm.set(DESC_TYPE, d.type);
      dm.set(DESC_ARRAY, d.array);
      dm.set(DESC_COMP, d.comp);
      if (d.fp !== undefined) dm.set(DESC_FP, d.fp);
      if (d.name !== undefined) dm.set(DESC_NAME, d.name);
      if (d.unit !== undefined) dm.set(DESC_UNIT, encodeUnit(d.unit));
      dm.set(DESC_DATA, d.data);
      return dm;
    }),
  );

  if (spec.interp !== null && spec.interp !== undefined) h.set(7, spec.interp);
  if (spec.userParams && spec.userParams.length) h.set(8, encodeUserParams(spec.userParams));
  return h;
}

function accessionTailOf(accession: string): number {
  return parseInt(accession.split(":")[1]!, 10);
}

export function parseHeaderMap(h: MsgMap): { decoded: DecodedSpectrum; descriptors: Descriptor[] } {
  const formatVersion = FORMAT_VERSION;
  const defaultArrayLength = h.get(0) as number;
  const id = (h.get(1) as string | undefined) ?? null;
  const params = decodeParamMap(h.get(2) as MsgMap | undefined);

  let scans: Scan[] = [];
  let scanCombination: CvParam | null = null;
  const scanEntry = h.get(3) as MsgMap | undefined;
  if (scanEntry) {
    scans = ((scanEntry.get("s") as MsgMap[] | undefined) ?? []).map(decodeScan);
    if (scanEntry.has("c")) scanCombination = { accession: decodeTail(scanEntry.get("c") as number) };
  }

  const precursors = ((h.get(4) as MsgMap[] | undefined) ?? []).map(decodePrecursor);
  const products = ((h.get(5) as MsgMap[] | undefined) ?? []).map(decodeProduct);
  const interp = (h.get(7) as string | undefined) ?? null;
  const userParams = decodeUserParams(h.get(8) as MsgMap[] | undefined);
  // The trailing token part; decodeCbor fills it in after verification.
  const checksum = "";

  const rawDescriptors = (h.get(6) as MsgMap[] | undefined) ?? [];
  const descriptors: Descriptor[] = rawDescriptors.map((d) => ({
    type: d.get(DESC_TYPE) as number,
    array: d.get(DESC_ARRAY) as number,
    comp: d.get(DESC_COMP) as number,
    fp: d.has(DESC_FP) ? (d.get(DESC_FP) as number) : undefined,
    name: d.has(DESC_NAME) ? (d.get(DESC_NAME) as string) : undefined,
    unit: d.has(DESC_UNIT) ? decodeUnitTail(d.get(DESC_UNIT) as number | [string, number] | string) : undefined,
    data: d.has(DESC_DATA) ? (d.get(DESC_DATA) as Uint8Array) : undefined,
  }));

  const decoded: DecodedSpectrum = {
    defaultArrayLength,
    mz: null,
    intensity: null,
    charge: null,
    id,
    params,
    scans,
    scanCombination,
    precursors,
    products,
    interp,
    userParams,
    extraArrays: {},
    arrayUnits: {},
    checksum,
    formatVersion,
  };
  return { decoded, descriptors };
}
