/**
 * spectrl browser demo.
 *
 * Builds example spectra, encodes them live with the real @spectrl-ms/spectrl
 * codec, shows the shareable URL + QR, then decodes the token and renders a
 * stick plot, all in the browser, no network.
 */
import {
  encodeSpectrum,
  decodeToken,
  toFragment,
  extractToken,
  tokenBreakdown,
  mobilityArrays,
  ArrayAccession,
  type InlineSpectrum,
  type CvParam,
  type DecodedSpectrum,
} from "../../js/dist/index.js";
import { installZstd } from "../../js/dist/zstd.js";
// qrcode-generator is CommonJS. esbuild provides the default-import interop.
import qrcode from "qrcode-generator";

installZstd();

// ---------------------------------------------------------------------------
// Tiny mass calculator (monoisotopic) for chemically real fragment ions.
// ---------------------------------------------------------------------------
const PROTON = 1.0072764665;
const WATER = 18.0105646863;
const RESIDUE: Record<string, number> = {
  G: 57.02146, A: 71.03711, S: 87.03203, P: 97.05276, V: 99.06841,
  T: 101.04768, C: 103.00919, L: 113.08406, I: 113.08406, N: 114.04293,
  D: 115.02694, Q: 128.05858, K: 128.09496, E: 129.04259, M: 131.04049,
  H: 137.05891, F: 147.06841, R: 156.10111, Y: 163.06333, W: 186.07931,
};

interface Peak { mz: number; intensity: number }

/** Singly-charged b and y ion series for a bare peptide sequence. */
function fragmentIons(peptide: string): Peak[] {
  const res = [...peptide].map((a) => RESIDUE[a] ?? 0);
  const n = res.length;
  const peaks: Peak[] = [];
  let bSum = 0;
  for (let i = 0; i < n - 1; i++) {
    bSum += res[i]!;
    peaks.push({ mz: bSum + PROTON, intensity: 0 });
  }
  let ySum = 0;
  for (let i = n - 1; i > 0; i--) {
    ySum += res[i]!;
    peaks.push({ mz: ySum + WATER + PROTON, intensity: 0 });
  }
  // Deterministic pseudo-random intensities so the plot looks like real data.
  let seed = 1337;
  const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
  for (const p of peaks) p.intensity = 1000 + rnd() * rnd() * 9e4;
  peaks.sort((a, b) => a.mz - b.mz);
  return peaks;
}

function precursorMz(peptide: string, charge: number): number {
  const mass = [...peptide].reduce((s, a) => s + (RESIDUE[a] ?? 0), 0) + WATER;
  return (mass + charge * PROTON) / charge;
}

/** A simple decaying isotope envelope around a base m/z (1 Da spacing / charge). */
function isotopeEnvelope(baseMz: number, charge: number, n: number, base = 1e5): Peak[] {
  const peaks: Peak[] = [];
  for (let i = 0; i < n; i++) {
    peaks.push({ mz: baseMz + (i * 1.00335) / charge, intensity: base * Math.exp(-0.55 * i) });
  }
  return peaks;
}

// ---------------------------------------------------------------------------
// Example spectra → InlineSpectrum
// ---------------------------------------------------------------------------
const flag = (acc: string): CvParam => ({ accession: acc });
const val = (acc: string, value: number | string, unit?: string): CvParam => ({
  accession: acc,
  value,
  ...(unit ? { unitAccession: unit } : {}),
});

function fromPeaks(peaks: Peak[]): { mz: number[]; intensity: number[] } {
  return { mz: peaks.map((p) => p.mz), intensity: peaks.map((p) => p.intensity) };
}

