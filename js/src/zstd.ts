/** Optional browser and Node zstd backend for the official PSI-MS zstd codecs. */

import { compressSync, decompressSync } from "@cloudpss/zstd/wasm";

import { registerZstdBackend } from "./codecs.js";

let installed = false;

/** Explicitly install the optional zstd backend. Safe to call more than once. */
export function installZstd(): void {
  if (installed) return;
  registerZstdBackend({
    compress: (data, level) => compressSync(data, level),
    decompress: (data) => decompressSync(data),
  });
  installed = true;
}
