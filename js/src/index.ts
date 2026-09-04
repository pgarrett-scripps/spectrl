/**
 * spectrl: Inline Spectrum URL Encoder (JavaScript/TypeScript).
 *
 * Encodes a single mass spectrum into a compact, URL-safe `spectrl.v1` token and
 * back. Byte-compatible with the Python reference implementation; validated
 * against the shared conformance vectors in `test-vectors/`.
 */

import { decodeCbor, encodeCbor } from "./cbor_format.js";
import { tokenBreakdown } from "./inspect.js";
import type { ArrayEncodingOption, DecodedSpectrum, InlineSpectrum } from "./model.js";

export * from "./model.js";
export * from "./array_accession.js";
export * from "./compression_accession.js";
export * from "./unit_accession.js";
export { mobilityArrays } from "./array_helpers.js";
export { SpectrlError, SpectrlDecodeError } from "./errors.js";
export { tokenBreakdown, type TokenPart } from "./inspect.js";
export { toFragment, toQuery, toDataUri, extractToken } from "./url.js";
export { MAGIC, FORMAT_VERSION } from "./token.js";

const SIZE_WARN = 8192;

export interface EncodeOptions {
  /** Use raw IEEE-754 + zlib (bit-exact) instead of the default lossy MS-Numpress. */
  lossless?: boolean;
  /** Throw if the encoded token exceeds this many characters. */
  maxLen?: number;
  /** Suppress the console warning emitted past the recommended size. */
  quiet?: boolean;
  /**
   * Omit free-text user params at both spectrum and scan level. Vendor trailers
   * are often a large share of a small MS2 token and usually restate CV params
   * the token already carries. The result is conforming; the omitted values are
   * not recoverable from it.
   */
  dropUserParams?: boolean;
  /** Per-array codec overrides keyed by core name, core PSI-MS accession alias, or exact extraArrays key. */
  arrayEncodings?: Record<string, ArrayEncodingOption>;
  /** Permit explicit lossy codecs for semantically unknown custom arrays. */
  allowUnsafeLossyCustom?: boolean;
}

/** Encode an {@link InlineSpectrum} into a `spectrl.v1` token (a single CBOR document). */
export function encodeSpectrum(spec: InlineSpectrum, opts: EncodeOptions = {}): string {
  const {
    lossless = false,
    maxLen,
    quiet = false,
    dropUserParams = false,
    arrayEncodings,
    allowUnsafeLossyCustom = false,
  } = opts;

  const token = encodeCbor(spec, lossless, dropUserParams, arrayEncodings, allowUnsafeLossyCustom);

  if (!quiet && token.length > SIZE_WARN) {
    console.warn(
      `spectrl token length ${token.length} exceeds recommended maximum of ${SIZE_WARN}. ` +
        `Consider trimming peaks (e.g. keep top-N).`,
    );
  }
  if (maxLen !== undefined && token.length > maxLen) {
    throw new RangeError(`Encoded spectrl token is ${token.length} chars, exceeding maxLen=${maxLen}.`);
  }
  return token;
}

/** Decode a `spectrl.v1` token into a {@link DecodedSpectrum}, verifying its trailing CRC-32 checksum. */
export function decodeToken(token: string): DecodedSpectrum {
  return decodeCbor(token);
}

/** Resolve automatic codecs, fixed points, types, and units for a spectrum. */
export function encodingPlan(
  spec: InlineSpectrum,
  opts: Pick<EncodeOptions, "lossless" | "arrayEncodings" | "allowUnsafeLossyCustom"> = {},
) {
  const token = encodeCbor(
    spec, opts.lossless ?? false, false, opts.arrayEncodings, opts.allowUnsafeLossyCustom ?? false,
  );
  return tokenBreakdown(token).filter((part) => part.accession !== undefined);
}

export { encodingReport, fitToBudget, topN, type BudgetOptions } from "./workflows.js"
export { parsePeakList, formatPeakList, type PeakDelimiter } from "./peaklist.js"
