/** Shared browser assertions, runnable manually or through the CI driver. */
import { encodeSpectrum, decodeToken } from "../../js/src/index"

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
async function load(token?: string) {
  const loaded = new Promise(resolve => frame.addEventListener("load", resolve, { once: true }))
  frame.src = "../index.html?regression=" + Date.now() + (token ? "#" + token : "")
  await loaded
  await waitFor(() => Boolean(element<HTMLTextAreaElement>("#token")?.value))
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
const tests: [string, () => Promise<void>][] = [
  ["zstd loads on demand", async () => {
    const { installZstd } = await import("../../js/src/zstd")
    installZstd()
    await load(encodeSpectrum({ defaultArrayLength: 1, mz: [100], intensity: [10] }, { arrayEncodings: { mz: "zstd" } }))
    await waitFor(() => element("#tokenMeta").textContent!.includes("checksum verified"))
    assert(!element("#decodeErr").textContent, "Zstd token failed to render")
  }],
  ["metadata is rendered literally", async () => {
    const markup = '<img id="injected" src="missing" onerror="document.body.dataset.injected=1">'
    await load(encodeSpectrum({ defaultArrayLength: 1, mz: [100], intensity: [10], id: markup, interp: markup,
      params: [{ accession: "MS:1000511", value: markup }], extraArrays: { [markup]: [1] } }))
    assert(!frame.contentDocument!.querySelector("#injected"), "Metadata created an HTML element")
    assert(!frame.contentDocument!.body.dataset.injected, "Metadata executed a handler")
    assert(element("#metaTable").textContent!.includes(markup), "Metadata text was lost")
    assert(element("#spectrumSummary").textContent!.includes(markup), "Summary text was lost")
    assert(element("#stats").textContent!.includes(markup), "Custom-array label was lost")
  }],
  ["peak import and lossless mode preserve user data", async () => {
    await load()
    change("#peakInput", "mz,intensity\n200.123456,20\n100.123456,10")
    element("#importPeaks").click()
    assert(decodeToken(currentToken()).defaultArrayLength === 2, "Import failed")
    element<HTMLInputElement>("#lossless").checked = true
    element("#lossless").dispatchEvent(new Event("change", { bubbles: true }))
    assert(decodeToken(currentToken()).mz![0] === 100.123456, "Lossless mode replaced or rounded imported data")
    assert(element("#qualityReport").textContent!.includes('"allArraysExact": true'), "Quality report did not update")
    const previous = currentToken()
    change("#peakInput", "1,2,3")
    element("#importPeaks").click()
    assert(currentToken() === previous, "Invalid import replaced the current spectrum")
    assert(element("#importStatus").textContent!.includes("line 1"), "Missing useful import error")
  }],
  ["budget preview requires consent and apply", async () => {
    await load(encodeSpectrum({ defaultArrayLength: 300,
      mz: Array.from({ length: 300 }, (_, i) => 100 + i * 1.234567),
      intensity: Array.from({ length: 300 }, (_, i) => i + 1) }))
    const original = currentToken()
    change("#shareBudget", "220")
    element("#previewBudget").click()
    assert(element<HTMLButtonElement>("#applyBudget").disabled, "Trimming did not require opt-in")
    check("#allowTrim")
    element("#previewBudget").click()
    assert(!element<HTMLButtonElement>("#applyBudget").disabled, "No fitting candidate")
    assert(currentToken() === original, "Preview changed the displayed spectrum")
    element("#applyBudget").click()
    assert(currentToken() !== original, "Apply did not replace the token")
    assert(decodeToken(currentToken()).defaultArrayLength < 300, "Apply did not trim")
    assert(element("#budgetStatus").textContent!.includes("Applied"), "Missing removal report")
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
