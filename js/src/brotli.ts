/** Optional browser Brotli backend, initialized before synchronous token use. */
import brotliPromise from "brotli-wasm"
import { registerBrotliBackend } from "./payload.js"

export async function installBrotli(): Promise<void> {
  const wasm = await brotliPromise
  registerBrotliBackend({
    compress: data => wasm.compress(data, { quality: 5 }),
    decompress: (data, cap) => {
      const stream = new wasm.DecompressStream()
      const chunks: Uint8Array[] = []
      let offset = 0
      let length = 0
      try {
        while (true) {
          const result = stream.decompress(data.subarray(offset), Math.min(65536, cap - length + 1))
          let code: number
          let consumed: number
          let chunk: Uint8Array
          try {
            code = result.code
            consumed = result.input_offset
            chunk = result.buf
          } finally { result.free() }
          offset += consumed
          length += chunk.length
          if (length > cap) throw Error("brotli output exceeds the size limit")
          chunks.push(chunk)
          if (code === wasm.BrotliStreamResultCode.ResultSuccess) {
            if (offset !== data.length) throw Error("trailing data after brotli payload")
            break
          }
          if (code === wasm.BrotliStreamResultCode.NeedsMoreInput || !consumed && !chunk.length) throw Error("truncated brotli payload")
        }
      } finally { stream.free() }
      const raw = new Uint8Array(length)
      let position = 0
      for (const chunk of chunks) {
        raw.set(chunk, position)
        position += chunk.length
      }
      return raw
    },
  })
}
