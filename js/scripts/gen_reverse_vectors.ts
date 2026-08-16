/**
 * Generate "reverse" conformance vectors: tokens encoded by the JavaScript
 * implementation, plus the values JS recovers from them. The Python reference
 * impl decodes these in `tests/test_reverse_vectors.py`, proving JS → Python
 * interoperability (the existing `vectors.json` proves Python → JS).
 *
 * Output: test-vectors/reverse-vectors.json
 * Run:    node --import tsx scripts/gen_reverse_vectors.ts   (from js/)
 */

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import {
  decodeToken,
  encodeSpectrum,
  type CvParam,
  type DecodedSpectrum,
  type InlineSpectrum,
  type UserParam,
} from "../src/index.ts";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(here, "../../test-vectors/reverse-vectors.json");

const LOSSY_TOL = { abs: 1e-6, rel: 1e-6 };
const EXACT_TOL = { abs: 1e-9, rel: 0.0 };

function paramJson(p: CvParam) {
  return { accession: p.accession, value: p.value ?? null, unit_accession: p.unitAccession ?? null };
}
function paramsJson(ps: CvParam[]) {
  return ps.map(paramJson);
}
function userParamJson(u: UserParam) {
  return { name: u.name, value: u.value ?? null, type: u.type ?? null, unit_accession: u.unitAccession ?? null };
}
function userParamsJson(us: UserParam[]) {
  return us.map(userParamJson);
}
function arr(a: Float64Array | null) {
  return a === null ? null : Array.from(a);
}

function dtypeOf(a: Float64Array | Float32Array | Int32Array): string {
  return a instanceof Int32Array ? "int32" : a instanceof Float32Array ? "float32" : "float64";
}

function extraJson(e: Record<string, Float64Array | Float32Array | Int32Array>) {
  return Object.fromEntries(Object.entries(e).map(([k, a]) => [k, { dtype: dtypeOf(a), values: Array.from(a) }]));
}

function decodedJson(d: DecodedSpectrum) {
  return {
    default_array_length: d.defaultArrayLength,
    id: d.id,
    mz: arr(d.mz),
    intensity: arr(d.intensity),
    charge: arr(d.charge),
    ion_mobility: arr(d.ionMobility),
    ion_mobility_type: d.ionMobilityType,
    params: paramsJson(d.params),
    scans: d.scans.map((s) => ({
      params: paramsJson(s.params),
      windows: (s.windows ?? []).map((w) => ({ params: paramsJson(w.params) })),
      user_params: userParamsJson(s.userParams ?? []),
    })),
    scan_combination: d.scanCombination ? paramJson(d.scanCombination) : null,
    precursors: d.precursors.map((p) => ({
      isolation_window: p.isolationWindow ? { params: paramsJson(p.isolationWindow.params) } : null,
      selected_ions: (p.selectedIons ?? []).map((si) => ({ params: paramsJson(si.params) })),
      activation: p.activation ? { params: paramsJson(p.activation.params) } : null,
    })),
    products: d.products.map((pr) => ({ isolation_window: pr.isolationWindow ? { params: paramsJson(pr.isolationWindow.params) } : null })),
    interp: d.interp,
    user_params: userParamsJson(d.userParams),
    extra_arrays: extraJson(d.extraArrays),
    hash: d.hash,
    format_version: d.formatVersion,
  };
}

function vector(name: string, description: string, spec: InlineSpectrum, lossless: boolean) {
  const token = encodeSpectrum(spec, { lossless, quiet: true });
  return {
    name: lossless ? `${name}__lossless` : name,
    description: lossless ? `${description} (lossless)` : description,
    mode: lossless ? "lossless" : "lossy",
    token,
    tolerance: lossless ? EXACT_TOL : LOSSY_TOL,
    decoded: decodedJson(decodeToken(token)),
  };
}

