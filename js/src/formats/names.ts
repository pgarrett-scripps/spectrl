/** CV term names for formats that require them, without bundling an ontology.
 *
 * mzML declares `name` required on every cvParam, but a token carries
 * accessions only. spectrl does not ship psi-ms.obo -- it is larger than the
 * library and would tie releases to ontology releases -- so names come from
 * what the format defines itself, and anything else is written with the
 * accession as its name. Mirrors src/spectrl/formats/_names.py. */

import { ArrayAccession } from "../array_accession.js"
import { UnitAccession } from "../unit_accession.js"

const CORE: Record<string, string> = {
  "MS:1000514": "m/z array",
  "MS:1000515": "intensity array",
  "MS:1000516": "charge array",
  "MS:1000786": "non-standard data array",
  "MS:1000523": "64-bit float",
  "MS:1000521": "32-bit float",
  "MS:1000519": "32-bit integer",
  "MS:1000576": "no compression",
  "MS:1000127": "centroid spectrum",
  "MS:1000128": "profile spectrum",
  "MS:1000129": "negative scan",
  "MS:1000130": "positive scan",
  "MS:1000511": "ms level",
  "MS:1000285": "total ion current",
  "MS:1000504": "base peak m/z",
  "MS:1000505": "base peak intensity",
  "MS:1000527": "highest observed m/z",
  "MS:1000528": "lowest observed m/z",
  "MS:1000016": "scan start time",
  "MS:1000927": "ion injection time",
  "MS:1000744": "selected ion m/z",
  "MS:1000041": "charge state",
  "MS:1000042": "peak intensity",
  "MS:1000045": "collision energy",
  "MS:1000501": "scan window lower limit",
  "MS:1000500": "scan window upper limit",
}

function fromEnum(source: Record<string, string>): Record<string, string> {
  // The generated enums spell the PSI-MS term in their member names, so
  // RAW_ION_MOBILITY already carries "raw ion mobility".
  const out: Record<string, string> = {}
  for (const [member, accession] of Object.entries(source)) {
    out[accession] = member.replace(/_/g, " ").toLowerCase()
  }
  return out
}

/** Core spellings win: an enum member name is a mechanical transform, while
 * these are the terms as PSI-MS writes them. */
export const KNOWN: Record<string, string> = {
  ...fromEnum(ArrayAccession as unknown as Record<string, string>),
  ...fromEnum(UnitAccession as unknown as Record<string, string>),
  ...CORE,
}

export function termName(accession: string, names?: Record<string, string>): string {
  return names?.[accession] ?? KNOWN[accession] ?? accession
}