function peptideMs2(peptide: string): InlineSpectrum {
  const peaks = fragmentIons(peptide);
  const { mz, intensity } = fromPeaks(peaks);
  const preMz = precursorMz(peptide, 2);
  return {
    defaultArrayLength: mz.length,
    mz,
    intensity,
    id: `scan=1042 (${peptide}, 2+)`,
    interp: peptide,
    params: [
      val("MS:1000511", 2), // ms level
      flag("MS:1000130"), // positive scan
      flag("MS:1000127"), // centroid spectrum
    ],
    scans: [{ params: [val("MS:1000016", 24.71, "UO:0000031")] }], // scan start time (min)
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", preMz), val("MS:1000828", 1.0), val("MS:1000829", 1.0)] },
        selectedIons: [{ params: [val("MS:1000744", preMz), val("MS:1000041", 2)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 28, "UO:0000266")] }, // HCD, 28 eV
      },
    ],
  };
}

function smallMoleculeMs1(): InlineSpectrum {
  const peaks = [
    ...isotopeEnvelope(522.3558, 1, 5, 1e5),
    ...isotopeEnvelope(746.1234, 1, 4, 4.2e4),
    ...isotopeEnvelope(301.1411, 1, 3, 2.6e4),
  ].sort((a, b) => a.mz - b.mz);
  const { mz, intensity } = fromPeaks(peaks);
  return {
    defaultArrayLength: mz.length,
    mz,
    intensity,
    id: "scan=88",
    params: [val("MS:1000511", 1), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 3.42, "UO:0000031")] }],
  };
}

/** A synthetic profile-style MS¹ scan with `n` peaks (seeded → deterministic). */
function randomSpectrum(n: number): InlineSpectrum {
  let seed = (0x2545f491 ^ (n * 2654435761)) & 0x7fffffff;
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
  const peaks: Peak[] = [];
  for (let i = 0; i < n; i++) {
    const mz = 150 + rnd() * 1850;
    const intensity = Math.pow(rnd(), 3) * 1e6 + 100; // skewed: many small, few tall
    peaks.push({ mz, intensity });
  }
  peaks.sort((a, b) => a.mz - b.mz);
  const { mz, intensity } = fromPeaks(peaks);
  return {
    defaultArrayLength: n,
    mz,
    intensity,
    id: `scan=${n}`,
    params: [val("MS:1000511", 1), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 12.5, "UO:0000031")] }],
  };
}

/** A dense centroided top-down MS² scan with an intact, highly charged precursor. */
function topDownMs2(): InlineSpectrum {
  const base = randomSpectrum(320);
  const mz = Array.from(base.mz as number[]);
  const intensity = Array.from(base.intensity as number[]);
  const precursor = 1029.5832;
  const charge = mz.map((m, i) => 1 + ((Math.floor(m) + i * 3) % 8));
  return {
    ...base,
    mz,
    intensity,
    charge,
    id: "scan=2201 (intact protein, 12+)",
    params: [val("MS:1000511", 2), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 45.18, "UO:0000031")] }],
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", precursor), val("MS:1000828", 2), val("MS:1000829", 2)] },
        selectedIons: [{ params: [val("MS:1000744", precursor), val("MS:1000041", 12)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 35, "UO:0000266")] },
      },
    ],
  };
}

/** Per-peak inverse reduced ion mobility alongside a centroided MS² scan. */
function ionMobilityMs2(): InlineSpectrum {
  const base = randomSpectrum(180);
  const mz = Array.from(base.mz as number[]);
  const intensity = Array.from(base.intensity as number[]);
  const ionMobility = mz.map((m, i) => 0.68 + ((m - 150) / 1850) * 0.55 + Math.sin(i * 0.71) * 0.012);
  const precursor = 687.8421;
  return {
    ...base,
    mz,
    intensity,
    extraArrays: {
      [ArrayAccession.RAW_INVERSE_REDUCED_ION_MOBILITY]: ionMobility,
    },
    id: "frame=412 scan=37",
    params: [val("MS:1000511", 2), flag("MS:1000130"), flag("MS:1000127")],
    scans: [{ params: [val("MS:1000016", 18.73, "UO:0000031")] }],
    precursors: [
      {
        isolationWindow: { params: [val("MS:1000827", precursor), val("MS:1000828", 0.7), val("MS:1000829", 0.7)] },
        selectedIons: [{ params: [val("MS:1000744", precursor), val("MS:1000041", 2)] }],
        activation: { params: [flag("MS:1000422"), val("MS:1000045", 30, "UO:0000266")] },
      },
    ],
  };
}

