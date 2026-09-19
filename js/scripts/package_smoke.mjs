/** Copy this file beside an installed package to exercise the published exports. */
import assert from "node:assert/strict"
import { parsePeakList, formatPeakList, encodingReport, fitToBudget, decodeToken, encodeSpectrum } from "@spectrl-ms/spectrl"

const source = parsePeakList("mz,intensity\n100.123456,10\n200.123456,20")
const report = encodingReport(source, { lossless: true })
assert.ok(report.token.startsWith("spectrl.v3."))
assert.ok(report.allArraysExact)
assert.equal(decodeToken(report.token, { maxDecodedBytes: 32 }).defaultArrayLength, 2)
assert.throws(() => decodeToken(report.token, { maxDecodedBytes: 31 }), /maxDecodedBytes/)
assert.equal(parsePeakList(formatPeakList(decodeToken(report.token))).defaultArrayLength, 2)
assert.equal(fitToBudget(source, 1000).droppedPeaks, 0)
assert.deepEqual(encodingReport(source, { arrayEncodings: { mz: "raw" } }).arrays[0].encoding, [0, 1])
const { installBrotli } = await import("@spectrl-ms/spectrl/brotli")
await installBrotli()
const compressed = encodeSpectrum(source, { compression: "brotli" })
assert.ok(compressed.startsWith("spectrl.v3.b."))
assert.equal(decodeToken(compressed).defaultArrayLength, 2)
console.log("Installed npm workflows passed")
