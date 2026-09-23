/**
 * spectrl browser demo.
 *
 * Builds example spectra, encodes them live with the real @spectrl-ms/spectrl
 * codec, shows the shareable URL + QR, then decodes the token and renders a
 * stick plot, all in the browser, no network.
 */
import {
  encodeSpectrum,
  encodingReport,
  topN,
  decodeToken,
  toFragment,
  tokenBreakdown,
  mobilityArrays,
  type InlineSpectrum,
  type CvParam,
  type DecodedSpectrum,
} from "../../js/dist/index.js";
import { EXAMPLES } from "./examples.js";
// qrcode-generator is CommonJS. esbuild provides the default-import interop.
import qrcode from "qrcode-generator";



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
const $ = <T extends Element = HTMLElement>(sel: string) => document.querySelector(sel) as T
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
let lastReport: ReturnType<typeof encodingReport> | null = null
let currentShare = ""; // shareable URL for the current token. Copied on demand.

function baseUrl(): string {
  return location.origin + location.pathname;
}

// Recognize a supplied spectrum before checking its version. Unsupported links
// must never fall through to a different example or overwrite the original URL.
function tokenFromLocation(): string | null {
  const url = new URL(location.href)
  let fragment = url.hash.slice(1)
  try { fragment = decodeURIComponent(fragment) } catch { /* Keep malformed input visible. */ }
  return [fragment, ...url.searchParams.values()]
    .find(value => /^spectrl(?:\.|[0-9]+(?:\.|$))/.test(value)) ?? null
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
  lastReport = encodingReport(spec, { lossless: losslessEl.checked })
  const token = lastReport.token
  lastEncodeMs = performance.now() - t0;
  lastSource = spec;
  setToken(token);
}

let brotliBackendPromise: Promise<unknown> | null = null