/** A spectrum carrying standard and free-text auxiliary arrays for every peak. */
function auxiliaryArraySpectrum(): InlineSpectrum {
  const base = randomSpectrum(120);
  const intensity = Array.from(base.intensity as number[]);
  return {
    ...base,
    id: "scan=731 (auxiliary arrays)",
    extraArrays: {
      "MS:1000517": new Float64Array(intensity.map((v, i) => v / (900 + (i % 11) * 85))),
      local_baseline: new Float32Array(intensity.map((_, i) => 600 + 240 * Math.sin(i * 0.19) ** 2)),
      peak_flags: new Int32Array(intensity.map((v, i) => (v > 500000 ? 2 : i % 9 === 0 ? 1 : 0))),
    },
  };
}

const EXAMPLES: Record<string, () => InlineSpectrum> = {
  ms2: () => peptideMs2("PEPTIDER"),
  ms1: smallMoleculeMs1,
  topdown: topDownMs2,
  mobility: ionMobilityMs2,
  aux: auxiliaryArraySpectrum,
  r100: () => randomSpectrum(100),
  r500: () => randomSpectrum(500),
};

// ---------------------------------------------------------------------------
// CV label map for the metadata table
// ---------------------------------------------------------------------------
const CV_LABEL: Record<string, string> = {
  "MS:1000511": "ms level",
  "MS:1000127": "centroid spectrum",
  "MS:1000128": "profile spectrum",
  "MS:1000130": "positive scan",
  "MS:1000129": "negative scan",
  "MS:1000016": "scan start time",
  "MS:1000744": "selected ion m/z",
  "MS:1000041": "charge state",
  "MS:1000045": "collision energy",
  "MS:1000422": "HCD (beam-type CID)",
  "MS:1000133": "CID",
  "MS:1000827": "isolation window target m/z",
  "MS:1000828": "isolation window lower offset",
  "MS:1000829": "isolation window upper offset",
  "MS:1003008": "inverse reduced ion mobility",
  "MS:1000517": "signal-to-noise array",
  "UO:0000031": "minute",
  "UO:0000266": "electronvolt",
};
const label = (acc: string) => CV_LABEL[acc] ?? acc;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = <T extends HTMLElement = HTMLElement>(sel: string) => document.querySelector(sel) as T;
const tokenEl = $<HTMLTextAreaElement>("#token");
const tokenMeta = $("#tokenMeta");
const qrEl = $("#qr");
const plotEl = $("#plot");
const metaTable = $("#metaTable");
const decodeErr = $("#decodeErr");
const tip = $("#tip");
const losslessEl = $<HTMLInputElement>("#lossless");
const statsEl = $("#stats");
const spectrumSummaryEl = $("#spectrumSummary");

let suppressHash = false;
// The InlineSpectrum the current token was encoded from (null when pasted),
// plus the measured encode time, used for round-trip precision + size stats.
let lastSource: InlineSpectrum | null = null;
let lastEncodeMs: number | null = null;
let currentShare = ""; // shareable URL for the current token. Copied on demand.

function baseUrl(): string {
  return location.origin + location.pathname;
}

// ---------------------------------------------------------------------------
// Render pipeline
// ---------------------------------------------------------------------------
function setToken(token: string, pushHash = true) {
  tokenEl.value = token;
  if (pushHash) {
    suppressHash = true;
    location.hash = token;
    setTimeout(() => (suppressHash = false), 0);
  }
  renderFromToken(token);
}

function encodeAndShow(spec: InlineSpectrum) {
  const t0 = performance.now();
  const token = encodeSpectrum(spec, { lossless: losslessEl.checked, quiet: true });
  lastEncodeMs = performance.now() - t0;
  lastSource = spec;
  setToken(token);
}

let zstdBackendPromise: Promise<unknown> | null = null;

