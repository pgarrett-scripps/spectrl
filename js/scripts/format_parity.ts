/** Emit this implementation's mzML, MGF and MS2 for each token on stdin, so
 * the Python writers can be compared byte for byte against them.
 *
 * Input is a JSON array of tokens; output is a JSON array of results in the
 * same order. Batched because the corpus comparison runs hundreds of tokens
 * and a process per token dominates the time. */
import { decodeToken } from "../src/index.js"
import { writeMgf, writeMs2 } from "../src/formats/peaklist_formats.js"
import { writeMzml } from "../src/formats/mzml.js"

const chunks: Buffer[] = []
for await (const chunk of process.stdin) chunks.push(chunk as Buffer)
const tokens: string[] = JSON.parse(Buffer.concat(chunks).toString("utf8"))

const out = tokens.map(token => {
  const decoded = decodeToken(token)
  const mgf = writeMgf(decoded)
  const ms2 = writeMs2(decoded)
  const mzml = writeMzml(decoded, { indent: false })
  return {
    mgf: mgf.text, ms2: ms2.text, mzml: mzml.text,
    mgfOmitted: mgf.omitted, ms2Omitted: ms2.omitted,
    mzmlIssues: mzml.issues.map(i => i.code).sort(),
  }
})
process.stdout.write(JSON.stringify(out))
