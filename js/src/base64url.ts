/** Base64url (RFC 4648 §5) encode/decode for Uint8Array, dependency-free, browser + node. */

import { SpectrlDecodeError } from "./errors.js";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

const LOOKUP = (() => {
  const t = new Int16Array(128).fill(-1);
  for (let i = 0; i < ALPHABET.length; i++) t[ALPHABET.charCodeAt(i)] = i;
  return t;
})();

/** Encode bytes to base64url without padding. */
export function b64urlEncode(data: Uint8Array): string {
  let out = "";
  let i = 0;
  for (; i + 3 <= data.length; i += 3) {
    const n = (data[i]! << 16) | (data[i + 1]! << 8) | data[i + 2]!;
    out += ALPHABET[(n >>> 18) & 63]! + ALPHABET[(n >>> 12) & 63]! + ALPHABET[(n >>> 6) & 63]! + ALPHABET[n & 63]!;
  }
  const rem = data.length - i;
  if (rem === 1) {
    const n = data[i]! << 16;
    out += ALPHABET[(n >>> 18) & 63]! + ALPHABET[(n >>> 12) & 63]!;
  } else if (rem === 2) {
    const n = (data[i]! << 16) | (data[i + 1]! << 8);
    out += ALPHABET[(n >>> 18) & 63]! + ALPHABET[(n >>> 12) & 63]! + ALPHABET[(n >>> 6) & 63]!;
  }
  return out;
}

/** Bits of the final character that fall outside the decoded bytes. A canonical
 * encoding leaves them zero, so exactly one spelling exists per payload. */
const TAIL_MASK: Record<number, number> = { 2: 0b001111, 3: 0b000011 };

/** Decode a canonical unpadded base64url string. Strict: rejects characters
 * outside the base64url alphabet, `=` padding, impossible lengths, and
 * non-zero unused trailing bits, matching the Python reference
 * implementation. Each payload therefore has exactly one valid spelling. */
export function b64urlDecode(s: string): Uint8Array {
  if (s.includes("=")) throw new SpectrlDecodeError("invalid base64url payload: must be unpadded");
  const len = s.length;
  if (len % 4 === 1) throw new SpectrlDecodeError("invalid base64url payload: impossible length");
  const outLen = Math.floor((len * 6) / 8);
  const out = new Uint8Array(outLen);
  let bits = 0;
  let acc = 0;
  let oi = 0;
  for (let i = 0; i < len; i++) {
    const v = LOOKUP[s.charCodeAt(i)] ?? -1;
    if (v < 0) throw new SpectrlDecodeError(`invalid base64url character: ${JSON.stringify(s[i])}`);
    acc = (acc << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[oi++] = (acc >>> bits) & 0xff;
    }
  }
  const mask = TAIL_MASK[len % 4];
  if (mask !== undefined && (LOOKUP[s.charCodeAt(len - 1)]! & mask) !== 0) {
    throw new SpectrlDecodeError("invalid base64url payload: non-zero trailing bits");
  }
  return out;
}
