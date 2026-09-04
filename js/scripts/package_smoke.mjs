/** Copy this file beside an installed package to exercise the published exports. */
import assert from "node:assert/strict"
import { parsePeakList, formatPeakList, encodingReport, fitToBudget, decodeToken } from "@spectrl-ms/spectrl"
import { installZstd } from "@spectrl-ms/spectrl/zstd"

const source = parsePeakList("mz,intensity\n100.123456,10\n200.123456,20")
const report = encodingReport(source, { lossless: true })
assert.ok(report.allArraysExact)
assert.equal(parsePeakList(formatPeakList(decodeToken(report.token))).defaultArrayLength, 2)
assert.equal(fitToBudget(source, 1000).droppedPeaks, 0)
installZstd()
assert.equal(encodingReport(source, { arrayEncodings: { mz: "zstd" } }).arrays[0].comp, 1003780)
console.log("Installed npm workflows passed")
