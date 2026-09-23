/** Application budgets applied by default, separate from the wire format's hard limits. */
import { MAGIC, MAX_ARRAY_LENGTH, MAX_CBOR_ITEMS, MAX_TOKEN_BYTES } from "./format.js"

/** Longest token the wire format can express: base64url of a 16 MiB payload
 * plus framing. A ceiling, not a budget. */
export const MAX_TOKEN_CHARS = Math.ceil(MAX_TOKEN_BYTES * 4 / 3) + MAGIC.length + 10

export interface DecodeLimits {
  /** Complete ASCII token bytes, including framing and checksum. */
  maxTokenBytes?: number
  /** Declared number of peaks, including spectra without arrays. */
  maxPeaks?: number
  /** Total core and auxiliary array count. */
  maxArrays?: number
  /** Sum of output array byte lengths, excluding metadata and temporary buffers. */
  maxDecodedBytes?: number
}

/**
 * The budgets applied when a caller supplies none.
 *
 * A token usually arrives from a URL or a message, and the wire ceilings alone
 * permit a 21 kB token to expand into 128 MB of arrays. These values sit
 * roughly an order of magnitude above the largest spectrum in the reference
 * corpus (217,009 peaks, a 1.05 MB token), so ordinary data is unaffected.
 * Pass {@link UNLIMITED_DECODE_LIMITS} for a trusted producer.
 */
export const DEFAULT_DECODE_LIMITS: Readonly<Required<DecodeLimits>> = Object.freeze({
  maxTokenBytes: 4 * 1024 * 1024,
  maxPeaks: 1_000_000,
  maxArrays: 64,
  maxDecodedBytes: 64 * 1024 * 1024,
})

/** Budgets raised to the format's hard ceilings, for a trusted producer. */
export const UNLIMITED_DECODE_LIMITS: Readonly<Required<DecodeLimits>> = Object.freeze({
  maxTokenBytes: MAX_TOKEN_CHARS,
  maxPeaks: MAX_ARRAY_LENGTH,
  maxArrays: MAX_CBOR_ITEMS,
  maxDecodedBytes: MAX_ARRAY_LENGTH * 8 * MAX_CBOR_ITEMS,
})

export function resolveDecodeLimits(limits?: DecodeLimits): Required<DecodeLimits> {
  if (limits === undefined) return DEFAULT_DECODE_LIMITS
  if (limits === null || typeof limits !== "object" || Array.isArray(limits)) {
    throw new TypeError("limits must be an object")
  }
  const resolved = { ...DEFAULT_DECODE_LIMITS }
  for (const key of Object.keys(resolved) as (keyof DecodeLimits)[]) {
    const value = limits[key] === undefined ? resolved[key] : limits[key]
    if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
      throw new RangeError(`${key} must be a nonnegative safe integer`)
    }
    resolved[key] = value
  }
  return resolved
}
