/** Shared browser assertions, runnable manually or through the CI driver. */
import { encodeSpectrum, decodeToken, tokenBreakdown } from "../../js/src/index"

import { installBrotli } from "../../js/src/brotli"

const frame = document.querySelector<HTMLIFrameElement>("#viewer")!
const result = document.querySelector<HTMLElement>("#result")!
const assert = (condition: unknown, message: string) => { if (!condition) throw new Error(message) }
const element = <T extends HTMLElement>(id: string) => frame.contentDocument!.querySelector<T>(id)!
const waitFor = async (predicate: () => boolean) => {
  const deadline = Date.now() + 10000
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("Timed out waiting for the demo")
    await new Promise(resolve => setTimeout(resolve, 25))
  }
}
async function load(token?: string, carrier: "fragment" | "query" | "encoded-fragment" = "fragment") {
  const loaded = new Promise(resolve => frame.addEventListener("load", resolve, { once: true }))
  const suffix = !token ? "" : carrier === "query" ? "&d=" + encodeURIComponent(token)
    : "#" + (carrier === "encoded-fragment" ? encodeURIComponent(token).replaceAll(".", "%2E") : token)
  frame.src = "../index.html?regression=" + Date.now() + suffix
  await loaded
  await waitFor(() => Boolean(element<HTMLTextAreaElement>("#token")?.value))
}
/** The converter lives on its own page: it is a tool, not part of the pitch. */
async function loadConverter() {
  const loaded = new Promise(resolve => frame.addEventListener("load", resolve, { once: true }))
  frame.src = "../convert.html?regression=" + Date.now()
  await loaded
  await waitFor(() => Boolean(element("#convertFile")))
}
function change(id: string, value: string) {
  element<HTMLInputElement>(id).value = value
  element(id).dispatchEvent(new Event("input", { bubbles: true }))
}
function check(id: string) {
  element<HTMLInputElement>(id).checked = true
  element(id).dispatchEvent(new Event("input", { bubbles: true }))
}
const currentToken = () => element<HTMLTextAreaElement>("#token").value
/** The converter's token box, which is a separate page from the demo's. */
const convertedToken = () => element<HTMLTextAreaElement>("#tokenInput").value
const tests: [string, () => Promise<void>][] = [
  ["unsupported shared links preserve their token and never display an example", async () => {
    for (const token of ["spectrl1.saved-token", "spectrl.v2.saved-token", "spectrl.v99.saved-token"]) {
      for (const carrier of ["fragment", "query", "encoded-fragment"] as const) {
        await load(token, carrier)
        const originalUrl = frame.src
        assert(currentToken() === token, "Unsupported input was replaced")
        assert(frame.contentWindow!.location.href === originalUrl, "Original URL was rewritten")
        assert(element("#decodeErr").textContent!.includes("Unsupported spectrum token version"), "Missing version error")
        assert(!element("#plot").querySelector("svg"), "An unrelated spectrum was plotted")
        assert(!element("#tokenMeta").textContent!.includes("checksum verified"), "Invalid input shown as verified")
      }
    }
  }],
  ["invalid URL changes clear the old spectrum and recover on valid input", async () => {
    const valid = encodeSpectrum({ defaultArrayLength: 2, mz: [100, 200], intensity: [1, 2] })
    await load(valid)
    assert(Boolean(element("#plot").querySelector("svg")), "Valid spectrum was not plotted")
    for (const invalid of ["spectrl.v2.saved-token", "spectrl.v3.z.broken.00000000"]) {
      frame.contentWindow!.location.hash = invalid
      await waitFor(() => currentToken() === invalid && Boolean(element("#decodeErr").textContent))
      assert(!element("#plot").querySelector("svg"), "Invalid input retained the previous spectrum")
      assert(!element("#stats").textContent, "Stale statistics remain")
      assert(!element("#plotNote").textContent, "Stale plot note remains")
    }
    frame.contentWindow!.location.hash = valid
    await waitFor(() => currentToken() === valid && element("#tokenMeta").textContent!.includes("checksum verified"))
    assert(!element("#decodeErr").textContent, "Error was not cleared after a valid link")
  }],
  ["current tokens load through query and encoded fragments", async () => {
    const token = encodeSpectrum({ defaultArrayLength: 1, mz: [123], intensity: [42] }, { lossless: true })
    for (const carrier of ["query", "encoded-fragment"] as const) {
      await load(token, carrier)
      assert(currentToken() === token, "Current token was replaced")
      assert(!element("#decodeErr").textContent, "Valid current link did not decode")
    }
  }],
  ["Brotli browser backend round trips a quantized token", async () => {
    await installBrotli()
    const token = encodeSpectrum({ defaultArrayLength: 2, mz: [100, 200], intensity: [10, 20] }, { compression: "brotli" })
    assert(token.startsWith("spectrl.v3.b."), "Brotli mode missing")
    const decoded = decodeToken(token)
    assert(Math.abs(decoded.mz![0]! - 100) <= 100 * 1e-7 && Math.abs(decoded.intensity![1]! - 20) < 0.01, "Brotli round trip failed")
    await load(token)
    await waitFor(() => element("#tokenMeta").textContent!.includes("checksum verified"))
    assert(!element("#decodeErr").textContent, "Viewer failed to initialize Brotli")
  }],
  ["raw and compressed payloads preserve metadata in the browser", async () => {
    const raw = encodeSpectrum({ defaultArrayLength: 0 }, { compression: "raw" })
    assert(raw.startsWith("spectrl.v3.r."), "Explicit raw token has the wrong mode")
    assert(decodeToken(raw).defaultArrayLength === 0, "Raw token did not decode")
    const id = "context-record-".repeat(100)
    const compressed = encodeSpectrum({ defaultArrayLength: 2, id, mz: [100, 200], intensity: [1, 2] })
    assert(compressed.startsWith("spectrl.v3.z."), "Metadata-rich token did not choose zlib mode")
    assert(decodeToken(compressed).id === id, "Compressed metadata changed")
    await load(compressed)
    await waitFor(() => element("#tokenMeta").textContent!.includes("checksum verified"))
    assert(!element("#decodeErr").textContent, "Compressed token failed to render")
  }],
  ["decoder budgets reject excessive array data", async () => {
    const token = encodeSpectrum({ defaultArrayLength: 2, mz: [100, 200], intensity: [1, 2] })
    assert(decodeToken(token, { maxDecodedBytes: 32 }).defaultArrayLength === 2, "Exact budget was rejected")
    let rejected = false
    try {
      decodeToken(token, { maxDecodedBytes: 31 })
    } catch (error) {
      rejected = error instanceof Error && error.message.includes("maxDecodedBytes")
    }
    assert(rejected, "Aggregate byte budget was ignored")
  }],
  ["metadata is rendered literally", async () => {
    const markup = '<img id="injected" src="missing" onerror="document.body.dataset.injected=1">'
    await load(encodeSpectrum({ defaultArrayLength: 1, mz: [100], intensity: [10], id: markup,
      params: [{ accession: "MS:1000511", value: markup }], extraArrays: { [markup]: [1] } }))
    assert(!frame.contentDocument!.querySelector("#injected"), "Metadata created an HTML element")
    assert(!frame.contentDocument!.body.dataset.injected, "Metadata executed a handler")
    assert(element("#metaTable").textContent!.includes(markup), "Metadata text was lost")
    assert(!element("#spectrumSummary").textContent!.includes(markup), "Unmodeled text entered the summary")
    assert(element("#stats").textContent!.includes(markup), "Custom-array label was lost")
  }],
  ["pasted peaks encode, and bad input does not replace a good token", async () => {
    await loadConverter()
    change("#peakInput", "mz,intensity\n200.123456,20\n100.123456,10")
    element("#importPeaks").click()
    await waitFor(() => Boolean(convertedToken()))
    assert(decodeToken(convertedToken()).defaultArrayLength === 2, "Import failed")
    const previous = convertedToken()
    change("#peakInput", "1,2,3")
    element("#importPeaks").click()
    assert(convertedToken() === previous, "Invalid import replaced the current token")
    assert(element("#convertStatus").textContent!.includes("line 1"), "Missing useful import error")
  }],
  ["lossless mode uses the fixed core policy", async () => {
    await loadConverter()
    const mz = Array.from({ length: 256 }, (_, i) => 100 + i / 8)
    change("#peakInput", mz.map((value, i) => `${value},${i * i}`).join("\n"))
    check("#lossless")
    element("#importPeaks").click()
    await waitFor(() => Boolean(convertedToken()))
    assert(tokenBreakdown(convertedToken()).some(part => part.encoding?.[0] === 2), "Lossless core policy not used")
    const decoded = decodeToken(convertedToken())
    assert(decoded.mz!.every((value, i) => value === mz[i]), "Lossless encoding changed m/z values")
    assert(decoded.intensity!.every((value, i) => value === i * i), "Lossless encoding changed intensities")

  }],
  ["the quality report reflects the lossless toggle", async () => {
    await load()
    element<HTMLInputElement>("#lossless").checked = true
    element("#lossless").dispatchEvent(new Event("change", { bubbles: true }))
    await waitFor(() => element("#qualityReport").textContent!.includes('"allArraysExact"'))
    assert(element("#qualityReport").textContent!.includes('"allArraysExact": true'),
      "Quality report did not report an exact encoding")
  }],
  // The example files on the Convert page are written by the library's own
  // writers, so the converter must read every spectrum in each of them back.
  ["the downloadable example files load in the converter", async () => {
    for (const [name, rows, mime] of [["example.mzML", 3, "application/xml"], ["example.mgf", 2, "text/plain"], ["example.ms2", 2, "text/plain"]] as const) {
      await loadConverter()
      const text = await (await fetch("../examples/" + name)).text()
      const transfer = new DataTransfer()
      transfer.items.add(new File([text], name, { type: mime }))
      const input = element<HTMLInputElement>("#convertFile")
      input.files = transfer.files
      input.dispatchEvent(new Event("change", { bubbles: true }))
      await waitFor(() => !element("#spectrumList").hidden)
      const listed = frame.contentDocument!.querySelectorAll("#spectrumRows tr")
      assert(listed.length === rows, `${name}: expected ${rows} spectra, got ${listed.length}`)
      ;(listed[listed.length - 1] as HTMLElement).click()
      await waitFor(() => Boolean(convertedToken()))
      const decoded = decodeToken(convertedToken())
      assert(decoded.defaultArrayLength === 18, `${name}: LVNELTEFAK should have 18 peaks, got ${decoded.defaultArrayLength}`)
      assert(decoded.id?.includes("1043"), `${name}: lost the scan number: ${decoded.id}`)
    }
  }],
  // The converter is the only place the mzML reader runs, because it needs a
  // DOMParser that Node does not have.
  ["a spectrum file becomes a token and comes back as a file", async () => {
    await load(encodeSpectrum({
      defaultArrayLength: 3,
      mz: [100.5, 200.25, 300.125],
      intensity: [10, 20.5, 30],
      id: "scan=7",
      params: [{ accession: "MS:1000511", value: 2 }],
      precursors: [{ selectedIons: [{ params: [{ accession: "MS:1000744", value: 445.25 }] }] }],
    }, { lossless: true }))
    const original = currentToken()

    // Write the displayed spectrum as mzML, using the same code the download
    // button calls, then feed it back through the converter's file input.
    const { write, listSpectra, readText } = await import("../../js/src/formats/index")
    const mzml = write(decodeToken(original), "mzml")
    assert(mzml.lossless, "mzML export should not drop anything: " + mzml.omitted.join("; "))

    const summaries = listSpectra(mzml.text, "mzml")
    assert(summaries.length === 1, `Expected one spectrum, got ${summaries.length}`)
    assert(summaries[0]!.id === "scan=7", "Lost the spectrum id: " + summaries[0]!.id)
    assert(summaries[0]!.peaks === 3, "Wrong peak count: " + summaries[0]!.peaks)
    assert(summaries[0]!.msLevel === 2, "Wrong MS level: " + summaries[0]!.msLevel)
    assert(Math.abs(summaries[0]!.precursorMz! - 445.25) < 1e-9, "Lost the precursor")

    const [reread] = readText(mzml.text, "mzml", { index: 0 })
    const back = decodeToken(encodeSpectrum(reread!, { lossless: true }))
    const first = decodeToken(original)
    assert(back.defaultArrayLength === first.defaultArrayLength, "Peak count changed on the round trip")
    for (let i = 0; i < first.mz!.length; i++) {
      assert(back.mz![i] === first.mz![i], `m/z ${i} changed: ${first.mz![i]} -> ${back.mz![i]}`)
      assert(back.intensity![i] === first.intensity![i], `intensity ${i} changed`)
    }
    assert(back.id === "scan=7", "Lost the id through mzML: " + back.id)

    // MGF holds far less, and has to say so rather than pretend otherwise.
    const mgf = write(first, "mgf")
    assert(mgf.text.includes("PEPMASS=445.25"), "MGF lost the precursor")
    assert(readText(mgf.text, "mgf").length === 1, "MGF did not re-read")
  }],
  ["the converter loads a file the page never uploads", async () => {
    await loadConverter()
    const { write } = await import("../../js/src/formats/index")
    const mzml = write(decodeToken(encodeSpectrum({ defaultArrayLength: 3, mz: [100, 200, 300],
      intensity: [1, 2, 3], id: "scan=11", params: [{ accession: "MS:1000511", value: 2 }] },
      { lossless: true })), "mzml")
    const transfer = new DataTransfer()
    transfer.items.add(new File([mzml.text], "demo.mzML", { type: "application/xml" }))
    const input = element<HTMLInputElement>("#convertFile")
    input.files = transfer.files
    input.dispatchEvent(new Event("change", { bubbles: true }))
    await waitFor(() => !element("#spectrumList").hidden)
    const rows = frame.contentDocument!.querySelectorAll("#spectrumRows tr")
    assert(rows.length === 1, `Expected one spectrum row, got ${rows.length}`)
    assert(rows[0]!.textContent!.includes("scan=11"), "Row did not show the spectrum id")
    ;(rows[0] as HTMLElement).click()
    await waitFor(() => Boolean(convertedToken()))
    const decoded = decodeToken(convertedToken())
    assert(decoded.defaultArrayLength === 3, "Loading the converted file changed the peak count")
    assert(decoded.id === "scan=11", "Lost the spectrum id through the converter")
    assert(element("#tokenStatus").textContent!.includes("Encoded"), "Missing load confirmation")
  }],
]
document.querySelector<HTMLButtonElement>("#run")!.addEventListener("click", async event => {
  const button = event.currentTarget as HTMLButtonElement
  button.disabled = true
  result.dataset.status = "running"
  const messages: string[] = []
  try {
    for (const [name, run] of tests) {
      await run()
      messages.push("PASS " + name)
      result.textContent = messages.join("\n")
    }
    result.dataset.status = "passed"
  } catch (error) {
    result.textContent = [...messages, "FAIL " + (error as Error).message].join("\n")
    result.dataset.status = "failed"
  } finally { button.disabled = false }
})