async function renderFromToken(token: string) {
  token = token.trim();
  currentShare = toFragment(token, baseUrl());
  if (!qrEl.hidden) renderQr(currentShare)

  decodeErr.textContent = "";
  let decoded: DecodedSpectrum;
  let decodeMs: number;
  try {
    if (!token.startsWith("spectrl.v3.") && /^spectrl(?:\.|[0-9]+(?:\.|$))/.test(token)) {
      throw new Error("Unsupported spectrum token version. This viewer supports spectrl.v3. The supplied token has been preserved.")
    }
    const t0 = performance.now();
    decoded = decodeToken(token);
    decodeMs = performance.now() - t0;
  } catch (e) {
    if ((e as Error).message.includes("Brotli support is unavailable")) {
      brotliBackendPromise ??= import("../../js/dist/brotli.js").then(module => module.installBrotli())
      try {
        await brotliBackendPromise
        if (tokenEl.value.trim() !== token) return
        await renderFromToken(token)
        return
      } catch (loadError) {
        if (tokenEl.value.trim() !== token) return
        e = loadError
      }
    }
    decodeErr.textContent = `Decode failed: ${(e as Error).message}`
    $("#qualityReport").textContent = "A valid token and its original spectrum are needed to measure encoding error."
    $<HTMLButtonElement>("#exportReport").disabled = true
    plotEl.innerHTML = "";
    metaTable.innerHTML = "";
    statsEl.innerHTML = "";
    spectrumSummaryEl.innerHTML = "";
    $("#plotNote").textContent = "";
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
  const level = msLevel(d);
  if (level !== null) chips.push([`MS${level === 2 ? "²" : level === 3 ? "³" : level}`, "level"]);
  const precursorMz = d.precursors
    .flatMap((p) => p.selectedIons ?? [])
    .flatMap((ion) => ion.params)
    .find((p) => p.accession === "MS:1000744")?.value;
  if (precursorMz != null && Number.isFinite(Number(precursorMz))) chips.push([Number(precursorMz).toFixed(4), "precursor m/z"]);
  const charge = d.precursors
    .flatMap((p) => p.selectedIons ?? [])
    .flatMap((ion) => ion.params)
    .find((p) => p.accession === "MS:1000041")?.value;
  if (charge != null && Number.isFinite(Number(charge))) chips.push([`${charge}+`, "charge"]);
  const activation = d.precursors
    .flatMap((p) => p.activation?.params ?? [])
    .find((p) => p.accession === "MS:1000422" || p.accession === "MS:1000133");
  if (activation) chips.push([label(activation.accession).replace(" (beam-type CID)", ""), "activation"]);
  const mobilityCount = Object.keys(mobilityArrays(d)).length;
  if (mobilityCount) chips.push([`${mobilityCount}`, "ion mobility array(s)"]);
  const extraCount = Object.keys(d.extraArrays).length - mobilityCount;
  if (extraCount) chips.push([`${extraCount}`, "auxiliary arrays"]);
  chips.push([`${d.mz?.length ?? 0}`, "peaks"]);

  spectrumSummaryEl.replaceChildren(...chips.map(([value, name]) => {
    const chip = document.createElement("div")
    chip.className = "chip"
    const strong = document.createElement("b")
    strong.textContent = value
    const label = document.createElement("span")
    label.textContent = name
    chip.append(strong, label)
    return chip
  }))
}

function renderQr(url: string) {
  qrEl.innerHTML = "";
  try {
    if (url.length > 2953) throw new Error("URL exceeds QR capacity")
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
  const rows: HTMLTableRowElement[] = []
  const add = (key: string, value: string, accession = "") => {
    const row = document.createElement("tr")
    for (const text of [key, value, accession]) {
      const cell = document.createElement("td")
      cell.textContent = text
      row.append(cell)
    }
    rows.push(row)
  }
  if (d.id) add("native id", d.id)

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

  const details = (value: unknown, path: string) => {
    if (value == null || rows.length >= 500) return
    if (Array.isArray(value)) value.forEach((item, i) => details(item, `${path} ${i + 1}`))
    else if (typeof value === "object") {
      const object = value as Record<string, unknown>
      if (typeof object.accession === "string") add(`${path}: ${label(object.accession)}`, fmtVal(object as unknown as CvParam), object.accession)
      else for (const [key, child] of Object.entries(object)) details(child, `${path} ${key}`)
    } else add(path.trim(), String(value))
  }
  for (const key of ["source", "acquisition", "processing", "arrayParams", "arrayUserParams", "arrayProcessing", "userParams"] as const) details(d[key], key)
  d.scans.forEach((scan, i) => {
    details(scan.userParams, `scan ${i + 1} notes`)
    details(scan.windows, `scan ${i + 1} windows`)
    details(scan.source, `scan ${i + 1} source`)
    details(scan.acquisition, `scan ${i + 1} acquisition`)
  })
  metaTable.replaceChildren(...rows)
}

function fmtVal(p: CvParam): string {
  if (p.value === null || p.value === undefined) return "(flag)"
  const value = typeof p.value === "number" ? round(p.value, 5) : p.value
  return p.unitAccession ? `${value} ${label(p.unitAccession)}` : String(value)
}

function htmlText(value: unknown): string {
  const span = document.createElement("span")
  span.textContent = String(value)
  return span.innerHTML
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
  let rawBytes = (d.mz?.byteLength ?? 0) + (d.intensity?.byteLength ?? 0) + (d.charge?.byteLength ?? 0)
  for (const array of Object.values(d.extraArrays)) rawBytes += array.byteLength;
  const tokenOverRaw = token.length / Math.max(rawBytes, 1);
  cards.push(
    statCard(
      "complete token vs peak arrays",
      `${tokenOverRaw.toFixed(1)}×`,
      `${fmtBytes(rawBytes)} raw arrays. Token also includes metadata + framing`,
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

  $<HTMLButtonElement>("#exportReport").disabled = lastReport === null
  if (lastReport) {
    const mz = lastReport.arrays.find(a => a.key === "mz")
    const intensity = lastReport.arrays.find(a => a.key === "intensity")
    const metric = (value: number | null | undefined, scale = 1) => value == null ? "n/a" : (value * scale).toPrecision(4)
    cards.push(statCard("max m/z error", `${metric(mz?.maxErrorPpm)} ppm`, `${metric(mz?.maxAbsoluteError)} absolute`))
    cards.push(statCard("max intensity error", `${metric(intensity?.maxRelativeError, 100)}%`, "Zero reference values are reported separately"))
    $("#qualityReport").textContent = JSON.stringify({ ...lastReport, token: undefined }, null, 2)
  } else {
    $("#qualityReport").textContent = "The original spectrum is needed to measure encoding error. Select an example here, or encode a spectrum from a file on the Convert page."
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
      const color = Object.hasOwn(SEG_COLOR, s.label) ? SEG_COLOR[s.label] : "#8b97a6"
      return (
        `<div class="bar"><div>${htmlText(s.label)}</div>` +
        `<div class="track"><div class="fill" style="width:${pct}%;background:${color}"></div></div>` +
        `<div class="n">${fmtBytes(s.bytes)}</div></div>`
      );
    })
    .join("");
  cards.push(`<div class="stat wide"><div class="label">size breakdown (before outer compression)</div><div class="bars">${bars}</div></div>`);

  statsEl.innerHTML = cards.join("");
}

function msLevel(d: DecodedSpectrum): number | null {
  const p = d.params.find((x) => x.accession === "MS:1000511");
  return p?.value != null && Number.isFinite(Number(p.value)) ? Number(p.value) : null
}

function basePeakIndex(d: DecodedSpectrum): number {
  const inten = d.intensity;
  if (!inten || inten.length === 0) return -1;
  let bi = 0;
  for (let i = 1; i < inten.length; i++) if (inten[i]! > inten[bi]!) bi = i;
  return bi;
}


/** Mode of the token actually displayed (a pasted token may differ from the checkbox). */
function tokenMode(token: string): string {
  try {
    const lossy = tokenBreakdown(token).some((p) => p.fidelity === "lossy");
    return lossy ? "lossy encoding" : "lossless encoding"
  } catch {
    return "unknown";
  }
}

// ---------------------------------------------------------------------------
// SVG stick plot
// ---------------------------------------------------------------------------
function renderPlot(d: DecodedSpectrum) {
  const plotted = d.defaultArrayLength > 5000 && d.intensity ? topN({ ...d, extensions: {}, arrayExtensions: {} }, 5000) : d
  const mz = Array.from(plotted.mz ?? []).slice(0, 5000)
  const inten = Array.from(plotted.intensity ?? []).slice(0, 5000)
  $("#plotNote").textContent = d.defaultArrayLength > 5000 ? "Plot shows at most 5,000 peaks. The token and exported data retain all peaks." : ""
  if (mz.length === 0 || inten.length === 0) {
    plotEl.innerHTML = `<div class="meta">Both m/z and intensity arrays are needed to plot this token.</div>`
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

losslessEl.addEventListener("change", async () => {
  try {
    const source = lastSource ?? decodeToken(tokenEl.value)
    const initialToken = tokenEl.value
    if (tokenEl.value !== initialToken) return
    encodeAndShow(source)
  } catch (error) { decodeErr.textContent = (error as Error).message }
})

tokenEl.addEventListener("input", () => {
  lastReport = null
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
  if (show) renderQr(currentShare)
  qrToggle.textContent = show ? "Hide QR" : "QR code";
  qrToggle.setAttribute("aria-expanded", String(show));
});

$<HTMLButtonElement>("#copyToken").addEventListener("click", async event => {
  await flashCopy(event.currentTarget as HTMLButtonElement, tokenEl.value);
});

window.addEventListener("hashchange", () => {
  if (suppressHash) return;
  const t = tokenFromLocation()
  if (t !== null) {
    lastReport = null
    lastSource = null;
    lastEncodeMs = null;
    setToken(t, false);
  }
});

function download(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement("a")
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
$("#exportReport").addEventListener("click", () => {
  if (lastReport) download("encoding-report.json", JSON.stringify(lastReport, null, 2), "application/json")
})

// Boot: load a token from the URL fragment if present, else the default example.
function boot() {
  const t = tokenFromLocation()
  if (t !== null) {
    setToken(t, false);
    return;
  }
  encodeAndShow(EXAMPLES[currentExample]!());
}
boot()
