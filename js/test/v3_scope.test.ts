import { readTokenPayload } from "../src/cbor_format.ts"
import test from "node:test"
import assert from "node:assert/strict"
import { decodeToken, encodeSpectrum } from "../src/index.ts"
import { cborDecode, cborEncode } from "../src/cbor.ts"
import { b64urlDecode, b64urlEncode } from "../src/base64url.ts"
import { tokenChecksum } from "../src/checksum.ts"

function frame(document: Map<unknown, unknown>, version = 3): string {
  const body = `spectrl.v${version}.r.${b64urlEncode(cborEncode(document))}`
  return `${body}.${tokenChecksum(body)}`
}

test("spectrum user parameters use key 7 and scan parameters retain key 2", () => {
  const userParams = [{ name: "elapsed", value: 3.5, unitAccession: "UO:0000010" }]
  for (const lossless of [false, true]) {
    const token = encodeSpectrum({ defaultArrayLength: 0, userParams, scans: [{ params: [], windows: [], userParams }] }, { lossless })
    const document = cborDecode(readTokenPayload(token)) as Map<number, unknown>
    assert.ok([...document.keys()].every(key => key >= 0 && key <= 7))
    const parameters = document.get(7) as Map<string, unknown>[]
    assert.equal(parameters[0]!.get("n"), "elapsed")
    const scanList = document.get(3) as Map<string, Map<number, unknown>[]>
    assert.deepEqual(scanList.get("s")![0]!.get(2), parameters)
    const decoded = decodeToken(token)
    assert.deepEqual(decoded.userParams, userParams)
    assert.deepEqual(decoded.scans[0]!.userParams, userParams)
    assert.equal(decoded.formatVersion, 3)
  }
})

test("empty user parameters are omitted", () => {
  const token = encodeSpectrum({ defaultArrayLength: 0 })
  const document = cborDecode(readTokenPayload(token)) as Map<number, unknown>
  assert.equal(document.has(7), false)
  assert.deepEqual(decodeToken(token).userParams, [])
})

test("unsupported header keys are rejected even alongside valid parameters", () => {
  for (const key of [13, 14, 99, -1, "7"]) {
    for (const includeParameters of [false, true]) {
      const parameters = [new Map([["n", "note"], ["v", "value"]])]
      const document = new Map<unknown, unknown>([[0, 0], [key, parameters]])
      if (includeParameters) document.set(7, parameters)
      assert.throws(() => decodeToken(frame(document)), /unsupported spectrl header key/)
    }
  }
})

test("user parameters require an array", () => {
  for (const value of [null, "PEPTIDE", 0, new Map()]) {
    assert.throws(() => decodeToken(frame(new Map<unknown, unknown>([[0, 0], [7, value]]))), /header key 7 must be array/)
  }
})

test("only the current format is accepted", () => {
  for (const version of [0, 1, 2, 99]) {
    assert.throws(() => decodeToken(frame(new Map([[0, 0]]), version)), /Not a spectrl.v3 token/)
  }
})

test("identification input cannot be silently discarded", () => {
  const source = { defaultArrayLength: 0, interp: "PEPTIDE" }
  assert.throws(() => encodeSpectrum(source), /identification/)
})

test("removed wire type annotation is rejected", () => {
  const user = new Map<string, unknown>([["n", "example"], ["v", "2.5"], ["t", "xsd:float"]])
  assert.throws(() => decodeToken(frame(new Map<number, unknown>([[0, 0], [7, [user]]]))), /invalid metadata map fields/)
})

test("cv_versions round-trips on key 12 and stays absent when unset", () => {
  const cvVersions = { MS: "4.1.142", UO: "releases/2020-03-10" }
  const token = encodeSpectrum({ defaultArrayLength: 0, cvVersions })
  const document = cborDecode(readTokenPayload(token)) as Map<number, unknown>
  assert.deepEqual(document.get(12), new Map([["MS", "4.1.142"], ["UO", "releases/2020-03-10"]]))
  assert.deepEqual(decodeToken(token).cvVersions, cvVersions)
  const bare = encodeSpectrum({ defaultArrayLength: 0 })
  assert.ok(!(cborDecode(readTokenPayload(bare)) as Map<number, unknown>).has(12))
  assert.deepEqual(decodeToken(bare).cvVersions, {})
})

test("malformed cv_versions entries are rejected", () => {
  // Keys are accession prefixes, so neither a whole accession nor mzML's <cv> @id spelling.
  for (const cvVersions of [{ "MS:": "4.1.142" }, { "PSI-MS": "4.1.142" }, { "": "4.1.142" }, { "1MS": "4.1.142" }, { MS: "" }]) {
    assert.throws(() => encodeSpectrum({ defaultArrayLength: 0, cvVersions: cvVersions as Record<string, string> }))
  }
  assert.throws(() => decodeToken(frame(new Map<unknown, unknown>([[0, 0], [12, "4.1.142"]]))), /cv_versions must be a map/)
})

test("an unrecognized ontology release is provenance, not a decode gate", () => {
  const token = encodeSpectrum({ defaultArrayLength: 0, cvVersions: { MS: "99.99.99-unreleased" } })
  assert.deepEqual(decodeToken(token).cvVersions, { MS: "99.99.99-unreleased" })
})
