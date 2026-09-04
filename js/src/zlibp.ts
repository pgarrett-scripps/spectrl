/** Single-stream zlib with bounded inflation and explicit framing checks. */
import pako from "pako"

export function zlibCompress(data: Uint8Array): Uint8Array {
  return pako.deflate(data)
}

export function zlibDecompress(data: Uint8Array, maxBytes?: number): Uint8Array {
  if (data.length < 6) throw new Error("truncated zlib stream")
  const cmf = data[0]!
  const flags = data[1]!
  if ((cmf & 15) !== 8 || cmf >>> 4 > 7 || (cmf * 256 + flags) % 31 !== 0 || (flags & 32) !== 0) {
    throw new Error("invalid or unsupported zlib header")
  }
  const chunks: Uint8Array[] = []
  let total = 0
  let adlerA = 1
  let adlerB = 0
  let completed = false
  // Raw inflation prevents pako from automatically accepting concatenated streams.
  // avail_in identifies trailing compressed bytes after the first stream.
  const inf = new pako.Inflate({ raw: true }) as pako.Inflate & { strm: { avail_in: number } }
  inf.onData = chunk => {
    const c = chunk as Uint8Array
    total += c.length
    if (maxBytes !== undefined && total > maxBytes) throw new Error(`zlib output exceeds the ${maxBytes}-byte bound`)
    for (const value of c) {
      adlerA = (adlerA + value) % 65521
      adlerB = (adlerB + adlerA) % 65521
    }
    chunks.push(c)
  }
  inf.onEnd = status => {
    if (status !== 0) throw new Error("invalid zlib deflate stream")
    completed = true
  }
  inf.push(data.subarray(2, -4), true)
  if (!completed) throw new Error("truncated zlib stream")
  if (inf.strm.avail_in !== 0) throw new Error("trailing data after zlib stream")
  const stored = new DataView(data.buffer, data.byteOffset + data.length - 4, 4).getUint32(0)
  if ((adlerB * 65536 + adlerA) >>> 0 !== stored) throw new Error("zlib checksum mismatch")
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.length
  }
  return out
}
