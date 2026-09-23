/** The converter page: a file becomes a token, a token becomes a file.
 *
 * Deliberately not the demo. The demo's job is to show that one string holds a
 * whole spectrum; this page's job is to move data across a boundary, so it has
 * no hero, no examples and nothing behind a disclosure. Both directions are on
 * screen at once because a converter that only shows you one of them makes you
 * guess which way you are going.
 *
 * Spectra are listed as rows rather than a dropdown. A run holds thousands, and
 * a dropdown hides all but one of them behind a click while showing no context. */

import {
  decodeToken,
  encodeSpectrum,
  formatForPath,
  formatPeakList,
  parsePeakList,
  listSpectra,
  readText,
  write,
  type SpectrumFormat,
  type SpectrumSummary,
} from "../../js/dist/index.js"

const $ = <T extends Element = HTMLElement>(selector: string) => document.querySelector(selector) as T

const fileInput = $<HTMLInputElement>("#convertFile")
const statusEl = $("#convertStatus")
const listEl = $("#spectrumList")
const rowsEl = $<HTMLTableSectionElement>("#spectrumRows")
const filterEl = $<HTMLInputElement>("#spectrumFilter")
const tokenEl = $<HTMLTextAreaElement>("#tokenInput")
const tokenStatus = $("#tokenStatus")
const lossEl = $("#conversionLoss")
const losslessEl = $<HTMLInputElement>("#lossless")
const viewLink = $<HTMLAnchorElement>("#viewInDemo")

// A browser is the wrong tool past this size; the CLI selects a spectrum
// without holding the file in memory.
const MAX_BYTES = 64 * 1024 * 1024

let opened: { name: string, text: string, format: SpectrumFormat, summaries: SpectrumSummary[] } | null = null

function describe(summary: SpectrumSummary): string {
  const parts: string[] = []
  if (summary.msLevel != null) parts.push(`MS${summary.msLevel}`)
  if (summary.precursorMz != null) parts.push(`precursor ${summary.precursorMz.toFixed(4)}`)
  if (summary.retentionSeconds != null) parts.push(`${(summary.retentionSeconds / 60).toFixed(2)} min`)
  parts.push(`${summary.peaks} peaks`)
  return parts.join(" · ")
}

/** The part of every id that is the same, so the rows can show only the part
 * that differs. Native ids in a run look like
 * "controllerType=0 controllerNumber=1 scan=1842", where everything before the
 * scan number is shared; truncating those to fit a column hides the one field
 * that tells them apart. */
function commonPrefix(ids: string[]): string {
  if (ids.length < 2) return ""
  let prefix = ids[0]!
  for (const id of ids) {
    let i = 0
    while (i < prefix.length && i < id.length && prefix[i] === id[i]) i++
    prefix = prefix.slice(0, i)
    if (!prefix) return ""
  }
  // Only worth stripping if it removes real noise and leaves something behind.
  const shortest = Math.min(...ids.map(id => id.length))
  return prefix.length >= 8 && prefix.length < shortest ? prefix : ""
}

function renderRows(): void {
  if (!opened) return
  const needle = filterEl.value.trim().toLowerCase()
  const matches = opened.summaries.filter(s =>
    !needle || s.id.toLowerCase().includes(needle) || describe(s).toLowerCase().includes(needle))
  rowsEl.replaceChildren()
  const prefix = commonPrefix(opened.summaries.map(s => s.id))
  const noteEl = $("#idPrefix")
  if (prefix) {
    noteEl.innerHTML = "Every id starts with <code></code>, so the rows show the rest."
    noteEl.querySelector("code")!.textContent = prefix
    noteEl.hidden = false
  } else {
    noteEl.hidden = true
  }
  // A run can hold tens of thousands of spectra; rendering every row would
  // stall the page, so the list shows a window and says what it is hiding.
  const shown = matches.slice(0, 300)
  for (const summary of shown) {
    const row = document.createElement("tr")
    row.tabIndex = 0
    row.innerHTML = `<td class="id"></td><td class="about"></td><td class="go">Load →</td>`
    const idCell = row.querySelector<HTMLElement>(".id")!
    idCell.textContent = prefix ? summary.id.slice(prefix.length) : summary.id
    idCell.title = summary.id  // the full id stays reachable on hover
    row.querySelector<HTMLElement>(".about")!.textContent = describe(summary)
    const load = () => loadSpectrum(summary)
    row.addEventListener("click", load)
    row.addEventListener("keydown", event => {
      if ((event as KeyboardEvent).key === "Enter") load()
    })
    rowsEl.append(row)
  }
  const hidden = matches.length - shown.length
  statusEl.textContent = needle
    ? `${matches.length} of ${opened.summaries.length} spectra match${hidden > 0 ? `, showing the first ${shown.length}` : ""}.`
    : `${opened.summaries.length} spectra in ${opened.name}${hidden > 0 ? `, showing the first ${shown.length}` : ""}. Choose one.`
}

