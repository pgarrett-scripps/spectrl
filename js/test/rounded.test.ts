import test from "node:test"
import assert from "node:assert/strict"
import { decodeRounded, encodeRounded, roundedParameters, roundedWords, validateRounded } from "../src/rounded.ts"
import { decodePipeline, encodePipeline } from "../src/pipeline.ts"

const F32 = 1000521, F64 = 1000523
const FORMATS = { [F32]: [23, 4], [F64]: [52, 8] } as Record<number, [number, number]>

/** (u + 2^(d-1)) >> d on BigInt, independent of the codec's Number fast path. */
function referenceWord(value: number, type: number, bits: number): bigint {
  const [mantissa, size] = FORMATS[type]!
  const view = new DataView(new ArrayBuffer(8))
  let u: bigint
  if (size === 4) { view.setFloat32(0, value, true); u = BigInt(view.getUint32(0, true)) }
  else { view.setFloat64(0, value, true); u = view.getBigUint64(0, true) }
  const d = BigInt(mantissa - bits)
  return d === 0n ? u : (u + (1n << (d - 1n))) >> d
}

function values(type: number): number[] {
  let state = 4
  const random = () => (state = (state * 1103515245 + 12345) % 2 ** 31) / 2 ** 31
  const out: number[] = []
  for (let i = 0; i < 400; i++) {
    const v = (random() < 0.5 ? -1 : 1) * Math.exp((random() - 0.5) * 120)
    out.push(type === F32 ? Math.fround(v) : v)
  }
  const tiny = type === F32 ? 2 ** -126 : 2 ** -1022
  const sub = type === F32 ? 2 ** -149 : 5e-324
  out.push(0, -0, tiny, -tiny, sub, type === F32 ? Math.fround(tiny / 3) : tiny / 3, 1, 1.5, -2.75)
  return out.filter(v => Number.isFinite(v))
}

for (const type of [F32, F64]) for (const bits of [0, 1, 7, 12, 20, 23, 40, 52]) {
  const [mantissa] = FORMATS[type]!
  if (bits > mantissa) continue
  test(`rounded words and bound type ${type} bits ${bits}`, () => {
    const source = values(type)
    const words = roundedWords(source, type, bits)
    for (const [i, v] of source.entries()) assert.equal(BigInt(words[i]!), referenceWord(v, type, bits))
    const head = source.slice(0, 50)
    const array = type === F32 ? Float32Array.from(head) : Float64Array.from(head)
    const params = roundedParameters(array, type, bits)
    const out = decodeRounded(encodeRounded(array, type, params), type, head.length, params)
    assert.ok(type === F32 ? out instanceof Float32Array : out instanceof Float64Array)
    const d = mantissa - bits
    const tiny = type === F32 ? 2 ** -126 : 2 ** -1022
    const sub = type === F32 ? 2 ** -149 : 5e-324
    for (const [i, x] of head.entries()) {
      const y = out[i]!
      if (Math.abs(x) >= tiny) assert.ok(Math.abs(y - x) <= Math.abs(x) * 2 ** -(bits + 1))
      else assert.ok(Math.abs(y - x) <= (d ? 2 ** (d - 1) * sub : 0))
      assert.equal(Object.is(y, -0) || y < 0, Object.is(x, -0) || x < 0)
    }
  })
}

test("all mantissa bits is bit exact", () => {
  for (const type of [F32, F64]) {
    const source = values(type)
    const array = type === F32 ? Float32Array.from(source) : Float64Array.from(source)
    const params = roundedParameters(array, type, FORMATS[type]![0])
    const out = decodeRounded(encodeRounded(array, type, params), type, array.length, params)
    assert.deepEqual(Buffer.from(out.buffer as ArrayBuffer), Buffer.from(array.buffer))
  }
})

