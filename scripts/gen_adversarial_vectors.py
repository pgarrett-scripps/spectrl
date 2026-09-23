"""Write the named adversarial cases to the shared conformance vector file.

    python scripts/gen_adversarial_vectors.py

The corpus itself lives in `scripts/adversarial_corpus.py`; this only pins the
named half of it as a language-agnostic file both test suites read, so a change
to the accepted language shows up as a reviewable diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adversarial_corpus import named_cases  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "test-vectors/adversarial-vectors.json"


def main() -> int:
    document = {
        "format": "spectrl-adversarial-vectors-1",
        "description": (
            "Complete spectrl.v3 tokens that every implementation must accept or reject as "
            "recorded. Each entry names the rule under test. Unlike negative-vectors.json "
            "these are whole tokens, so framing, base64url canonicality, compression and "
            "resource budgets are covered alongside CBOR and header validation. Rejection "
            "must be reported as the implementation's decode error, never another exception."
        ),
        "generated_by": "scripts/gen_adversarial_vectors.py",
        "vectors": [
            {"name": c["name"], "rule": c["rule"], "expect": c["expect"], "token": c["token"]} for c in named_cases()
        ],
    }
    OUT.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    counts = {"accept": 0, "reject": 0}
    for vector in document["vectors"]:
        counts[vector["expect"]] += 1
    summary = f"{counts['accept']} accept, {counts['reject']} reject"
    print(f"{OUT.relative_to(ROOT)}: {len(document['vectors'])} vectors ({summary})")
    print(f"size: {OUT.stat().st_size / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