async function renderFromToken(token: string) {
  token = token.trim();
  currentShare = toFragment(token, baseUrl());
  renderQr(currentShare);

  decodeErr.textContent = "";
  let decoded: DecodedSpectrum;
  let decodeMs: number;
  try {
    const t0 = performance.now();
    decoded = decodeToken(token);
    decodeMs = performance.now() - t0;
  } catch (e) {
    if ((e as Error).message.includes("zstd support is not loaded")) {
      zstdBackendPromise ??= import("../../js/dist/zstd.js");
      try {
        await zstdBackendPromise;
        await renderFromToken(token);
        return;
      } catch (loadError) {
        e = loadError;
      }
    }
    decodeErr.textContent = `Decode failed: ${(e as Error).message}`;
    plotEl.innerHTML = "";
    metaTable.innerHTML = "";
    statsEl.innerHTML = "";
    spectrumSummaryEl.innerHTML = "";
    tokenMeta.innerHTML = `token size: <b>${fmtBytes(token.length)}</b>`;
    return;
  }

  const npeaks = decoded.mz?.length ?? 0;
  tokenMeta.innerHTML =
    `<b>${fmtBytes(token.length)}</b> link payload &nbsp;·&nbsp; <b>${npeaks}</b> peaks ` +
    `&nbsp;·&nbsp; <b>checksum verified ✓</b>`;

  renderStats(token, decoded, decodeMs);
  renderPlot(decoded);
  renderSpectrumSummary(decoded);
  renderMeta(decoded);
}

function renderSpectrumSummary(d: DecodedSpectrum) {
  const chips: Array<[string, string]> = [];
  if (d.interp) chips.push([d.interp, "ProForma"]);
  const level = msLevel(d);
  if (level !== null) chips.push([`MS${level === 2 ? "²" : level === 3 ? "³" : level}`, "level"]);
  const precursorMz = d.precursors
    .flatMap((p) => p.selectedIons ?? [])
    .flatMap((ion) => ion.params)
    .find((p) => p.accession === "MS:1000744")?.value;
  if (typeof precursorMz === "number") chips.push([precursorMz.toFixed(4), "precursor m/z"]);
  const charge = d.precursors
    .flatMap((p) => p.selectedIons ?? [])
    .flatMap((ion) => ion.params)
    .find((p) => p.accession === "MS:1000041")?.value;
  if (typeof charge === "number") chips.push([`${charge}+`, "charge"]);
  const activation = d.precursors
    .flatMap((p) => p.activation?.params ?? [])
    .find((p) => p.accession === "MS:1000422" || p.accession === "MS:1000133");
  if (activation) chips.push([label(activation.accession).replace(" (beam-type CID)", ""), "activation"]);
  const mobilityCount = Object.keys(mobilityArrays(d)).length;
  if (mobilityCount) chips.push([`${mobilityCount}`, "ion mobility array(s)"]);
  const extraCount = Object.keys(d.extraArrays).length - mobilityCount;
  if (extraCount) chips.push([`${extraCount}`, "auxiliary arrays"]);
  chips.push([`${d.mz?.length ?? 0}`, "peaks"]);

  spectrumSummaryEl.innerHTML = chips
    .map(([value, name]) => `<div class="chip"><b>${value}</b><span>${name}</span></div>`)
    .join("");
}

function renderQr(url: string) {
  qrEl.innerHTML = "";
  try {
    const qr = qrcode(0, "L");
    qr.addData(url);
    qr.make();
    const img = document.createElement("img");
    img.src = qr.createDataURL(4, 8);
    img.alt = "QR code of the shareable URL";
    img.width = Math.min(qr.getModuleCount() * 4 + 16, 280);
    qrEl.appendChild(img);
    const cap = document.createElement("div");
    cap.className = "meta";
    cap.innerHTML = `${fmtBytes(url.length)} · scan to open the spectrum`;
    qrEl.appendChild(cap);
  } catch {
    qrEl.innerHTML = `<div class="meta">Token too large for a single QR code (${url.length} chars).<br/>Trim the peak list or share the token through a channel without QR-size limits.</div>`;
  }
}

