/**
 * Regression pin for the JS-authored reverse vectors: the JS implementation must
 * decode its own committed `reverse-vectors.json` and reproduce the recorded
 * values (the same fixtures the Python impl decodes for JS → Python interop).
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { test } from "node:test";

import { decodeToken } from "../src/index.ts";
import { installZstd } from "../src/zstd.ts";

installZstd();

const here = dirname(fileURLToPath(import.meta.url));
const path = resolve(here, "../../test-vectors/reverse-vectors.json");

if (!existsSync(path)) {
  test("reverse vectors present", { skip: "run: npm run gen-vectors" }, () => {});
} else {
  const doc = JSON.parse(readFileSync(path, "utf-8"));
  for (const v of doc.vectors) {
    test(`reverse self-decode: ${v.name} (${v.mode})`, () => {
      const tol = v.tolerance;
      const d = decodeToken(v.token);
      const exp = v.decoded;
      assert.equal(d.defaultArrayLength, exp.default_array_length);
      assert.equal(d.checksum, exp.checksum);
      assert.equal(d.id, exp.id);
      for (const [name, actual] of [
        ["mz", d.mz],
        ["intensity", d.intensity],
        ["charge", d.charge],
      ] as const) {
        const e = exp[name];
        if (e === null) {
          assert.equal(actual, null, name);
          continue;
        }
        assert.equal(actual!.length, e.length, name);
        for (let i = 0; i < e.length; i++) {
          assert.ok(Math.abs(actual![i]! - e[i]) <= tol.abs + tol.rel * Math.abs(e[i]), `${name}[${i}]`);
        }
      }
    });
  }
}
