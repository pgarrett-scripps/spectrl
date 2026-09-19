import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { decodeToken, encodeSpectrum, tokenBreakdown, SpectrlDecodeError } from "../src/index.ts"
import { readTokenPayload } from "../src/cbor_format.ts"
import { b64urlEncode } from "../src/base64url.ts"
import { tokenChecksum } from "../src/checksum.ts"
import { zlibCompress } from "../src/zlibp.ts"
import { installBrotli } from "../src/brotli-node.ts"
import { compressPayload, decompressPayload } from "../src/payload.ts"

await installBrotli()

const vectors = JSON.parse(readFileSync(new URL("../../test-vectors/outer-payload.json", import.meta.url), "utf8"))
for (const vector of vectors.valid) {
  test(`shared outer payload: ${vector.name}`, () => {
    assert.equal(Buffer.from(readTokenPayload(vector.token)).toString("hex"), vector.cbor_hex)
    assert.equal(decodeToken(vector.token).defaultArrayLength, 0)
    const parts = tokenBreakdown(vector.token)
    assert.equal(parts.length, 1)
    assert.equal(parts[0]!.bytes, vector.cbor_hex.length / 2)
  })
}
for (const vector of vectors.invalid) {
  test(`invalid outer payload: ${vector.name}`, () => {
    for (const reader of [decodeToken, tokenBreakdown]) {
      assert.throws(() => reader(vector.token), (e: unknown) =>
        e instanceof SpectrlDecodeError && new RegExp(vector.error).test(e.message))
    }
  })
}
test("default is zlib and auto selects the smallest complete token", () => {
  for (const id of [undefined, "context-".repeat(1000)]) {
    const token = encodeSpectrum({ defaultArrayLength: 0, id })
    assert.equal(token.split(".")[2], "z")
    const lengths = (["raw", "zlib", "brotli"] as const).map(compression =>
      encodeSpectrum({ defaultArrayLength: 0, id }, { compression }).length)
    assert.equal(encodeSpectrum({ defaultArrayLength: 0, id }, { compression: "auto" }).length, Math.min(...lengths))
    assert.equal(decodeToken(token).id, id ?? null)
  }
})

test("outer compressors enforce bounded output", () => {
  const raw = new Uint8Array(10000)
  for (const mode of ["z", "b"] as const) {
    const [, packed] = compressPayload(raw, mode, 20000)
    assert.equal(decompressPayload(packed, mode, raw.length).length, raw.length)
    assert.throws(() => decompressPayload(packed, mode, raw.length - 1))
  }
})
