/** Optional Node Brotli backend. */
import { brotliCompressSync, brotliDecompressSync, constants } from "node:zlib"
import { registerBrotliBackend } from "./payload.js"

export async function installBrotli(): Promise<void> {
  registerBrotliBackend({
    compress: data => brotliCompressSync(data, { params: { [constants.BROTLI_PARAM_QUALITY]: 5 } }),
    decompress: (data, cap) => {
      const result = brotliDecompressSync(data, { maxOutputLength: cap, info: true }) as unknown as {
        buffer: Buffer, engine: { bytesWritten: number }
      }
      if (result.engine.bytesWritten !== data.length) throw Error("trailing data after brotli payload")
      return result.buffer
    },
  })
}
