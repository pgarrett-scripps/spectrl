"""Compare complete Python/JavaScript tokens from identical source inputs.

Run after `cd js && npm ci`: python scripts/check_token_parity.py
Reports raw-CBOR differences separately from compressor differences. No files are
written unless --output is supplied. A mismatch exits unsuccessfully.
"""

from __future__ import annotations

import argparse
import copy
import json
import platform
import subprocess
import warnings
import zlib
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import numpy as np

from spectrl import encode_spectrum, spectrum_from_dict
from spectrl.cbor_format import read_token_payload

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    cases = json.loads((ROOT / "test-vectors/token-parity-inputs.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(20260920)
    for dtype in ("float64", "float32", "int32"):
        for n in (0, 1, 3, 24, 256, 4096):
            for sample in range(3):
                mz = np.sort(rng.uniform(50, 2000, n)).astype(dtype)
                intensity = rng.lognormal(3, 4, n).astype(dtype)
                cases.append(
                    {
                        "name": f"random/{dtype}/{n}/{sample}",
                        "spec": {
                            "default_array_length": n,
                            "mz": mz.tolist(),
                            "intensity": intensity.tolist(),
                            "array_dtypes": {"mz": dtype, "intensity": dtype},
                        },
                    }
                )
    return cases


def _decode_mismatch(token, decoded):
    """Array names whose reconstructed float64 bits differ between languages."""
    if decoded is None:
        return []
    from spectrl import decode_token

    result = decode_token(token)
    mismatched = []
    for name in ("mz", "intensity", "charge"):
        values = getattr(result, name)
        ours = np.asarray(values, dtype="<f8").tobytes().hex() if values is not None else None
        if ours != decoded.get(name):
            mismatched.append(name)
    return mismatched


def compare(cases):
    run = subprocess.run(
        ["node", "--import", "tsx", "scripts/token_parity.ts"],
        cwd=ROOT / "js",
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    results = json.loads(run.stdout)
    counts, differences = Counter(), []
    for case, result in zip(cases, results, strict=True):
        label = f"{'lossless' if case['options']['lossless'] else 'lossy'}/{case['options']['compression']}"
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="spectrl token length .* exceeds recommended")
                token = encode_spectrum(spectrum_from_dict(copy.deepcopy(case["spec"])), **case["options"])
        except ValueError as error:
            differences.append({"name": case["name"], "profile": label, "python_error": str(error)})
            continue
        if token == result.get("token"):
            counts[label] += 1
            # A byte-identical token can still reconstruct different values if
            # the two runtimes disagree about expm1, so the decoded arrays are
            # compared bit for bit as well.
            mismatched = _decode_mismatch(token, result.get("decoded"))
            if mismatched:
                counts[label] -= 1
                differences.append(
                    {"name": case["name"], "profile": label, "kind": "decoded arrays", "arrays": mismatched}
                )
        else:
            kind = (
                "encoding error"
                if "error" in result
                else (
                    "compression"
                    if read_token_payload(token) == read_token_payload(result["token"])
                    else "CBOR or arrays"
                )
            )
            differences.append({"name": case["name"], "profile": label, "kind": kind, "js_error": result.get("error")})
    return {"compared": len(cases), "identical": dict(counts), "differences": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inputs", type=Path, help="Optional JSON list of {name, spec} source inputs")
    args = parser.parse_args()
    cases = [
        {**case, "options": {"lossless": lossless, "compression": compression}}
        for case in (json.loads(args.inputs.read_text(encoding="utf-8")) if args.inputs else inputs())
        for lossless in (True, False)
        for compression in ("raw", "zlib", "brotli")
    ]
    report = {"compared": 0, "identical": Counter(), "differences": []}
    # Keep large real-spectrum runs bounded instead of duplicating the whole
    # corpus in a single Node subprocess request/response.
    for start in range(0, len(cases), 36):
        batch = compare(cases[start : start + 36])
        report["compared"] += batch["compared"]
        report["identical"].update(batch["identical"])
        report["differences"].extend(batch["differences"])
    report["environment"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "numpy": np.__version__,
        "cbor2": version("cbor2"),
        "brotli": version("brotli"),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "pako": json.loads((ROOT / "js/node_modules/pako/package.json").read_text(encoding="utf-8"))["version"],
        "cbor-x": json.loads((ROOT / "js/node_modules/cbor-x/package.json").read_text(encoding="utf-8"))["version"],
    }
    text = json.dumps(report, indent=2) + "\n"
    print(text, end="")
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    raise SystemExit(bool(report["differences"]))


if __name__ == "__main__":
    main()
