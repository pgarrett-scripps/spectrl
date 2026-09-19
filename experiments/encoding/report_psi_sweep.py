"""Summarize the PSI mode sweep with separate array-family comparisons."""

import argparse
import json
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("experiments/encoding/psi-sweep.json"))
    parser.add_argument("--output", type=Path, default=Path("experiments/encoding/PSI_SWEEP.md"))
    args = parser.parse_args()
    result = json.loads(args.input.read_text())
    modes = result["modes"]
    policies = result["policies"]
    baseline = {row["array"]: row["bytes"] for row in modes if row["codec"] == "MS:1000574" and row["level"] == 6}
    groups = ("all", "mz", "intensity", "MS:1003006")
    lines = [
        "# PSI-MS compression mode sweep",
        "",
        "All 17 standalone array compression terms were exercised where their numeric domains permit.",
        "The 18th term, coordinate-grid encoding (`MS:1003826`), requires an external grid and",
        "spacing model that these standalone arrays do not contain. It is not a drop-in compressor.",
        "",
        f"The corpus contains {result['array_count']} arrays from {result['spectra']} spectra in 40 datasets:",
        "127 m/z arrays, 127 intensity arrays, and three mean inverse reduced ion-mobility arrays.",
        "All use float64 in spectrl's canonical lossless representation. No real charge arrays",
        "occur in this sample. Supplementary synthetic positive/signed charge checks are kept",
        "in `psi-synthetic-charge.json` and are excluded from every corpus total below.",
        "",
        "## Standalone lossless methods at default compressor levels",
        "",
        "Every entry compares the same arrays with raw zlib 6. Positive percentages mean smaller",
        "compressed payloads. Metadata, XML, token framing, and Base64 are excluded.",
        "",
        "| Method | Total bytes | Overall savings | m/z savings | Intensity savings | Mobility savings |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for codec, level, name in (
        ("MS:1000576", 0, "No compression"),
        ("MS:1000574", 6, "zlib 6"),
        ("MS:1003780", 3, "Zstandard 3"),
        ("MS:1003781", 3, "Byte-shuffled Zstandard 3"),
        ("MS:1003782", 3, "Dictionary-encoded Zstandard 3"),
        ("experimental:delta-shuffle-zlib", 6, "Experimental modular delta + shuffle + zlib 6"),
        ("experimental:delta-shuffle-zstd", 3, "Experimental modular delta + shuffle + Zstandard 3"),
    ):
        subset = {row["array"]: row for row in modes if row["codec"] == codec and row["level"] == level}
        savings = [f"{100 * (1 - subset[group]['bytes'] / baseline[group]):.2f}%" for group in groups]
        lines.append(f"| {name} | {subset['all']['bytes']:,} | " + " | ".join(savings) + " |")
    lines += [
        "",
        "## Per-array selection",
        "",
        "The general lossless PSI pool is no compression, zlib, Zstandard, byte-shuffled Zstandard,",
        "and dictionary-encoded Zstandard. Truncation with zero removed bits is equivalent to raw",
        "zlib. Numpress and floating-point predictors are not assumed lossless just because some",
        "arrays happen to round-trip exactly.",
        "",
        "Default levels mean zlib 6 and Zstandard 3. The tuned pool additionally searches zlib",
        "levels 1 and 9 and Zstandard levels 1, 9, and 19. This is a size search, not a speed recommendation.",
        "",
        "| Policy | Total bytes | Savings versus raw zlib 6 |",
        "| --- | ---: | ---: |",
    ]
    names = {
        "current_supported": "Current spectrl PSI selector",
        "psi_lossless_defaults": "PSI lossless selector including dictionary, default levels",
        "psi_defaults_plus_delta_zlib6": "Same pool plus proposed delta + shuffle + zlib 6",
        "psi_defaults_plus_delta": "Same pool plus modular delta with either compressor",
        "psi_lossless_tuned": "PSI lossless selector, tuned levels",
        "psi_tuned_plus_delta": "Tuned PSI pool plus modular delta",
        "psi_verified_exact_defaults": "All tested PSI modes, with exact-byte verification per array",
        "psi_verified_exact_defaults_plus_delta": "Verified-exact PSI pool plus modular delta",
    }
    for policy, name in names.items():
        row = policies[policy]["all"]
        lines.append(f"| {name} | {row['bytes']:,} | {row['saving_vs_zlib6_pct']:.2f}% |")
    lines += [
        "",
        "The last two rows use an exhaustive selector that verifies exact recovery. It admits a normally",
        "lossy codec only when this particular encoded array reconstructs the original bytes",
        "exactly. Using this approach would require encoding, decoding, and checking each candidate.",
        "It is not the production policy or evidence that those codecs are generally lossless.",
        "A future selector could nevertheless guarantee lossless output by verifying every",
        "candidate against the source bytes and retaining a conventional lossless fallback.",
        "",
        "## Marginal benefit of modular delta after adding dictionary",
        "",
        "| Comparison | Overall | m/z | Intensity | Mobility |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for before, after, name in (
        ("psi_lossless_defaults", "psi_defaults_plus_delta_zlib6", "Add proposed delta + zlib 6"),
        ("psi_lossless_defaults", "psi_defaults_plus_delta", "Add delta with either default compressor"),
        ("psi_lossless_tuned", "psi_tuned_plus_delta", "Add delta with tuned compressors"),
        (
            "psi_verified_exact_defaults",
            "psi_verified_exact_defaults_plus_delta",
            "Add delta to exact-recovery selector",
        ),
    ):
        savings = [
            f"{100 * (1 - policies[after][group]['bytes'] / policies[before][group]['bytes']):.2f}%" for group in groups
        ]
        lines.append(f"| {name} | " + " | ".join(savings) + " |")
    lines += [
        "",
        "## Why array types need separate results",
        "",
        "m/z arrays are ordered and can favor prediction. Intensity arrays have different",
        "structure and repeated values. Mobility arrays can contain a small repeated value set",
        "in an order determined by m/z. Charge is integer-valued and has its own codec eligibility.",
        "",
        "The table below shows codec choices for the default PSI lossless pool, including dictionary.",
        "",
        "| Array | Chosen codec | Arrays |",
        "| --- | --- | ---: |",
    ]
    for group in groups[1:]:
        for winner, count in policies["psi_lossless_defaults"][group]["winners"].items():
            lines.append(f"| {group} | {winner} | {count} |")
    lines += [
        "",
        "Separate profile and centroid summaries are also recorded in the JSON. Large profile",
        "spectra dominate byte-weighted totals. The three mobility arrays are too few to support",
        "broad claims about mobility instruments. The sample contains no real charge arrays or",
        "chromatogram time arrays, so those need dedicated datasets before choosing defaults.",
        "",
        "## All PSI terms and applicability",
        "",
        "| Accession | Name | Status |",
        "| --- | --- | --- |",
    ]
    for term in result["inventory"]:
        status = term.get("reason", term["status"])
        lines.append(f"| {term['accession']} | {term['name']} | {status} |")
    skipped = Counter(row["family"] for row in result["skipped"])
    lines += [
        "",
        "Numpress linear used fixed point 100,000. SLOF requested 3,600, clamped per array to avoid",
        "uint16 overflow. PIC was tried only for nonnegative whole numbers within uint32 range.",
        "Rejected domains were recorded rather than silently changing input values or precision.",
        f"Ineligible arrays by Numpress family: {dict(skipped)}.",
        "",
        "The three mzMLb codecs were tested with 0, 16, 29, and 36 low mantissa bits removed.",
        "Their predictors use the mzMLb reference equations and floating-point arithmetic.",
        "Numpress modes were tested without an outer compressor, with zlib 6, and with Zstandard 3.",
        "Smaller lossy output is not an improvement at equal accuracy. Per-array maximum absolute,",
        "relative, and peak-normalized errors and bit-change counts are recorded for every variant.",
        "",
        "## Reproduction and reference implementations",
        "",
        "```bash",
        "PYTHONPATH=src .venv/bin/python experiments/encoding/psi_codec_sweep.py \\",
        "  --manifest ../spectrl-paper/paper/analysis/data/corpus.json \\",
        "  --vocabulary /path/to/psi-ms.obo",
        ".venv/bin/python experiments/encoding/report_psi_sweep.py",
        "```",
        "",
        "- [Detailed mode, policy, error, timing, and provenance results](psi-sweep.json)",
        "- [PSI-MS vocabulary](https://github.com/HUPO-PSI/psi-ms-CV/blob/master/psi-ms.obo)",
        "- [Dictionary reference](https://github.com/mobiusklein/mzdata/blob/ebe2e9a8f3db8f11de8726aaa5a04920d00aa580/crates/mzdata-bindata/src/encodings.rs)",
        "- [mzMLb predictor reference](https://github.com/biospi/pwiz/blob/mzMLb/pwiz/data/msdata/IO.cpp)",
        "- [Numpress reference](https://github.com/ms-numpress/ms-numpress)",
        "",
        "The dictionary implementation stores sorted unsigned bit patterns and byte-shuffles the",
        "dictionary and index arrays separately. Its 16-byte header is included in every nonempty",
        "payload. Index widths follow the maintained mzdata reference, including the 256 and 65,536",
        "distinct-value boundaries. An independent scalar implementation checked the transformed",
        "bytes at the boundary cases. Signed zeros, NaN payloads, and arbitrary bit patterns were checked.",
        "",
        "This is a Python benchmark reproduction, not a conformance claim for all existing readers.",
        "Older C++ and Python reference versions disagree at certain dictionary index-width boundaries.",
        "Runtime figures are one-shot exploratory measurements and include Python predictor loops.",
        "They should not be used to rank optimized production implementations or browser performance.",
        "No new public codec or token format was enabled by this experiment.",
        "The full per-array variant rows are written to `/tmp/spectrl-psi-sweep-rows.json` by default.",
        "Use `--rows PATH` to save them elsewhere. The saved summary retains per-mode",
        "aggregates, per-array winning selections, rejected domains, and input provenance.",
    ]
    args.output.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
