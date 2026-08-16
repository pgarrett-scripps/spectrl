/** zlib wrapper over pako; works in node and the browser. */

import pako from "pako";

export function zlibCompress(data: Uint8Array): Uint8Array {
  return pako.deflate(data);
}

/**
 * Inflate `data`, aborting as soon as the output would exceed `maxBytes`.
 * Tokens are decoded from untrusted URLs; the bound (derived from the token's
 * declared array length) stops decompression bombs before they materialize.
 */
export function zlibDecompress(data: Uint8Array, maxBytes?: number): Uint8Array {
  if (maxBytes === undefined) return pako.inflate(data);
  const chunks: Uint8Array[] = [];
  let total = 0;
  const inf = new pako.Inflate();
  inf.onData = (chunk: pako.Data) => {
    const c = chunk as Uint8Array;
    total += c.length;
    if (total > maxBytes) {
      throw new Error(
        `array blob decompresses beyond the ${maxBytes}-byte bound implied by the declared array length`,
      );
    }
    chunks.push(c);
  };
  inf.push(data, true);
  if (inf.err) throw new Error(`zlib: ${inf.msg || inf.err}`);
  const out = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    out.set(c, off);
    off += c.length;
  }
  return out;
}
