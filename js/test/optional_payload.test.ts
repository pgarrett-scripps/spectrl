import assert from "node:assert/strict"
import test from "node:test"
import { encodeSpectrum } from "../src/index.ts"

test("optional payload backends fail explicitly and auto uses available methods", () => {
  const source = { defaultArrayLength: 0 }
  assert.throws(() => encodeSpectrum(source, { compression: "brotli" }), /Brotli support is unavailable/)
  const available = (["raw", "zlib"] as const).map(compression => encodeSpectrum(source, { compression }).length)
  assert.equal(encodeSpectrum(source, { compression: "auto" }).length, Math.min(...available))
})

test("removed payload modes are rejected", () => {
  for (const compression of ["zstd", "s"]) {
    assert.throws(() => encodeSpectrum({ defaultArrayLength: 0 }, { compression: compression as any }), /payload compression must be/)
  }
})
