/** Run with: node consumer.mjs http://127.0.0.1:8000/spectra/example */
import { decodeToken, SpectrlDecodeError } from "@spectrl-ms/spectrl"


const limits = Object.freeze({
  maxTokenBytes: 256 * 1024,
  maxPeaks: 100_000,
  maxArrays: 16,
  maxDecodedBytes: 16 * 1024 * 1024,
})

async function consume(url) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) throw new Error(`Producer returned HTTP ${response.status}`)
    if (!response.body) throw new Error("Producer returned no response body")
    const chunks = []
    let bytes = 0
    for await (const chunk of response.body) {
      bytes += chunk.byteLength
      if (bytes > 512 * 1024) {
        controller.abort()
        throw new Error("Producer response exceeds the HTTP body budget")
      }
      chunks.push(chunk)
    }
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"))
    if (!payload || typeof payload.token !== "string") throw new Error("Missing spectrum token")
    const spectrum = decodeToken(payload.token, limits)
    console.log(JSON.stringify({
      id: spectrum.id,
      peaks: spectrum.defaultArrayLength,
      mz: Array.from(spectrum.mz ?? []),
      intensity: Array.from(spectrum.intensity ?? []),
    }))
  } finally {
    clearTimeout(timeout)
  }
}

try {
  await consume(process.argv[2] ?? "http://127.0.0.1:8000/spectra/example")
} catch (error) {
  console.error(error instanceof SpectrlDecodeError
    ? `Spectrum rejected: ${error.message}`
    : `Request failed: ${error instanceof Error ? error.message : String(error)}`)
  process.exitCode = 1
}
