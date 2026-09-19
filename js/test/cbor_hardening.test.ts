import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { test } from "node:test"
import { decodeToken, tokenBreakdown, SpectrlDecodeError } from "../src/index.ts"
import { framePayload } from "../src/cbor_format.ts"

const cases = JSON.parse(readFileSync(new URL("../../test-vectors/cbor-hardening.json", import.meta.url), "utf8")) as { name: string, hex: string }[]
for (const fixture of cases) {
  test(`reject malformed CBOR in decoding and inspection: ${fixture.name}`, () => {
    const token = framePayload(Buffer.from(fixture.hex, "hex"))
    for (const read of [decodeToken, tokenBreakdown]) {
      assert.throws(() => read(token), SpectrlDecodeError)
    }
  })
}