function renderMeta(d: DecodedSpectrum) {
  const rows: string[] = [];
  const add = (k: string, v: string, acc = "") =>
    rows.push(`<tr><td class="k">${k}</td><td>${v}</td><td class="acc">${acc}</td></tr>`);

  if (d.id) add("native id", d.id);
  if (d.interp) add("ProForma", `<b style="color:var(--accent-2)">${d.interp}</b>`, "key 7");

  for (const p of d.params) {
    add(label(p.accession), fmtVal(p), p.accession);
  }
  for (const s of d.scans) for (const p of s.params) add(label(p.accession), fmtVal(p), p.accession);

  d.precursors.forEach((pre, i) => {
    const tag = d.precursors.length > 1 ? ` #${i + 1}` : "";
    for (const ion of pre.selectedIons ?? [])
      for (const p of ion.params) add(`precursor${tag}: ${label(p.accession)}`, fmtVal(p), p.accession);
    for (const p of pre.activation?.params ?? [])
      add(`activation${tag}: ${label(p.accession)}`, fmtVal(p), p.accession);
    for (const p of pre.isolationWindow?.params ?? [])
      add(`isolation${tag}: ${label(p.accession)}`, fmtVal(p), p.accession);
  });

  metaTable.innerHTML = rows.join("");
}

function fmtVal(p: CvParam): string {
  if (p.value === null || p.value === undefined) return "<span style='color:var(--muted)'>(flag)</span>";
  const v = typeof p.value === "number" ? round(p.value, 5) : p.value;
  return p.unitAccession ? `${v} <span style="color:var(--muted)">${label(p.unitAccession)}</span>` : `${v}`;
}

const round = (x: number, n: number) => {
  const f = 10 ** n;
  return Math.round(x * f) / f;
};

/** Format a byte count; base64url tokens are ASCII so 1 char = 1 byte. */
const fmtBytes = (n: number) => (n >= 1024 ? `${(n / 1024).toFixed(2)} KB` : `${n} B`);

// ---------------------------------------------------------------------------
// Encoding stats
// ---------------------------------------------------------------------------
const SEG_COLOR: Record<string, string> = {
  header: "#8b97a6",
  "m/z": "#4cc2ff",
  intensity: "#7ee787",
  charge: "#d2a8ff",
  "ion mobility": "#ffa657",
  "signal-to-noise": "#f2cc60",
  local_baseline: "#ff9bce",
  peak_flags: "#79c0ff",
};

function statCard(label: string, value: string, sub = "", cls = ""): string {
  return (
    `<div class="stat"><div class="label">${label}</div>` +
    `<div class="value ${cls}">${value}</div>` +
    (sub ? `<div class="sub">${sub}</div>` : "") +
    `</div>`
  );
}

