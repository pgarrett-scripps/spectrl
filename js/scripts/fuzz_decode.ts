/** Deterministic decoder mutation smoke test for CI and local hardening. */

import { decodeToken, encodeSpectrum, SpectrlDecodeError } from "../src/index.ts";

let state = 0x5ec7;
function random(): number {
  state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
  return state / 0x100000000;
}

const seed = encodeSpectrum(
  { defaultArrayLength: 3, mz: [100, 200, 300], intensity: [10, 20, 30] },
  { quiet: true },
);
for (let trial = 0; trial < 2_000; trial++) {
  const chars = [...seed];
  const edits = 1 + Math.floor(random() * 8);
  for (let edit = 0; edit < edits && chars.length; edit++) {
    const i = Math.floor(random() * chars.length);
    if (random() < 0.15) chars.splice(i, 1);
    else chars[i] = String.fromCharCode(chars[i]!.charCodeAt(0) ^ (1 << Math.floor(random() * 7)));
  }
  try {
    decodeToken(chars.join(""));
  } catch (error) {
    if (!(error instanceof SpectrlDecodeError)) throw error;
  }
}
console.log("TypeScript decoder mutation smoke test passed (2,000 cases)");
