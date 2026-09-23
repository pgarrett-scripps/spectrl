import test from "node:test"
import assert from "node:assert/strict"
import { expm1, log1p } from "../src/deterministic.ts"

/** The platform routines are what these replace, so agreeing with them to
 * within an ulp is the accuracy check; the bit-for-bit check against Python
 * lives in the cross-language parity run. */
function ulpDifference(a: number, b: number): number {
  if (a === b) return 0
  const view = new DataView(new ArrayBuffer(16))
  view.setFloat64(0, a, false)
  view.setFloat64(8, b, false)
  const left = view.getBigInt64(0, false), right = view.getBigInt64(8, false)
  const diff = left > right ? left - right : right - left
  return Number(diff)
}

test("expm1 stays within an ulp of the platform over the decode range", () => {
  let worst = 0
  for (let q = 0; q < 40000; q++) {
    const x = q / 3600
    worst = Math.max(worst, ulpDifference(expm1(x), Math.expm1(x)))
  }
  for (let i = 0; i < 40000; i++) {
    const x = -40 + (80 * i) / 40000
    worst = Math.max(worst, ulpDifference(expm1(x), Math.expm1(x)))
  }
  assert.ok(worst <= 1, `expm1 drifted ${worst} ulp from the platform`)
})

test("log1p stays within an ulp of the platform", () => {
  let worst = 0
  for (let i = 0; i < 40000; i++) {
    const x = (4000 * i) / 40000
    worst = Math.max(worst, ulpDifference(log1p(x), Math.log1p(x)))
  }
  for (let i = 1; i < 40000; i++) {
    const x = -0.999 + (10.999 * i) / 40000
    worst = Math.max(worst, ulpDifference(log1p(x), Math.log1p(x)))
  }
  assert.ok(worst <= 1, `log1p drifted ${worst} ulp from the platform`)
})

test("expm1 edges", () => {
  assert.ok(Object.is(expm1(0), 0))
  assert.ok(Object.is(expm1(-0), -0))
  assert.equal(expm1(Infinity), Infinity)
  assert.equal(expm1(-Infinity), -1)
  assert.equal(expm1(710), Infinity) // exp overflows above 709.78
  assert.equal(expm1(-40), -1) // saturates below -56 ln2
  assert.ok(Number.isNaN(expm1(NaN)))
})

test("log1p edges", () => {
  assert.ok(Object.is(log1p(0), 0))
  assert.ok(Object.is(log1p(-0), -0))
  assert.equal(log1p(-1), -Infinity)
  assert.equal(log1p(Infinity), Infinity)
  assert.ok(Number.isNaN(log1p(-1.5)))
  assert.ok(Number.isNaN(log1p(-Infinity)))
  assert.ok(Number.isNaN(log1p(NaN)))
})

test("the reduction boundaries stay monotone", () => {
  // A branch boundary is where a transcription slip would show.
  for (const centre of [0.3465735912322998, 1.0397214889526367, 38.816253662109375]) {
    let previous = -Infinity
    for (let i = 0; i <= 2000; i++) {
      const x = centre * (1 - 1e-12) + (centre * 2e-12 * i) / 2000
      const y = expm1(x)
      assert.ok(y >= previous, `expm1 went backwards at ${x}`)
      previous = y
    }
  }
  for (const centre of [0.4142136573791504, -0.2928931713104248]) {
    let previous = -Infinity
    for (let i = 0; i <= 2000; i++) {
      const x = centre - 1e-12 + (2e-12 * i) / 2000
      const y = log1p(x)
      assert.ok(y >= previous, `log1p went backwards at ${x}`)
      previous = y
    }
  }
})