test("carry, ties away from zero, and signed zero", () => {
  const p = { bits: 12, width: 4 }
  const below = 2 - 2 ** -52
  assert.deepEqual([...decodeRounded(encodeRounded(Float64Array.of(below, -below), F64, p), F64, 2, p)], [2, -2])
  const tie = 1 + 2 ** -13
  assert.deepEqual([...decodeRounded(encodeRounded(Float64Array.of(tie, -tie), F64, p), F64, 2, p)],
    [1 + 2 ** -12, -(1 + 2 ** -12)])
  const z = { bits: 0, width: 2 }
  const zeros = decodeRounded(encodeRounded(Float32Array.of(0, -0), F32, z), F32, 2, z)
  assert.ok(Object.is(zeros[0], 0) && Object.is(zeros[1], -0))
})

test("minimal widths", () => {
  const cases: [number, number, number[], number][] = [
    [F32, 0, [0, 1], 1], [F32, 0, [-1], 2], [F32, 12, [1], 4],
    [F64, 0, [1], 2], [F64, 20, [1], 4], [F64, 12, [1], 4], [F64, 30, [1], 8],
  ]
  for (const [type, bits, v, width] of cases) assert.deepEqual(roundedParameters(v, type, bits), { bits, width })
})

test("each width round trips through the pipeline", () => {
  const cases: [number, number, number, number[]][] = [
    [F32, 0, 1, [0, 2 ** -60]], [F32, 0, 2, [1, -1, 1e38]], [F32, 12, 4, [1.5, -7.25e-3]],
    [F64, 0, 2, [1, -1e300]], [F64, 12, 4, [123.456, -0]], [F64, 52, 8, [Math.PI, -Math.E]],
  ]
  for (const [type, bits, width, v] of cases) {
    const array = type === F32 ? Float32Array.from(v) : Float64Array.from(v)
    const params = { bits, width }
    const { blob, fidelity } = encodePipeline(array, type, [4, 1, params])
    assert.equal(fidelity, 1)
    assert.equal(blob.length, width * v.length)
    decodePipeline(blob, type, v.length, [4, 1, params], 1)
  }
})

test("writer rejects nonfinite rounding and overwide words", () => {
  assert.throws(() => encodeRounded(Float32Array.of(3.4028234663852886e38), F32, { bits: 0, width: 2 }), /not finite/)
  assert.throws(() => encodeRounded(Float64Array.of(1), F64, { bits: 12, width: 2 }), /word width/)
  assert.throws(() => encodeRounded(Float64Array.of(Infinity), F64, { bits: 12, width: 4 }), /finite values/)
})

test("decoder rejections", () => {
  const le = (value: number, width: number) => {
    const b = new Uint8Array(width)
    for (let i = 0; i < width; i++) b[i] = Math.floor(value / 256 ** i) % 256
    return b
  }
  const cases: [object, number, Uint8Array, RegExp][] = [
    [{ bits: 12, width: 4 }, F64, le(2 ** 24, 4), /declared type/],
    [{ bits: 0, width: 2 }, F32, le(2 ** 9, 2), /declared type/],
    [{ bits: 12, width: 8 }, F32, new Uint8Array(8), /width exceeds/],
    [{ bits: 24, width: 4 }, F32, new Uint8Array(4), /bits exceed/],
    [{ bits: 12, width: 4 }, F64, new Uint8Array(5), /byte count/],
    [{ bits: 0, width: 2 }, F32, le(0xFF, 2), /not finite/],
    [{ bits: 12, width: 4 }, 1000519, new Uint8Array(4), /float32 or float64/],
  ]
  for (const [p, type, blob, message] of cases) assert.throws(() => decodeRounded(blob, type, 1, p as never), message)
})

test("invalid parameters and int32", () => {
  for (const p of [{ bits: 12 }, { width: 4 }, { bits: 12, width: 4, log: true }, { bits: -1, width: 4 },
    { bits: 53, width: 8 }, { bits: 1.5, width: 4 }, { bits: true, width: 4 }, { bits: 12, width: 3 }])
    assert.throws(() => validateRounded(p as never))
  assert.throws(() => encodePipeline(Int32Array.of(1), 1000519, [4, 1, { bits: 12, width: 4 }]))
  assert.throws(() => decodePipeline(new Uint8Array(4), 1000519, 1, [4, 1, { bits: 12, width: 4 }], 1))
})
