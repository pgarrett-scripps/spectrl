/** Deterministic mutations reach framing, CBOR, and decompressed-array parsing. */
import { decodeToken, encodeSpectrum, SpectrlDecodeError } from "../src/index.ts"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"
import { cborDecode, cborEncode } from "../src/cbor.ts"
import { tokenChecksum } from "../src/checksum.ts"
import { DESC_DATA } from "../src/header.ts"
import { zlibCompress, zlibDecompress } from "../src/zlibp.ts"

let state = 0x5ec7
function random(): number {
  state = (Math.imul(state, 1664525) + 1013904223) >>> 0
  return state / 0x100000000
}
function mutate(data: Uint8Array): Uint8Array {
  const bytes = Array.from(data)
  let edits = 1 + Math.floor(random() * 4)
  while (edits-- && bytes.length) {
    const i = Math.floor(random() * bytes.length)
    if (random() < 0.15) bytes.splice(i, 1)
    else bytes[i] = bytes[i]! ^ (1 << Math.floor(random() * 8))
  }
  return Uint8Array.from(bytes)
}
const seed = encodeSpectrum({ defaultArrayLength: 3, mz: [100, 200, 300], intensity: [10, 20, 30] }, { quiet: true })
const raw = b64urlDecode(seed.split(".")[2]!)
const counts = { framing: 0, cbor: 0, array: 0 }
for (const trial of Array.from({ length: 2000 }, (_, i) => i)) {
  let token: string
  if (trial % 3 === 0) {
    token = new TextDecoder().decode(mutate(new TextEncoder().encode(seed)))
    counts.framing++
  } else {
    let payload: Uint8Array
    if (trial % 3 === 1) {
      payload = mutate(raw)
      counts.cbor++
    } else {
      const doc = cborDecode(raw) as Map<number, unknown>
      const descriptors = doc.get(6) as Map<number, unknown>[]
      const descriptor = descriptors[Math.floor(random() * 2)]!
      descriptor.set(DESC_DATA, zlibCompress(mutate(zlibDecompress(descriptor.get(DESC_DATA) as Uint8Array))))
      payload = cborEncode(doc)
      counts.array++
    }
    const body = "spectrl.v1." + b64urlEncode(payload)
    token = body + "." + tokenChecksum(body)
  }
  try { decodeToken(token) }
  catch (error) { if (!(error instanceof SpectrlDecodeError)) throw error }
}
console.log("TypeScript decoder mutations passed:", counts)
