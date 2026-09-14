/** Explicit read-only compatibility for the published spectrl.v1 format. */
import { decodeCbor, readTokenDocument } from "./cbor_format.js"
import type { DecodedSpectrum } from "./model.js"

export interface LegacySpectrum {
  spectrum: DecodedSpectrum
  interpretation: string | null
}

/** Keep the legacy interpretation separate from the v2 spectrum model. */
export function decodeV1Token(token: string): LegacySpectrum {
  const { doc } = readTokenDocument(token, true)
  return {
    spectrum: decodeCbor(token, true),
    interpretation: (doc.get(7) as string | undefined) ?? null,
  }
}
