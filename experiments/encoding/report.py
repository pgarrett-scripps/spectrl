"""Render benchmark summaries and an optional figure from results.json."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def table(rows, columns):
    lines = ["| " + " | ".join(label for label, _ in columns) + " |"]
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(value(row)) for _, value in columns) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("experiments/encoding/results.json"))
    parser.add_argument("--plot", action="store_true", help="Requires matplotlib")
    parser.add_argument("--rows", type=Path, help="Include error summaries from detailed benchmark rows")
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    output = args.input.parent
    lines = [
        "# Encoding benchmark measurements",
        "",
        f"{data['spectra']} spectra from {len(data['provenance'])} datasets. "
        f"{data['pipeline_rows']:,} array pipeline comparisons.",
        "",
        "Positive savings mean smaller output. Total savings weight by baseline bytes. "
        "Median savings weight each spectrum or array equally. "
        "Timing totals sum the per-input median wall times and are in milliseconds.",
        "",
        "## Complete tokens using the existing API",
        "",
        "Adaptive includes candidate search and final re-encoding. Static policies time the normal public encoder. "
        "All metadata, descriptors, base64url expansion, and checksums are included in token sizes.",
        "",
        table(
            data["token_summary"],
            [
                ("Mode", lambda r: r["mode"]),
                ("Policy", lambda r: r["policy"]),
                ("N", lambda r: r["n"]),
                ("Total savings", lambda r: f"{r['saving_pct']:.2f}%"),
                ("Median savings", lambda r: f"{r['median_saving_pct']:.2f}%"),
                ("Worst growth", lambda r: f"{r['worst_growth_pct']:.2f}%"),
                ("Wins", lambda r: r["wins"]),
                ("Encode ms", lambda r: f"{r['encode_us_total'] / 1000:.1f}"),
                ("Decode ms", lambda r: f"{r['decode_us_total'] / 1000:.1f}"),
            ],
        ),
    ]
    for mode in ("lossless", "lossy"):
        rows = sorted(
            (r for r in data["pipeline_summary"] if r["mode"] == mode),
            key=lambda r: r["saving_pct"],
            reverse=True,
        )
        lines += [
            "",
            f"## {mode.title()} array payloads",
            "",
            "These sizes exclude descriptors and token framing. Each row uses its own eligible input subset "
            "and matching baseline, so check N when comparing transforms. "
            "Float32 variants and custom delta/XOR pipelines are experiments, not new spectrl codec identifiers.",
            "",
            table(
                rows,
                [
                    ("Transform", lambda r: r["transform"]),
                    ("Compressor", lambda r: r["compressor"]),
                    ("N", lambda r: r["n"]),
                    ("Total savings", lambda r: f"{r['saving_pct']:.2f}%"),
                    ("Median savings", lambda r: f"{r['median_saving_pct']:.2f}%"),
                    ("Encode ms", lambda r: f"{r['encode_us_total'] / 1000:.1f}"),
                    ("Decode ms", lambda r: f"{r['decode_us_total'] / 1000:.1f}"),
                ],
            ),
        ]
    skips = [r for r in data["token_rows"] if "skip" in r]
    if args.rows:
        detailed = json.loads(args.rows.read_text())["pipelines"]
        unique = {(r["dataset"], r["id"], r["array"], r["mode"], r["transform"]): r for r in detailed}
        groups = defaultdict(list)
        for row in unique.values():
            groups[row["mode"], row["transform"], row["array"]].append(row)
        errors = []
        for (mode, transform, array), group in sorted(groups.items()):
            errors.append(
                {
                    "mode": mode,
                    "transform": transform,
                    "array": array,
                    "n": len(group),
                    "arrays_with_zero_numeric_error": sum(r["error"]["max_abs"] == 0 for r in group),
                    **{key: max(r["error"][key] for r in group) for key in group[0]["error"]},
                }
            )
        (output / "array-errors.json").write_text(json.dumps(errors, indent=2) + "\n")
        lines += [
            "",
            "## Lossy array reconstruction error",
            "",
            "Maximum observed error across arrays. Exact counts mean zero numeric error. "
            "Lossless transforms also passed separate byte equality checks.",
            "",
            table(
                [r for r in errors if r["mode"] == "lossy"],
                [
                    ("Transform", lambda r: r["transform"]),
                    ("Array", lambda r: r["array"]),
                    ("N", lambda r: r["n"]),
                    ("Exact arrays", lambda r: r["arrays_with_zero_numeric_error"]),
                    ("Absolute", lambda r: f"{r['max_abs']:.6g}"),
                    ("Relative", lambda r: f"{r['max_relative']:.6g}"),
                    ("Peak normalized", lambda r: f"{r['max_peak_normalized']:.6g}"),
                ],
            ),
        ]
    lines += ["", "## Rejected precision overrides", "", f"{len(skips)} rejected cases.", ""]
    for row in skips:
        lines.append(f"- {row['dataset']}, {row['id']}, {row['policy']}: {row['skip']}")
    lines += ["", "## Environment", "", "```json", json.dumps(data["environment"], indent=2), "```", ""]
    (output / "measurements.md").write_text("\n".join(lines))
    if args.plot:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), layout="constrained")
        for ax, mode in zip(axes, ("lossless", "lossy"), strict=True):
            rows = [r for r in data["token_summary"] if r["mode"] == mode and r["policy"] != "default"]
            for i, row in enumerate(rows):
                ax.barh(i - 0.17, row["saving_pct"], height=0.30, color="#286a9f", label="Total" if i == 0 else None)
                ax.barh(
                    i + 0.17,
                    row["median_saving_pct"],
                    height=0.30,
                    color="#74b5a1",
                    label="Median spectrum" if i == 0 else None,
                )
            ax.set_yticks(range(len(rows)), [r["policy"] for r in rows])
            ax.invert_yaxis()
            ax.axvline(0, color="#45515c", linewidth=0.8)
            ax.set_title(mode.title(), loc="left", fontweight="bold")
            ax.set_xlabel("Complete token savings versus current default (%)")
            ax.spines[["top", "right"]].set_visible(False)
            ax.legend(frameon=False, loc="lower right", fontsize=8)
        fig.suptitle(f"Encoding policy comparison across {data['spectra']} spectra", fontsize=14)
        fig.savefig(output / "token-savings.png", dpi=180)
        plt.close(fig)


if __name__ == "__main__":
    main()
