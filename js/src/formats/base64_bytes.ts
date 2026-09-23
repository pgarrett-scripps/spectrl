/** Base64 for binary array payloads, without a platform API.
 *
 * mzML binary is standard base64 with padding, which is not what the token's
 * base64url codec produces, so it needs its own pair. Written by hand rather
 * than through btoa/atob or Buffer: those split Node from the browser, and the
 * converter has to behave identically in both. */

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

const REVERSE = (() => {
  const table = new Int16Array(256).fill(-1)
  for (let i = 0; i < ALPHABET.length; i++) table[ALPHABET.charCodeAt(i)] = i
  return table
})()

export function bytesToBase64(bytes: Uint8Array): string {
  let out = ""
  let i = 0
  for (; i + 2 < bytes.length; i += 3) {
    const word = (bytes[i]! << 16) | (bytes[i + 1]! << 8) | bytes[i + 2]!
    out += ALPHABET[(word >> 18) & 63]! + ALPHABET[(word >> 12) & 63]! +
      ALPHABET[(word >> 6) & 63]! + ALPHABET[word & 63]!
  }
  const left = bytes.length - i
  if (left === 1) {
    const word = bytes[i]! << 16
    out += ALPHABET[(word >> 18) & 63]! + ALPHABET[(word >> 12) & 63]! + "=="
  } else if (left === 2) {
    const word = (bytes[i]! << 16) | (bytes[i + 1]! << 8)
    out += ALPHABET[(word >> 18) & 63]! + ALPHABET[(word >> 12) & 63]! + ALPHABET[(word >> 6) & 63]! + "="
  }
  return out
}

export function base64ToBytes(text: string): Uint8Array {
  const clean = text.replace(/[\s=]+/g, "")
  const out = new Uint8Array(Math.floor((clean.length * 3) / 4))
  let word = 0, bits = 0, at = 0
  for (let i = 0; i < clean.length; i++) {
    const value = REVERSE[clean.charCodeAt(i)]!
    if (value < 0) throw Error(`invalid base64 character ${JSON.stringify(clean[i])} in binary data`)
    word = (word << 6) | value
    bits += 6
    if (bits >= 8) {
      bits -= 8
      out[at++] = (word >> bits) & 0xff
    }
  }
  return out.subarray(0, at)
}