function renderStats(token: string, d: DecodedSpectrum, decodeMs: number) {
  const n = d.mz?.length ?? 0;
  const cards: string[] = [];

  // --- size ---
  const bytesPerPeak = n ? token.length / n : 0;
  cards.push(statCard("token size", fmtBytes(token.length), `${bytesPerPeak.toFixed(1)} B/peak`, "accent"));

  // raw IEEE-754 float64 payload (what the numbers cost uncompressed)
  let rawBytes = n * 16; // m/z + intensity
  if (d.charge) rawBytes += n * 8;
  for (const array of Object.values(d.extraArrays)) rawBytes += array.byteLength;
  const tokenOverRaw = token.length / Math.max(rawBytes, 1);
  cards.push(
    statCard(
      "complete token vs peak arrays",
      `${tokenOverRaw.toFixed(1)}×`,
      `${fmtBytes(rawBytes)} raw float64 arrays. Token also includes metadata + framing`,
    ),
  );

  // the other mode, when we know the source spectrum
  if (lastSource) {
    try {
      const altLossless = !losslessEl.checked;
      const altToken = encodeSpectrum(lastSource, { lossless: altLossless, quiet: true });
      const altName = altLossless ? "lossless" : "lossy";
      const delta = ((altToken.length - token.length) / token.length) * 100;
      cards.push(
        statCard(
          `${altName} would be`,
          fmtBytes(altToken.length),
          `${delta >= 0 ? "+" : ""}${delta.toFixed(0)}% vs current`,
        ),
      );
    } catch {
      /* alt-mode encode failed. Skip. */
    }
  }

  // --- spectrum summary ---
  cards.push(statCard("peaks", `${n}`, `ms level ${msLevel(d) ?? "?"}`));
  if (n) {
    const mz = d.mz!;
    cards.push(statCard("m/z range", `${round(mz[0]!, 1)}–${round(mz[n - 1]!, 1)}`, "min – max"));
    const bi = basePeakIndex(d);
    if (bi >= 0) cards.push(statCard("base peak m/z", `${round(mz[bi]!, 3)}`, `intensity ${round(d.intensity![bi]!, 0)}`));
  }

  // --- precision (lossy round-trip vs the source we encoded) ---
  if (lastSource && !losslessEl.checked) {
    const p = precision(lastSource, d);
    cards.push(
      statCard("max Δ m/z", `${p.maxMzMda.toFixed(4)} mDa`, `${p.maxMzPpm.toFixed(3)} ppm · mean ${p.meanMzPpm.toFixed(3)} ppm`, "good"),
    );
    cards.push(statCard("max Δ intensity", `${p.maxIntPct.toFixed(3)}%`, `mean ${p.meanIntPct.toFixed(3)}%`, "good"));
  } else if (lastSource && losslessEl.checked) {
    cards.push(statCard("round-trip error", "0", "bit-exact (IEEE-754)", "good"));
  }

  // --- performance + integrity ---
  if (lastEncodeMs !== null) cards.push(statCard("encode time", `${lastEncodeMs.toFixed(2)} ms`));
  cards.push(statCard("decode time", `${decodeMs.toFixed(2)} ms`));
  cards.push(statCard("checksum", "verified ✓", `CRC-32 · ${d.checksum}`, "good"));

  // --- size breakdown bar chart (header vs each array's compressed blob) ---
  const parts = tokenBreakdown(token);
  const maxPart = Math.max(...parts.map((s) => s.bytes), 1);
  const bars = parts
    .map((s) => {
      const pct = (s.bytes / maxPart) * 100;
      const color = SEG_COLOR[s.label] ?? "#8b97a6";
      return (
        `<div class="bar"><div>${s.label}</div>` +
        `<div class="track"><div class="fill" style="width:${pct}%;background:${color}"></div></div>` +
        `<div class="n">${fmtBytes(s.bytes)}</div></div>`
      );
    })
    .join("");
  cards.push(`<div class="stat wide"><div class="label">size breakdown (CBOR document bytes)</div><div class="bars">${bars}</div></div>`);

  statsEl.innerHTML = cards.join("");
}

function msLevel(d: DecodedSpectrum): number | null {
  const p = d.params.find((x) => x.accession === "MS:1000511");
  return p && typeof p.value === "number" ? p.value : null;
}

function basePeakIndex(d: DecodedSpectrum): number {
  const inten = d.intensity;
  if (!inten || inten.length === 0) return -1;
  let bi = 0;
  for (let i = 1; i < inten.length; i++) if (inten[i]! > inten[bi]!) bi = i;
  return bi;
}

const NUMPRESS_COMPS = new Set([1002746, 1002747, 1002748, 1003783, 1003784, 1003785]);

/** Mode of the token actually displayed (a pasted token may differ from the checkbox). */
function tokenMode(token: string): string {
  try {
    const lossy = tokenBreakdown(token).some((p) => p.comp !== undefined && NUMPRESS_COMPS.has(p.comp));
    return lossy ? "lossy (MS-Numpress)" : "lossless";
  } catch {
    return "unknown";
  }
}

