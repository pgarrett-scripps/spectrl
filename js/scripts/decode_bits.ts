/** Emit the exact float64 bits each decoded array reconstructs to, so the two
 * implementations can be compared bit for bit rather than within a tolerance. */
import { decodeToken } from "../src/index.js"

const chunks: Buffer[] = []
for await (const chunk of process.stdin) chunks.push(chunk as Buffer)
const tokens: string[] = JSON.parse(Buffer.concat(chunks).toString("utf8"))
process.stdout.write(JSON.stringify(tokens.map(token => {
  const d = decodeToken(token)
  const hex = (a: ArrayLike<number> | null) => {
    if (!a) return null
    const f = new Float64Array(a.length)
    for (let i = 0; i < a.length; i++) f[i] = a[i]!
    return Buffer.from(f.buffer, f.byteOffset, f.byteLength).toString("hex")
  }
  return { mz: hex(d.mz), intensity: hex(d.intensity) }
})))
