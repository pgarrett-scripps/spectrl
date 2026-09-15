/** Optional application budgets, separate from the wire format's hard limits. */
import { MAGIC, MAX_ARRAY_LENGTH, MAX_TOKEN_BYTES } from "./format.js"

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

export const DEFAULT_DECODE_LIMITS: Readonly<Required<DecodeLimits>> = Object.freeze({
  maxTokenBytes: Math.ceil(MAX_TOKEN_BYTES * 4 / 3) + MAGIC.length + 10,
  maxPeaks: MAX_ARRAY_LENGTH,
  maxArrays: 64,
  maxDecodedBytes: 64 * 1024 * 1024,
})

export function resolveDecodeLimits(limits?: DecodeLimits): Required<DecodeLimits> | undefined {
  if (limits === undefined) return undefined
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