/** Round-trip precision: compare decoded arrays (m/z-sorted) to the source we encoded. */
function precision(source: InlineSpectrum, d: DecodedSpectrum) {
  const smz = Array.from((source.mz ?? []) as ArrayLike<number>);
  const sint = Array.from((source.intensity ?? []) as ArrayLike<number>);
  const order = [...smz.keys()].sort((a, b) => smz[a]! - smz[b]!);
  const n = Math.min(order.length, d.mz?.length ?? 0);
  let maxMzAbs = 0, sumMzPpm = 0, maxMzPpm = 0, maxIntRel = 0, sumIntRel = 0;
  for (let k = 0; k < n; k++) {
    const om = smz[order[k]!]!, dm = d.mz![k]!;
    const oi = sint[order[k]!]!, di = d.intensity![k]!;
    const mzAbs = Math.abs(dm - om);
    const mzPpm = om ? (mzAbs / om) * 1e6 : 0;
    maxMzAbs = Math.max(maxMzAbs, mzAbs);
    maxMzPpm = Math.max(maxMzPpm, mzPpm);
    sumMzPpm += mzPpm;
    const ir = oi ? Math.abs(di - oi) / oi : 0;
    maxIntRel = Math.max(maxIntRel, ir);
    sumIntRel += ir;
  }
  return {
    maxMzMda: maxMzAbs * 1000,
    maxMzPpm,
    meanMzPpm: n ? sumMzPpm / n : 0,
    maxIntPct: maxIntRel * 100,
    meanIntPct: n ? (sumIntRel / n) * 100 : 0,
  };
}

// ---------------------------------------------------------------------------
// SVG stick plot
// ---------------------------------------------------------------------------
function renderPlot(d: DecodedSpectrum) {
  const mz = Array.from(d.mz ?? []);
  const inten = Array.from(d.intensity ?? []);
  if (mz.length === 0) {
    plotEl.innerHTML = `<div class="meta">No m/z array in this token.</div>`;
    return;
  }
  const W = 1000, H = 340, padL = 56, padR = 16, padT = 16, padB = 36;
  const mzMin = Math.min(...mz), mzMax = Math.max(...mz);
  const span = mzMax - mzMin || 1;
  const x0 = mzMin - span * 0.03, x1 = mzMax + span * 0.03;
  const iMax = Math.max(...inten) || 1;

  const sx = (v: number) => padL + ((v - x0) / (x1 - x0)) * (W - padL - padR);
  const sy = (v: number) => H - padB - (v / iMax) * (H - padT - padB);

  const parts: string[] = [];
  // axes
  parts.push(`<line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="var(--border)"/>`);
  parts.push(`<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="var(--border)"/>`);
  // y ticks (rel %)
  for (let f = 0; f <= 1.0001; f += 0.25) {
    const y = sy(f * iMax);
    parts.push(`<line x1="${padL - 4}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--border)" stroke-dasharray="2 4" opacity="0.5"/>`);
    parts.push(`<text x="${padL - 8}" y="${y + 4}" text-anchor="end">${Math.round(f * 100)}%</text>`);
  }
  // x ticks
  const ticks = 6;
  for (let i = 0; i <= ticks; i++) {
    const v = x0 + ((x1 - x0) * i) / ticks;
    const x = sx(v);
    parts.push(`<line x1="${x}" y1="${H - padB}" x2="${x}" y2="${H - padB + 4}" stroke="var(--border)"/>`);
    parts.push(`<text x="${x}" y="${H - padB + 18}" text-anchor="middle">${round(v, 1)}</text>`);
  }
  parts.push(`<text x="${(W) / 2}" y="${H - 4}" text-anchor="middle">m/z</text>`);

  // peaks
  for (let i = 0; i < mz.length; i++) {
    const x = sx(mz[i]!);
    parts.push(
      `<line x1="${x}" y1="${H - padB}" x2="${x}" y2="${sy(inten[i]!)}" ` +
        `stroke="var(--peak)" stroke-width="1.5" ` +
        `data-mz="${mz[i]}" data-int="${inten[i]}"/>`,
    );
  }

  plotEl.innerHTML = `<svg id="svg" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto" preserveAspectRatio="xMidYMid meet">${parts.join("")}</svg>`;
  wireTooltip(iMax);
}

