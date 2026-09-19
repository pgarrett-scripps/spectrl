/** Whole-document compression presets, independent of numeric encodings. */
import { zlibCompress, zlibDecompress } from "./zlibp.js"

export type PayloadCompression = "raw" | "zlib" | "brotli" | "auto" | "r" | "z" | "b"
export interface BrotliBackend {
  compress(data: Uint8Array): Uint8Array
  decompress(data: Uint8Array, cap: number): Uint8Array
}
let brotli: BrotliBackend | undefined
export function registerBrotliBackend(backend: BrotliBackend): void { brotli = backend }
function requireBrotli(): BrotliBackend {
  if (!brotli) throw Error("Brotli support is unavailable. Call installBrotli() from '@spectrl-ms/spectrl/brotli'.")
  return brotli
}
const names: Record<string, string> = { raw: "r", zlib: "z", brotli: "b", r: "r", z: "z", b: "b" }
export function compressPayload(raw: Uint8Array, compression: PayloadCompression, cap: number): [string, Uint8Array] {
  if (raw.length > cap) throw Error("CBOR payload exceeds the size limit")
  if (compression === "auto") {
    const modes: PayloadCompression[] = ["z", "r"]
    if (brotli) modes.push("b")
    let best: [string, Uint8Array] | undefined
    for (const mode of modes) {
      const candidate: [string, Uint8Array] = [mode, pack(raw, mode)]
      if (candidate[1].length > cap) continue
      if (!best || candidate[1].length < best[1].length) best = candidate
    }
    return best!
  }
  const mode = Object.prototype.hasOwnProperty.call(names, compression) ? names[compression] : undefined
  if (!mode) throw Error("payload compression must be raw, zlib, brotli, or auto")
  const packed = pack(raw, mode)
  if (packed.length > cap) throw Error("compressed payload exceeds the size limit")
  return [mode, packed]
}
function pack(raw: Uint8Array, mode: string): Uint8Array {
  return mode === "r" ? raw : mode === "z" ? zlibCompress(raw, 6)
    : requireBrotli().compress(raw)
}
export function decompressPayload(packed: Uint8Array, mode: string, cap: number): Uint8Array {
  const raw = mode === "r" ? packed : mode === "z" ? zlibDecompress(packed, cap)
    : requireBrotli().decompress(packed, cap)
  if (raw.length > cap) throw Error("expanded CBOR payload exceeds the size limit")
  return raw
}