const specs: Array<[string, string, InlineSpectrum]> = [
  ["minimal", "m/z and intensity only", { defaultArrayLength: 3, mz: [147.11, 175.119, 246.156], intensity: [1e5, 8e4, 3.2e4] }],
  [
    "centroid_ms2_params",
    "MS2 centroid with ms-level, polarity flag, centroid flag, TIC",
    {
      defaultArrayLength: 4,
      mz: [110.071, 175.119, 288.203, 405.221],
      intensity: [2.1e4, 9.9e4, 5.4e4, 1.2e4],
      id: "scan=1042",
      params: [{ accession: "MS:1000511", value: 2 }, { accession: "MS:1000130" }, { accession: "MS:1000127" }, { accession: "MS:1000285", value: 187600.0 }],
    },
  ],
  ["with_charge_array", "per-peak charge array", { defaultArrayLength: 3, mz: [500.25, 750.4, 1001.5], intensity: [4e4, 2e4, 1e4], charge: [2, 1, 1] }],
  [
    "negative_charge_sentinel",
    "charge array with a negative sentinel; lossy encode falls back to lossless zlib for the charge array",
    { defaultArrayLength: 3, mz: [500.25, 750.4, 1001.5], intensity: [4e4, 2e4, 1e4], charge: [2, -1, 1] },
  ],
  [
    "negative_intensity_fallback",
    "baseline-subtracted intensities with negative values; lossy encode falls back to lossless zlib for the intensity array",
    { defaultArrayLength: 3, mz: [100.0, 200.0, 300.0], intensity: [-0.5, 1e4, -3.0] },
  ],
  [
    "precursor_full",
    "isolation window, selected ion, and HCD activation",
    {
      defaultArrayLength: 3,
      mz: [129.102, 258.156, 386.18],
      intensity: [3e4, 7e4, 2e4],
      params: [{ accession: "MS:1000511", value: 2 }],
      precursors: [
        {
          isolationWindow: { params: [{ accession: "MS:1000827", value: 445.12 }, { accession: "MS:1000828", value: 0.75 }, { accession: "MS:1000829", value: 0.75 }] },
          selectedIons: [{ params: [{ accession: "MS:1000744", value: 445.12 }, { accession: "MS:1000041", value: 2 }] }],
          activation: { params: [{ accession: "MS:1000422" }, { accession: "MS:1000045", value: 27.0, unitAccession: "UO:0000266" }] },
        },
      ],
    },
  ],
  ["with_proforma", "ProForma interpretation", { defaultArrayLength: 3, mz: [147.113, 276.155, 389.239], intensity: [1e5, 5e4, 2e4], interp: "ELVIS[Phospho]K/2" }],
  ["ion_mobility", "per-peak ion mobility array", { defaultArrayLength: 3, mz: [300.1, 600.2, 900.3], intensity: [4e4, 3e4, 2e4], ionMobility: [0.82, 0.91, 1.05], ionMobilityType: "MS:1003008" }],
  [
    "non_ms_ontology_param_key",
    "a UO-ontology parameter (string map key)",
    { defaultArrayLength: 2, mz: [123.04, 456.07], intensity: [9e4, 1e4], params: [{ accession: "MS:1000511", value: 1 }, { accession: "UO:0000010", value: 3.5 }] },
  ],
  [
    "user_params",
    "free-text userParams: spectrum-level (typed value + unit) and a scan-level trailer extra",
    {
      defaultArrayLength: 2,
      mz: [200.1, 400.2],
      intensity: [5e4, 6e4],
      params: [{ accession: "MS:1000511", value: 2 }],
      userParams: [
        { name: "Mascot score", value: 42.7, type: "xsd:float" },
        { name: "reanalysis note", value: "rerun with semitryptic" },
      ],
      scans: [
        {
          params: [{ accession: "MS:1000016", value: 20.5, unitAccession: "UO:0000031" }],
          userParams: [{ name: "[Thermo Trailer Extra]Monoisotopic M/Z:", value: "445.1203", type: "xsd:string" }],
        },
      ],
    },
  ],
  [
    "extra_arrays",
    "auxiliary arrays: signal-to-noise (named CV, float64), non-standard float32 and int32",
    {
      defaultArrayLength: 4,
      mz: [150.05, 300.1, 450.2, 600.3],
      intensity: [8e4, 5e4, 3e4, 1e4],
      extraArrays: {
        "MS:1000517": new Float64Array([120, 80, 45, 12]),
        iso_score: new Float32Array([0.98, 0.91, 0.74, 0.55]),
        peak_flags: new Int32Array([3, 1, 0, 2]),
      },
    },
  ],
];

const vectors = specs.flatMap(([name, desc, spec]) => [vector(name, desc, spec, false), vector(name, desc, spec, true)]);

const doc = {
  spectrl_format_version: 2,
  generated_by: `spectrl-js ${JSON.parse(readFileSync(resolve(here, "../package.json"), "utf8")).version}`,
  note: "Reverse vectors: tokens encoded by the JS implementation, decoded values recorded. Other implementations MUST decode `token` and match `decoded` within `tolerance`, and the `hash` MUST verify.",
  vectors,
};

writeFileSync(OUT, JSON.stringify(doc, null, 2) + "\n");
console.log(`Wrote ${vectors.length} reverse vectors to ${OUT}`);