function wireTooltip(iMax: number) {
  const svg = $<SVGSVGElement>("#svg");
  const lines = Array.from(svg.querySelectorAll("line[data-mz]"));
  for (const ln of lines) {
    ln.addEventListener("mousemove", (ev) => {
      const e = ev as MouseEvent;
      const mzv = Number((ln as Element).getAttribute("data-mz"));
      const iv = Number((ln as Element).getAttribute("data-int"));
      tip.style.display = "block";
      tip.style.left = `${e.clientX + 12}px`;
      tip.style.top = `${e.clientY + 12}px`;
      tip.innerHTML = `m/z <b>${round(mzv, 4)}</b><br/>int <b>${round(iv, 1)}</b> (${round((iv / iMax) * 100, 1)}%)`;
      (ln as SVGLineElement).setAttribute("stroke-width", "3");
    });
    ln.addEventListener("mouseleave", () => {
      tip.style.display = "none";
      (ln as SVGLineElement).removeAttribute("stroke-width");
    });
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------
let currentExample = "ms2";

document.querySelectorAll<HTMLButtonElement>("button[data-example]").forEach((btn) => {
  btn.addEventListener("click", () => {
    currentExample = btn.dataset.example!;
    document.querySelectorAll("button[data-example]").forEach((b) => b.classList.remove("primary"));
    btn.classList.add("primary");
    encodeAndShow(EXAMPLES[currentExample]!());
  });
});

losslessEl.addEventListener("change", () => encodeAndShow(EXAMPLES[currentExample]!()));

tokenEl.addEventListener("input", () => {
  lastSource = null; // pasted token: no known source for precision/alt-mode stats
  lastEncodeMs = null;
  setToken(tokenEl.value, true);
});

async function flashCopy(btn: HTMLButtonElement, text: string) {
  await navigator.clipboard.writeText(text);
  const orig = btn.textContent;
  btn.textContent = "copied!";
  setTimeout(() => (btn.textContent = orig), 1200);
}

const copyLinkBtn = $<HTMLButtonElement>("#copyLink");
copyLinkBtn.addEventListener("click", () => flashCopy(copyLinkBtn, currentShare));

const qrToggle = $<HTMLButtonElement>("#qrToggle");
qrToggle.addEventListener("click", () => {
  const show = qrEl.hidden;
  qrEl.hidden = !show;
  qrToggle.textContent = show ? "Hide QR" : "QR code";
  qrToggle.setAttribute("aria-expanded", String(show));
});

const pasteToggle = $<HTMLButtonElement>("#pasteToggle");
pasteToggle.addEventListener("click", () => {
  const show = tokenEl.hidden;
  tokenEl.hidden = !show;
  pasteToggle.textContent = show ? "Hide token" : "View token";
  pasteToggle.setAttribute("aria-expanded", String(show));
  if (show) tokenEl.focus();
});

$("#heroPaste").addEventListener("click", () => {
  tokenEl.hidden = false;
  pasteToggle.textContent = "Hide token";
  pasteToggle.setAttribute("aria-expanded", "true");
  document.querySelector("#playground")?.scrollIntoView({ behavior: "smooth", block: "start" });
  tokenEl.focus({ preventScroll: true });
  tokenEl.select();
});

window.addEventListener("hashchange", () => {
  if (suppressHash) return;
  try {
    const t = extractToken(location.href);
    lastSource = null;
    lastEncodeMs = null;
    setToken(t, false);
  } catch {
    /* ignore non-token hashes */
  }
});

// Boot: load a token from the URL fragment if present, else the default example.
(function boot() {
  try {
    const t = extractToken(location.href);
    setToken(t, false);
    return;
  } catch {
    /* no token in URL */
  }
  encodeAndShow(EXAMPLES[currentExample]!());
})();
