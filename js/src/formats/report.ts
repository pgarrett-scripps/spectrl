/** What a conversion could not represent, reported rather than discarded.
 *
 * A token carries more spectrum-level structure than any text format it can be
 * written to, so every export except mzML drops something. The contract is that
 * a conversion never silently invents or discards semantics: each writer returns
 * what it wrote together with what it could not, mirroring the Python
 * ConversionResult so both implementations report the same omissions. */

export type Severity = "warning" | "info"

export interface ConversionIssue {
  code: string
  path: string
  message: string
  severity: Severity
}

export class ConversionResult {
  text = ""
  readonly format: string
  readonly issues: ConversionIssue[] = []

  constructor(format: string, text = "") {
    this.format = format
    this.text = text
  }

  add(code: string, path: string, message: string, severity: Severity = "warning"): void {
    this.issues.push({ code, path, message, severity })
  }

  /** Messages for information the output does not carry. */
  get omitted(): string[] {
    return this.issues.filter(i => i.severity === "warning").map(i => i.message)
  }

  /** True when nothing present in the token was left out. */
  get lossless(): boolean {
    return this.omitted.length === 0
  }

  /** A short report, empty when nothing was dropped. */
  summary(): string {
    const dropped = this.omitted
    if (!dropped.length) return ""
    return [`Not represented by ${this.format.toUpperCase()}:`, ...dropped.map(m => `  - ${m}`)].join("\n")
  }
}
