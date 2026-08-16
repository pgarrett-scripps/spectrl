/** Size introspection for tokens (used by the demo and handy for tooling). */

import { b64urlDecode } from "./base64url.js";
import { cborDecode } from "./cbor.js";
import { ARRAY_CHARGE, ARRAY_INTENSITY, ARRAY_MZ, ARRAY_NON_STANDARD, ION_MOBILITY_ARRAY_TAILS, decodeTail } from "./cv.js";
import { SpectrlDecodeError } from "./errors.js";
import { DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_NAME } from "./header.js";
import { MAGIC } from "./token.js";

export interface TokenPart {
  label: string;
  /** Size in payload bytes (compressed blob bytes; "header" is everything else). */
  bytes: number;
  /** Compression codec accession tail; absent for the header part. */
  comp?: number;
}

function arrayLabel(tail: number, name: string | undefined): string {
  if (tail === ARRAY_MZ) return "m/z";
  if (tail === ARRAY_INTENSITY) return "intensity";
  if (tail === ARRAY_CHARGE) return "charge";
  if (ION_MOBILITY_ARRAY_TAILS.has(tail)) return "ion mobility";
  if (tail === ARRAY_NON_STANDARD) return name ?? decodeTail(tail);
  return decodeTail(tail);
}

/**
 * Break a token's payload into header bytes vs each array's compressed blob.
 * Sizes are CBOR-document bytes (before base64url expansion).
 */
export function tokenBreakdown(token: string): TokenPart[] {
  const pieces = token.split(".");
  if (pieces[0] !== MAGIC || (pieces.length !== 2 && pieces.length !== 3)) {
    throw new SpectrlDecodeError(`Not a ${MAGIC} token`);
  }
  const raw = b64urlDecode(pieces[1]!);
  const doc = cborDecode(raw);
  if (!(doc instanceof Map)) throw new SpectrlDecodeError("spectrl payload is not a CBOR map");

  const parts: TokenPart[] = [];
  let blobTotal = 0;
  const descs = (doc.get(6) as Array<Map<number, unknown>> | undefined) ?? [];
  for (const d of descs) {
    const blob = d.get(DESC_DATA) as Uint8Array | undefined;
    const bytes = blob?.length ?? 0;
    blobTotal += bytes;
    parts.push({
      label: arrayLabel(d.get(DESC_ARRAY) as number, d.get(DESC_NAME) as string | undefined),
      bytes,
      comp: d.get(DESC_COMP) as number,
    });
  }
  parts.unshift({ label: "header", bytes: raw.length - blobTotal });
  return parts;
}
