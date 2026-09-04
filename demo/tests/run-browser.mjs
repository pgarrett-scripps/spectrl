/** CI driver for the same test page used in a normal browser. */
import { chromium } from "playwright"
import { spawn } from "node:child_process"

const server = spawn("python3", ["-m", "http.server", "8769", "--bind", "127.0.0.1"], { stdio: "ignore" })
let browser
try {
  const deadline = Date.now() + 10000
  while (true) {
    try {
      if ((await fetch("http://127.0.0.1:8769/tests/browser.html")).ok) break
    } catch {}
    if (Date.now() > deadline) throw new Error("Demo test server did not start")
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  browser = await chromium.launch()
  const page = await browser.newPage()
  await page.goto("http://127.0.0.1:8769/tests/browser.html")
  await page.locator("#run").click()
  await page.locator('#result[data-status="passed"], #result[data-status="failed"]').waitFor({ timeout: 45000 })
  console.log(await page.locator("#result").innerText())
  if (await page.locator("#result").getAttribute("data-status") !== "passed") process.exitCode = 1
} finally {
  await browser?.close()
  server.kill()
}
