/** Test bridge: encode the same spectrum_to_dict inputs as the Python writer. */
import { readFileSync } from "node:fs"
import { decodeToken, encodeSpectrum, type InlineSpectrum, type EncodeOptions } from "../src/index.ts"
import { installBrotli } from "../src/brotli-node.ts"

const camel = (key: string) => key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())

function data(value: any): any {
  if (Array.isArray(value)) return value.map(data)
  if (value && typeof value === "object") {
    if (value.$spectrl === "bytes") return Uint8Array.from(Buffer.from(value.hex, "hex"))
    if (value.$spectrl === "map") return new Map(value.items.map(([k, v]: any[]) => [data(k), data(v)]))
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, data(v)]))
  }
  return value
}

function metadata(value: any): any {
  if (Array.isArray(value)) return value.map(metadata)
  if (!value || typeof value !== "object") return value
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [camel(key),
    // User-owned keys are never renamed.
    ["parameters", "extensions", "array_extensions", "array_units", "array_names", "cv_versions"].includes(key) ? data(child)
      : ["array_params", "array_user_params", "array_processing"].includes(key)
        ? Object.fromEntries(Object.entries(child as object).map(([k, v]) => [k, metadata(v)]))
        : metadata(child),
  ]))
}

export function inputSpectrum(input: any): InlineSpectrum {
  const { array_dtypes = {}, extra_array_dtypes = {}, extra_arrays = {}, ...rest } = input
  const spec = metadata(rest)
  const constructors = { float64: Float64Array, float32: Float32Array, int32: Int32Array }
  const array = (values: number[], dtype = "float64") => {
    const Constructor = constructors[dtype as keyof typeof constructors]
    if (!Constructor) throw Error(`invalid test array dtype ${dtype}`)
    return new Constructor(values)
  }
  for (const key of ["mz", "intensity", "charge"]) {
    if (rest[key] != null) spec[key] = array(rest[key], array_dtypes[key])
  }
  spec.extraArrays = Object.fromEntries(Object.entries(extra_arrays).map(([key, values]) =>
    [key, array(values as number[], extra_array_dtypes[key])]))
  return spec
}

export function inputOptions(input: any): EncodeOptions {
  return Object.fromEntries(Object.entries(input).map(([k, v]) => [camel(k), v]))
}

/** The exact float64 bits each core array reconstructs to, as hex. */
function decodedBits(token: string): Record<string, string | null> {
  const decoded = decodeToken(token)
  const hex = (values: ArrayLike<number> | null) => {
    if (!values) return null
    const words = new Float64Array(values.length)
    for (let i = 0; i < values.length; i++) words[i] = values[i]!
    return Buffer.from(words.buffer, words.byteOffset, words.byteLength).toString("hex")
  }
  return { mz: hex(decoded.mz), intensity: hex(decoded.intensity), charge: hex(decoded.charge) }
}

// Importable by the standalone JS conformance tests as well as callable by Python.
if (process.argv[1]?.endsWith("token_parity.ts")) {
  await installBrotli()
  const cases = JSON.parse(readFileSync(0, "utf8"))
  const result = cases.map((item: any) => {
    try {
      const token = encodeSpectrum(inputSpectrum(item.spec), { ...inputOptions(item.options), quiet: true })
      // The decoded arrays travel back too. A token that is byte-identical can
      // still reconstruct different values if the two runtimes disagree about
      // expm1, which is the whole reason src/deterministic.ts exists.
      return { name: item.name, token, decoded: decodedBits(token) }
    } catch (error) {
      return { name: item.name, error: String(error) }
    }
  })
  process.stdout.write(JSON.stringify(result))
}
