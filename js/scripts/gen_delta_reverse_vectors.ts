/** Generate JS zlib streams for Python verification of the proposed codec. */
import { readFileSync, writeFileSync } from "node:fs"
import { encodeDeltaShuffleRaw } from "../src/delta.ts"

const source = new URL("../../test-vectors/delta-proposal.json", import.meta.url)
const data = JSON.parse(readFileSync(source, "utf8"))
for (const vector of data.vectors) {
  const raw = Buffer.from(vector.raw_hex, "hex")
  vector.shuffled_hex = Buffer.from(encodeDeltaShuffleRaw(raw, vector.item_size)).toString("hex")
}
writeFileSync(new URL("../../test-vectors/delta-proposal-reverse.json", import.meta.url), JSON.stringify(data, null, 2) + "\n")
