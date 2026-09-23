"""Fail if the Python and TypeScript decoders disagree on any adversarial token.

Run after `cd js && npm ci`:

    python scripts/check_adversarial_parity.py [--mutations N] [--seeds A B ...]

Generates the corpus from `scripts/adversarial_corpus.py`, decodes it with both
implementations, and compares three things per case: whether the token was
accepted, the values recovered when it was, and whether either decoder let a
non-SpectrlDecodeError exception escape. A named case is additionally checked
against the verdict the format requires. Any disagreement exits unsuccessfully.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adversarial_corpus import ACCEPT, build  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMPARED = ("n", "nparams", "nuser", "arrays", "mz", "units")


def typescript_verdicts(cases: list[dict], workdir: Path) -> list[dict]:
    corpus = workdir / "corpus.json"
    verdicts = workdir / "verdicts.json"
    corpus.write_text(json.dumps([{"name": c["name"], "token": c["token"]} for c in cases]), encoding="utf-8")
    subprocess.run(
        ["node", "--import", "tsx", "scripts/adversarial_decode.ts", str(corpus), str(verdicts)],
        cwd=ROOT / "js",
        check=True,
    )
    return json.loads(verdicts.read_text(encoding="utf-8"))


def compare(cases: list[dict], ts: list[dict]) -> list[str]:
    problems: list[str] = []
    for case, other in zip(cases, ts, strict=True):
        mine, name = case["py"], case["name"]
        for label, result in (("python", mine), ("typescript", other)):
            if result.get("escape"):
                problems.append(
                    f"{name}: {label} raised {result['escape']} instead of a decode error: {result['message']}"
                )
        if mine["ok"] != other["ok"]:
            accepted = "python" if mine["ok"] else "typescript"
            problems.append(f"{name}: accepted by {accepted} only")
            continue
        if mine["ok"]:
            for field in COMPARED:
                if mine.get(field) != other.get(field):
                    problems.append(
                        f"{name}: {field} differs, python={mine.get(field)!r} typescript={other.get(field)!r}"
                    )
        if "expect" in case and mine["ok"] != (case["expect"] == ACCEPT):
            problems.append(f"{name}: expected {case['expect']} by rule '{case['rule']}'")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mutations", type=int, default=20000, help="mutations per seed")
    parser.add_argument("--seeds", type=int, nargs="+", default=[31337, 7, 99, 2024, 55555, 8675309])
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "experiments/v3/adversarial-parity-results.json",
        help="where to record the run; pass /dev/null to skip",
    )
    args = parser.parse_args()

    named, mutations, problems = 0, 0, []
    with tempfile.TemporaryDirectory() as tmp:
        for index, seed in enumerate(args.seeds):
            # The named cases are the same every time; compare them once.
            cases = build(seed, args.mutations, include_named=index == 0)
            named += sum(1 for c in cases if "expect" in c)
            mutations += sum(1 for c in cases if "expect" not in c)
            problems += compare(cases, typescript_verdicts(cases, Path(tmp)))
            print(f"seed {seed}: {len(cases)} cases checked")

    total = named + mutations
    print(f"\n{total} adversarial tokens compared: {named} named, {mutations} mutations across {len(args.seeds)} seeds")
    if str(args.report) != os.devnull:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {
                    "description": "Python/TypeScript decoder agreement over the adversarial token corpus.",
                    "generated_by": "scripts/check_adversarial_parity.py",
                    "python": platform.python_version(),
                    "node": subprocess.run(
                        ["node", "--version"], capture_output=True, text=True, check=True
                    ).stdout.strip(),
                    "seeds": args.seeds,
                    "mutations_per_seed": args.mutations,
                    "compared": total,
                    "named": named,
                    "mutations": mutations,
                    "disagreements": len(problems),
                    "problems": problems[:200],
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.report.relative_to(ROOT)}")
    if problems:
        print(f"{len(problems)} disagreements:")
        for problem in problems[:60]:
            print(f"  {problem}")
        return 1
    print("Python and TypeScript agree on every case.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
