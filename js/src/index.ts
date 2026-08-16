/**
 * spectrl: Inline Spectrum URL Encoder (JavaScript/TypeScript).
 *
 * Encodes a single mass spectrum into a compact, URL-safe `spectrl2` token and
 * back. Byte-compatible with the Python reference implementation; validated
 * against the shared conformance vectors in `test-vectors/`.
 */

import { decodeCbor, encodeCbor } from "./cbor_format.js";
import type { DecodedSpectrum, InlineSpectrum } from "./model.js";

export * from "./model.js";
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
}

/** Encode an {@link InlineSpectrum} into a `spectrl2` token (a single CBOR document). */
export function encodeSpectrum(spec: InlineSpectrum, opts: EncodeOptions = {}): string {
  const { lossless = false, maxLen, quiet = false, dropUserParams = false } = opts;

  const token = encodeCbor(spec, lossless, dropUserParams);

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

/** Decode a `spectrl2` token into a {@link DecodedSpectrum}, verifying the trailing integrity hash if present. */
export function decodeToken(token: string): DecodedSpectrum {
  return decodeCbor(token);
}
