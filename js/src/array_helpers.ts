import { accessionTail } from "./cv.js";
import { ION_MOBILITY_ARRAY_TAILS } from "./format.js";
import type { DecodedSpectrum } from "./model.js";

/** Return the accession-keyed ion-mobility arrays without creating a second source of truth. */
export function mobilityArrays(decoded: DecodedSpectrum): DecodedSpectrum["extraArrays"] {
  return Object.fromEntries(
    Object.entries(decoded.extraArrays).filter(
      ([accession]) => /^MS:\d{7}$/.test(accession) && ION_MOBILITY_ARRAY_TAILS.has(accessionTail(accession)),
    ),
  );
}
