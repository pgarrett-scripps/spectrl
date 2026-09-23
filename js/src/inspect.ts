/** Size introspection for tokens (used by the demo and handy for tooling). */

import { descriptor, type Operation } from "./pipeline.js"
import { readTokenDocument, readTokenPayload } from "./cbor_format.js"
import type { DecodeLimits } from "./limits.js"
import { ARRAY_CHARGE, ARRAY_INTENSITY, ARRAY_MZ, ARRAY_NON_STANDARD, ION_MOBILITY_ARRAY_TAILS, decodeTail, decodeUnitTail } from "./cv.js";
import { DESC_ARRAY, DESC_DATA, DESC_NAME, DESC_TYPE, DESC_UNIT } from "./header.js";

export interface TokenPart {
  label: string;
  /** Size in payload bytes (encoded blob bytes; "header" is everything else). */
  bytes: number;
  encoding?: Operation
  fidelity?: "exact" | "lossy"
  accession?: string;
  typeAccession?: string;
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
 * Break a token's payload into header bytes vs each array's encoded blob.
 * Sizes are expanded CBOR bytes, before outer compression and base64url encoding.
 */
export function tokenBreakdown(token: string, limits?: DecodeLimits): TokenPart[] {
  const { doc } = readTokenDocument(token, limits)
  const raw = readTokenPayload(token, limits)

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
      encoding: descriptor(d.get(2) as any),
      fidelity: d.get(7) === 0 ? "exact" : "lossy",
      accession: decodeTail(tail),
      typeAccession: decodeTail(d.get(DESC_TYPE) as number),
      ...(d.has(DESC_UNIT) ? {
        unitAccession: decodeUnitTail(d.get(DESC_UNIT) as number | [string, number] | string),
      } : {}),
    });
  }
  parts.unshift({ label: "header", bytes: raw.length - blobTotal });
  return parts;
}
