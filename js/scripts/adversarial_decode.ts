/**
 * Decode an adversarial corpus and report this implementation's verdict.
 *
 * Reads the JSON written by `scripts/adversarial_corpus.py` and writes one
 * verdict per case, in the same shape the Python `verdict()` helper produces,
 * so `scripts/check_adversarial_parity.py` can compare them directly.
 *
 *   node --import tsx scripts/adversarial_decode.ts corpus.json verdicts.json
 */
import { readFileSync, writeFileSync } from "node:fs"
import { decodeToken, SpectrlDecodeError } from "../src/index.js"

interface Case { name: string; token: string }

function verdict(token: string): Record<string, unknown> {
  let decoded
  try {
    decoded = decodeToken(token)
  } catch (e) {
    if (e instanceof SpectrlDecodeError) return { ok: false }
    // Anything else escaping the decoder is the finding, not a crash.
    return { ok: false, escape: (e as Error)?.constructor?.name ?? "unknown", message: String((e as Error)?.message).slice(0, 200) }
  }
  return {
    ok: true,
    n: decoded.defaultArrayLength,
    nparams: (decoded.params ?? []).length,
    nuser: (decoded.userParams ?? []).length,
    arrays: Object.keys(decoded.extraArrays ?? {}).sort(),
    mz: decoded.mz ? Array.from(decoded.mz).slice(0, 3) : null,
    units: Object.fromEntries(Object.entries(decoded.arrayUnits ?? {}).sort()),
  }
}

const [, , input, output] = process.argv
if (!input || !output) {
  console.error("usage: adversarial_decode.ts <corpus.json> <verdicts.json>")
  process.exit(2)
}
const cases: Case[] = JSON.parse(readFileSync(input, "utf8"))
writeFileSync(output, JSON.stringify(cases.map((c) => verdict(c.token))))
console.error(`decoded ${cases.length} adversarial cases`)
