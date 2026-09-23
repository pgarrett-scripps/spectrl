import test from "node:test"
import assert from "node:assert/strict"
import { decodeToken, encodeSpectrum, readTokenDocument, topN } from "../src/index.ts"
import { framePayload } from "../src/cbor_format.ts"
import { cborEncode } from "../src/cbor.ts"

test("names survive sorting, selection and re-encoding", () => {
  const arrayNames = { mz: "Measured m/z", intensity: "Signal", "MS:1000517": "Signal", score: "score" }
  const spec = { defaultArrayLength: 2, mz: [200, 100], intensity: [10, 20],
    extraArrays: { "MS:1000517": [2, 3], score: [0.8, 0.9] }, arrayNames }
  const decoded = decodeToken(encodeSpectrum(spec, { lossless: true }))
  assert.deepEqual(decoded.arrayNames, arrayNames)
  assert.deepEqual(Array.from(decoded.mz!), [100, 200])
  assert.deepEqual(Array.from(decoded.extraArrays["MS:1000517"]!), [3, 2])
  assert.deepEqual(decodeToken(encodeSpectrum(decoded, { lossless: true })).arrayNames, arrayNames)
  const selected = decodeToken(encodeSpectrum(topN(decoded, 1), { lossless: true }))
  assert.deepEqual(selected.arrayNames, arrayNames)
  assert.deepEqual(Array.from(selected.mz!), [100])
})

for (const name of [null, "", 42, [], {}]) test(`reject invalid array name ${JSON.stringify(name)}`, () => {
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 1, mz: [100], arrayNames: { mz: name as any } }), /array name/)
  const { doc } = readTokenDocument(encodeSpectrum({ defaultArrayLength: 1, mz: [100] }, { lossless: true }))
  const arrays = doc.get(6) as Map<number, unknown>[]
  arrays[0]!.set(4, name)
  assert.throws(() => decodeToken(framePayload(cborEncode(doc))), /array name/)
})

for (const tail of [1000514, 1000517]) test(`names do not allow duplicate standard array ${tail}`, () => {
  const { doc } = readTokenDocument(encodeSpectrum({ defaultArrayLength: 1, mz: [100] }, { lossless: true }))
  const arrays = doc.get(6) as Map<number, unknown>[]
  arrays[0]!.set(1, tail)
  arrays[0]!.set(4, "First")
  const duplicate = new Map(arrays[0]!)
  duplicate.set(4, "Second")
  arrays.push(duplicate)
  assert.throws(() => decodeToken(framePayload(cborEncode(doc))), /duplicate array/)
})

test("names cannot relabel custom identities or name absent arrays", () => {
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 1, extraArrays: { score: [1] },
    arrayNames: { score: "other" } }), /must match/)
  assert.throws(() => encodeSpectrum({ defaultArrayLength: 1, mz: [100],
    arrayNames: { intensity: "Signal" } }), /absent/)
})

test("standard names do not use custom name restrictions", () => {
  const token = encodeSpectrum({ defaultArrayLength: 1, mz: [100], arrayNames: { mz: "mz" } })
  assert.deepEqual(decodeToken(token).arrayNames, { mz: "mz" })
})

for (const name of ["MS:1000517", "MS:1000514", "MS:1000786", "MS:1", "UO:0000001", "NCIT:C1"]) {
  test(`reject accession-shaped custom name ${name} regardless of descriptor order`, () => {
    for (const order of ["alone", "first", "last"]) {
      const { doc } = readTokenDocument(encodeSpectrum({ defaultArrayLength: 1, mz: [11] }, { lossless: true }))
      const standard = new Map((doc.get(6) as Map<number, unknown>[])[0]!)
      standard.set(1, 1000517)
      const custom = new Map(standard)
      custom.set(1, 1000786)
      custom.set(4, name)
      doc.set(6, order === "alone" ? [custom] : order === "first" ? [custom, standard] : [standard, custom])
      const token = framePayload(cborEncode(doc))
      for (const reader of [readTokenDocument, decodeToken]) assert.throws(() => reader(token), /non-standard array name/)
    }
  })
}

for (const name of ["__proto__", "constructor", "toString", "0", "01", "score: mean", "é", "🧪", "MS:1000517\n", "MS:１０００５１７", "MS:١٠٠٠٥١٧"]) {
  test(`custom name ${name} survives decoding and re-encoding`, () => {
    const spec = { defaultArrayLength: 2, mz: [2, 1], extraArrays: { [name]: Float32Array.from([-0, 7]) } }
    const decoded = decodeToken(encodeSpectrum(spec, { lossless: true }))
    const again = decodeToken(encodeSpectrum(decoded, { lossless: true }))
    assert.deepEqual(again.extraArrays[name], decoded.extraArrays[name])
    assert.deepEqual(again.arrayNames, decoded.arrayNames)
  })
}
