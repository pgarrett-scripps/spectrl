"""Pin complete raw Python tokens for the shared token-parity inputs.

Output: test-vectors/token-parity.json, read by tests/test_token_parity.py and
js/test/token_parity.test.ts. Both writers must reproduce every token exactly.

Run:  uv run python scripts/gen_token_parity.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from spectrl import encode_spectrum, spectrum_from_dict

ROOT = Path(__file__).resolve().parents[1]


def generate() -> dict:
    inputs = json.loads((ROOT / "test-vectors/token-parity-inputs.json").read_text(encoding="utf-8"))
    return {
        case["name"]: {
            profile: encode_spectrum(
                spectrum_from_dict(copy.deepcopy(case["spec"])), lossless=profile == "lossless", compression="raw"
            )
            for profile in ("lossless", "lossy")
        }
        for case in inputs
    }


if __name__ == "__main__":
    path = ROOT / "test-vectors/token-parity.json"
    path.write_text(json.dumps(generate(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}")
