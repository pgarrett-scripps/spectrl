"""Compare fixed exact encodings with two trial-compression policies.

Run with the paper analysis environment. The paper repository must be the sibling
spectrl-paper checkout. This experiment reads its pinned corpus through encode_all.
"""
from pathlib import Path
import copy
import hashlib
import json
import sys
import time
import warnings
import zlib

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT.parent / "spectrl-paper" / "paper"
sys.path[:0] = [str(ROOT / "src"), str(PAPER / "analysis" / "scripts")]
import cbor2
from _datasets import encode_all
from spectrl import encode_spectrum
from spectrl.cbor_format import read_token_document
from spectrl.peaks import canonical_sort
from spectrl.pipeline import encode_pipeline


def size(document):
    payload = zlib.compress(cbor2.dumps(document, canonical=True), 6)
    return 22 + (4 * len(payload) + 2) // 3


def main():
    warnings.simplefilter("ignore")
    rows = encode_all()
    result = []
    start = time.perf_counter()
    for row in rows:
        spectrum = canonical_sort(row.source)
        document, _ = read_token_document(encode_spectrum(spectrum, lossless=True))
        fixed = size(document)
        options = []
        for array in document.get(6, []):
            key = {1000514: "mz", 1000515: "intensity", 1000516: "charge"}.get(array[1])
            values = getattr(spectrum, key) if key else spectrum.extra_arrays[array.get(4, f"MS:{array[1]:07d}")]
            options.append([
                {**array, 2: [i, 1], 5: encode_pipeline(values, array[0], [i, 1])[0]}
                for i in (0, 1, 2)
            ])
        proxy = copy.deepcopy(document)
        proxy[6] = [min(candidates, key=lambda a: len(zlib.compress(cbor2.dumps(a, canonical=True), 6)))
                    for candidates in options]
        best = fixed
        for index, candidates in enumerate(options):
            chosen = document[6][index]
            for candidate in candidates:
                document[6][index] = candidate
                trial = size(document)
                if trial < best:
                    best, chosen = trial, candidate
            document[6][index] = chosen
        result.append({"dataset": row.dataset.key, "id": row.spectrum_id,
                       "fixed": fixed, "proxy": size(proxy), "coordinate": best,
                       "choices": [a[2][0] for a in document.get(6, [])]})
    report = {"n": len(result), "seconds": time.perf_counter() - start,
              "method": "Single coordinate pass in descriptor order, strict improvement only",
              "registry_sha256": hashlib.sha256((ROOT / "schema/registry.json").read_bytes()).hexdigest(),
              "totals": {key: sum(row[key] for row in result) for key in ("fixed", "proxy", "coordinate")},
              "spectra": result}
    (ROOT / "experiments/v3/core-selection-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k != "spectra"})


if __name__ == "__main__":
    main()
