/** CV accession ↔ integer-tail mapping (mirrors the Python `cv` module). */

import {
  ARRAY_CHARGE,
  ARRAY_INTENSITY,
  ARRAY_MZ,
  ARRAY_NON_STANDARD,
  COMP_NUMLIN_ZLIB,
  COMP_NUMPIC_ZLIB,
  COMP_NUMSLOF_ZLIB,
  COMP_ZLIB,
  COMP_ZSTD,
  COMP_BYTE_SHUFFLED_ZSTD,
  COMP_NUMLIN_ZSTD,
  COMP_NUMPIC_ZSTD,
  COMP_NUMSLOF_ZSTD,
  ION_MOBILITY_ARRAY_TAILS,
  TYPE_FLOAT32,
  TYPE_FLOAT64,
  TYPE_INT32,
} from "./format.js";

export {
  ARRAY_CHARGE,
  ARRAY_INTENSITY,
  ARRAY_MZ,
  ARRAY_NON_STANDARD,
  COMP_NUMLIN_ZLIB,
  COMP_NUMPIC_ZLIB,
  COMP_NUMSLOF_ZLIB,
  COMP_ZLIB,
  COMP_ZSTD,
  COMP_BYTE_SHUFFLED_ZSTD,
  COMP_NUMLIN_ZSTD,
  COMP_NUMPIC_ZSTD,
  COMP_NUMSLOF_ZSTD,
  ION_MOBILITY_ARRAY_TAILS,
  TYPE_FLOAT32,
  TYPE_FLOAT64,
  TYPE_INT32,
};

const DEFAULT_PARAM_ONTOLOGY = "MS";
const DEFAULT_UNIT_ONTOLOGY = "UO";

export function accessionTail(accession: string): number {
  return parseInt(accession.split(":")[1]!, 10);
}

export function accessionOntology(accession: string): string {
  return accession.split(":")[0]!;
}

function pad7(tail: number): string {
  return String(tail).padStart(7, "0");
}

export function decodeTail(tail: number, ontology: string = DEFAULT_PARAM_ONTOLOGY): string {
  return `${ontology}:${pad7(tail)}`;
}

/** True when the accession's tail is exactly 7 digits, i.e. survives the
 * 7-digit zero-padded reconstruction used for tail-encoded keys. */
function hasSevenDigitTail(accession: string): boolean {
  const idx = accession.indexOf(":");
  return idx >= 0 && /^\d{7}$/.test(accession.slice(idx + 1));
}

/**
 * Encode an accession as a param-map key: a bare integer tail for `MS:` keys
 * with 7-digit tails, or the full accession string (e.g. `"UO:0000031"`,
 * `"NCIT:C25330"`) otherwise, keeping the key a hashable CBOR-map scalar.
 */
export function encodeParamKey(accession: string): number | string {
  return accessionOntology(accession) === DEFAULT_PARAM_ONTOLOGY && hasSevenDigitTail(accession)
    ? accessionTail(accession)
    : accession;
}

export function decodeParamKey(key: number | string): string {
  return typeof key === "string" ? key : decodeTail(key);
}

/** Encode a unit accession: a bare tail (UO:), `[ontology, tail]` for other
 * ontologies, or the full accession string when the tail is not exactly 7
 * digits (e.g. `"MOD:00046"`, which would not round-trip through padding). */
export function encodeUnit(unitAccession: string): number | [string, number] | string {
  if (!hasSevenDigitTail(unitAccession)) return unitAccession;
  const onto = accessionOntology(unitAccession);
  const tail = accessionTail(unitAccession);
  return onto === DEFAULT_UNIT_ONTOLOGY ? tail : [onto, tail];
}

export function decodeUnitTail(t: number | [string, number] | string): string {
  if (typeof t === "string") return t;
  if (Array.isArray(t)) return `${t[0]}:${pad7(t[1])}`;
  return `${DEFAULT_UNIT_ONTOLOGY}:${pad7(t)}`;
}