function loadSpectrum(summary: SpectrumSummary): void {
  if (!opened) return
  try {
    const [spectrum] = readText(opened.text, opened.format, { index: summary.index })
    if (!spectrum) throw Error("that spectrum could not be read")
    const token = encodeSpectrum(spectrum, { lossless: losslessEl.checked, quiet: true })
    tokenEl.value = token
    showToken(`Encoded ${summary.id} · ${describe(summary)} · ${token.length} characters.`)
    for (const row of rowsEl.querySelectorAll("tr")) row.classList.remove("chosen")
    const index = opened.summaries.indexOf(summary)
    void index
    rowsEl.querySelectorAll("tr").forEach(row => {
      if (row.querySelector(".id")?.textContent === summary.id) row.classList.add("chosen")
    })
  } catch (error) {
    statusEl.textContent = (error as Error).message
  }
}

function showToken(message: string): void {
  tokenStatus.textContent = message
  lossEl.textContent = ""
  viewLink.href = tokenEl.value ? `./index.html#${tokenEl.value}` : "./index.html"
}

fileInput.addEventListener("change", async event => {
  const file = (event.target as HTMLInputElement).files?.[0]
  opened = null
  listEl.hidden = true
  if (!file) return
  if (file.size > MAX_BYTES) {
    statusEl.textContent = `${file.name} is ${(file.size / 1024 / 1024).toFixed(0)} MiB. A browser is the wrong tool for a run this large: the spectrl command line selects one spectrum without holding the file in memory.`
    return
  }
  statusEl.textContent = `Reading ${file.name}…`
  try {
    const format = formatForPath(file.name)
    const text = await file.text()
    const summaries = listSpectra(text, format)
    if (!summaries.length) throw Error(`${file.name} contains no spectra`)
    opened = { name: file.name, text, format, summaries }
    filterEl.value = ""
    listEl.hidden = false
    renderRows()
  } catch (error) {
    statusEl.textContent = (error as Error).message
  }
})

filterEl.addEventListener("input", renderRows)

$("#importPeaks").addEventListener("click", () => {
  try {
    const spectrum = parsePeakList($<HTMLTextAreaElement>("#peakInput").value)
    const token = encodeSpectrum(spectrum, { lossless: losslessEl.checked, quiet: true })
    tokenEl.value = token
    showToken(`Encoded ${spectrum.defaultArrayLength} pasted peaks · ${token.length} characters. No metadata was inferred.`)
  } catch (error) {
    statusEl.textContent = (error as Error).message
  }
})

losslessEl.addEventListener("change", () => {
  // The choice only applies to the next encode, so say so rather than silently
  // leaving a token on screen that was made under the other setting.
  if (tokenEl.value) tokenStatus.textContent = "Encoding mode changed. Load a spectrum again to apply it."
})

tokenEl.addEventListener("input", () => {
  const token = tokenEl.value.trim()
  if (!token) {
    showToken("No token loaded.")
    return
  }
  try {
    const decoded = decodeToken(token)
    const level = decoded.params?.find(p => p.accession === "MS:1000511")?.value
    const parts = [`${decoded.defaultArrayLength} peaks`]
    if (level != null) parts.unshift(`MS${level}`)
    if (decoded.id) parts.unshift(decoded.id)
    showToken(`Valid token · ${parts.join(" · ")}.`)
  } catch (error) {
    tokenStatus.textContent = (error as Error).message
    lossEl.textContent = ""
  }
})

function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const link = document.createElement("a")
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function baseName(id: string | null): string {
  return (id || "spectrum").replace(/[^A-Za-z0-9_.-]+/g, "_")
}

function save(format: SpectrumFormat, suffix: string): void {
  lossEl.textContent = ""
  const token = tokenEl.value.trim()
  if (!token) {
    lossEl.textContent = "Paste a token first, or load one from a file."
    return
  }
  try {
    const decoded = decodeToken(token)
    const result = write(decoded, format)
    const name = `${baseName(decoded.id)}.${suffix}`
    download(name, result.text, "text/plain;charset=utf-8")
    if (result.lossless) {
      lossEl.innerHTML = `<p class="kept">Wrote <b>${name}</b>. Nothing the token holds was left out.</p>`
    } else {
      const items = result.omitted.map(m => `<li></li>`).join("")
      lossEl.innerHTML = `<p class="dropped">Wrote <b>${name}</b>. ${format.toUpperCase()} cannot represent:</p><ul>${items}</ul>`
      lossEl.querySelectorAll("li").forEach((li, i) => { li.textContent = result.omitted[i]! })
    }
  } catch (error) {
    lossEl.textContent = (error as Error).message
  }
}

$("#downloadMzml").addEventListener("click", () => save("mzml", "mzML"))
$("#downloadMgf").addEventListener("click", () => save("mgf", "mgf"))
$("#downloadMs2").addEventListener("click", () => save("ms2", "ms2"))
$("#downloadTsv").addEventListener("click", () => {
  lossEl.textContent = ""
  try {
    const decoded = decodeToken(tokenEl.value.trim())
    download(`${baseName(decoded.id)}.tsv`, formatPeakList(decoded), "text/tab-separated-values")
    lossEl.innerHTML = `<p class="dropped">Wrote peaks only. A TSV carries no metadata at all.</p>`
  } catch (error) {
    lossEl.textContent = (error as Error).message
  }
})

// A token in the fragment opens ready to save, which is what a link from the
// demo's "Convert a file" action should do.
const fragment = decodeURIComponent(location.hash.replace(/^#/, ""))
if (fragment.startsWith("spectrl.")) {
  tokenEl.value = fragment
  tokenEl.dispatchEvent(new Event("input"))
}
