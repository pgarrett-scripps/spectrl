/** Size introspection for tokens (used by the demo and handy for tooling). */

import { b64urlDecode } from "./base64url.js";
import { cborDecode } from "./cbor.js";
import { tokenChecksum } from "./checksum.js";
import { ARRAY_CHARGE, ARRAY_INTENSITY, ARRAY_MZ, ARRAY_NON_STANDARD, ION_MOBILITY_ARRAY_TAILS, decodeTail, decodeUnitTail } from "./cv.js";
import { SpectrlDecodeError } from "./errors.js";
import { DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_FP, DESC_NAME, DESC_TYPE, DESC_UNIT } from "./header.js";
import { MAGIC } from "./token.js";

export interface TokenPart {
  label: string;
  /** Size in payload bytes (compressed blob bytes; "header" is everything else). */
  bytes: number;
  /** Compression codec accession tail; absent for the header part. */
  comp?: number;
  accession?: string;
  typeAccession?: string;
  fixedPoint?: number;
  unitAccession?: string;
}

function arrayLabel(tail: number, name: string | undefined): string {
  if (tail === ARRAY_MZ) return "m/z";
  if (tail === ARRAY_INTENSITY) return "intensity";
  if (tail === ARRAY_CHARGE) return "charge";
  if (ION_MOBILITY_ARRAY_TAILS.has(tail)) return "ion mobility";
  if (tail === 1000517) return "signal-to-noise";
  if (tail === ARRAY_NON_STANDARD) return name ?? decodeTail(tail);
  return decodeTail(tail);
}

/**
 * Break a token's payload into header bytes vs each array's compressed blob.
 * Sizes are CBOR-document bytes (before base64url expansion).
 */
export function tokenBreakdown(token: string): TokenPart[] {
  const prefix = `${MAGIC}.`;
  if (!token.startsWith(prefix)) {
    throw new SpectrlDecodeError(`Not a ${MAGIC} token`);
  }
  const pieces = token.slice(prefix.length).split(".");
  if (pieces.length !== 2 || pieces[1] !== tokenChecksum(`${MAGIC}.${pieces[0]}`)) {
    throw new SpectrlDecodeError(`Not a valid ${MAGIC} token`);
  }
  const raw = b64urlDecode(pieces[0]!);
  const doc = cborDecode(raw);
  if (!(doc instanceof Map)) throw new SpectrlDecodeError("spectrl payload is not a CBOR map");

  const parts: TokenPart[] = [];
  let blobTotal = 0;
  const descs = (doc.get(6) as Array<Map<number, unknown>> | undefined) ?? [];
  for (const d of descs) {
    const blob = d.get(DESC_DATA) as Uint8Array | undefined;
    const bytes = blob?.length ?? 0;
    blobTotal += bytes;
    const tail = d.get(DESC_ARRAY) as number;
    parts.push({
      label: arrayLabel(d.get(DESC_ARRAY) as number, d.get(DESC_NAME) as string | undefined),
      bytes,
      comp: d.get(DESC_COMP) as number,
      accession: decodeTail(tail),
      typeAccession: decodeTail(d.get(DESC_TYPE) as number),
      ...(d.has(DESC_FP) ? { fixedPoint: d.get(DESC_FP) as number } : {}),
      ...(d.has(DESC_UNIT) ? {
        unitAccession: decodeUnitTail(d.get(DESC_UNIT) as number | [string, number] | string),
      } : {}),
    });
  }
  parts.unshift({ label: "header", bytes: raw.length - blobTotal });
  return parts;
}
