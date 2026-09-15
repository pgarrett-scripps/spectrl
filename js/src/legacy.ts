/** Explicit read-only compatibility for the published spectrl.v1 format. */
import { decodeCbor, readTokenDocument } from "./cbor_format.js"
import type { DecodedSpectrum } from "./model.js"
import type { DecodeLimits } from "./limits.js"

export interface LegacySpectrum {
  spectrum: DecodedSpectrum
  interpretation: string | null
}

/** Keep the legacy interpretation separate from the v2 spectrum model. */
export function decodeV1Token(token: string, limits?: DecodeLimits): LegacySpectrum {
  const { doc } = readTokenDocument(token, true, limits)
  return {
    spectrum: decodeCbor(token, true, limits),
    interpretation: (doc.get(7) as string | undefined) ?? null,
  }
}
