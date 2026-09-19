"""Compare the historical PSI #377 predictor with bit-preserving modular delta.

This reproduces the floating predictor in mobiusklein/mzd.cpp commit
a69a89b2c3bb1c7346e934de1d7c18ee40775ab4, src/mzd.hpp, lines 98 to 133.
It compares payload size and reconstruction error, not implementation speed.
"""

import argparse
import json
import warnings
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import zstandard
from benchmark import array_key, arrays, load_samples, transform

from spectrl.codecs._delta import delta_shuffle, delta_unshuffle
from spectrl.codecs.raw import _np_dtype
from spectrl.header import DESC_TYPE
from spectrl.peaks import build_array_blobs

REFERENCE = "https://github.com/mobiusklein/mzd.cpp/blob/a69a89b2c3bb1c7346e934de1d7c18ee40775ab4/src/mzd.hpp#L98-L133"


def floating_encode(values):
    """Reproduce data[i] += offset - previous_original at the declared precision."""
    result = values.copy()
    if len(values) > 1:
        result[1:] += values[0] - values[:-1]
    return result


def floating_decode(values):
    """Reproduce data[i] += previous_decoded - offset at the declared precision."""
    result = values.copy()
    if len(values) > 1:
        offset = result[0]
        previous = result[1]
        for i in range(2, len(result)):
            result[i] += previous - offset
            previous = result[i]
    return result


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups[row["array"]].append(row)
    summaries = {}
    for key, group in groups.items():
        summaries[key] = {
            "arrays": len(group),
            "values": sum(row["values"] for row in group),
            "floating_changed_arrays": sum(row["floating_changed_values"] > 0 for row in group),
            "floating_changed_values": sum(row["floating_changed_values"] for row in group),
            "floating_max_abs_error": max(row["floating_max_abs_error"] for row in group),
            "floating_max_relative_error": max(row["floating_max_relative_error"] for row in group),
            "modular_all_bit_exact": all(row["modular_bit_exact"] for row in group),
            "sizes": {},
        }
        for compressor in ("zlib-6", "zstd-3"):
            totals = {
                method: sum(row["sizes"][compressor][method] for row in group)
                for method in ("raw", "shuffle", "floating_delta_shuffle", "modular_delta_shuffle")
            }
            totals["modular_saving_vs_floating_pct"] = 100 * (
                1 - totals["modular_delta_shuffle"] / totals["floating_delta_shuffle"]
            )
            totals["modular_smaller_arrays"] = sum(
                row["sizes"][compressor]["modular_delta_shuffle"] < row["sizes"][compressor]["floating_delta_shuffle"]
                for row in group
            )
            summaries[key]["sizes"][compressor] = totals
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--per-group", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("experiments/encoding/delta-comparison.json"))
    args = parser.parse_args()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        samples, provenance = load_samples(args)
    rows = []
    skipped = []
    zstd_encoder = zstandard.ZstdCompressor(level=3)
    engines = {
        "zlib-6": (lambda raw: zlib.compress(raw, 6), zlib.decompress),
        "zstd-3": (zstd_encoder.compress, zstandard.ZstdDecompressor().decompress),
    }
    for sample in samples:
        source = arrays(sample.source)
        _, descriptors = build_array_blobs(sample.source, lossless=True)
        for descriptor in descriptors:
            key = array_key(descriptor)
            dtype = np.dtype(_np_dtype(descriptor[DESC_TYPE]))
            if dtype.kind != "f":
                skipped.append({"dataset": sample.dataset, "id": sample.source.id, "array": key})
                continue
            values = source[key].astype(dtype)
            raw = values.tobytes()
            width = dtype.itemsize
            predicted = floating_encode(values)
            recovered = floating_decode(predicted)
            uint = np.dtype(f"<u{width}")
            changed = np.count_nonzero(values.view(uint) != recovered.view(uint))
            error = np.abs(values.astype(np.float64) - recovered.astype(np.float64))
            nonzero = values != 0
            modular = delta_shuffle(raw, width)
            assert delta_unshuffle(modular, width) == raw
            payloads = {
                "raw": raw,
                "shuffle": transform(raw, width, "shuffle"),
                "floating_delta_shuffle": transform(predicted.tobytes(), width, "shuffle"),
                "modular_delta_shuffle": modular,
            }
            sizes = {}
            for name, (encode, decode) in engines.items():
                sizes[name] = {}
                for method, payload in payloads.items():
                    blob = encode(payload)
                    assert decode(blob) == payload
                    sizes[name][method] = len(blob)
            rows.append(
                {
                    "dataset": sample.dataset,
                    "id": sample.source.id,
                    "array": key,
                    "representation": sample.representation,
                    "dtype": dtype.str,
                    "values": len(values),
                    "floating_changed_values": int(changed),
                    "floating_max_abs_error": float(error.max(initial=0)),
                    "floating_max_relative_error": float((error[nonzero] / np.abs(values[nonzero])).max(initial=0)),
                    "modular_bit_exact": True,
                    "sizes": sizes,
                }
            )
    summary = summarize(rows)
    result = {
        "floating_predictor_reference": REFERENCE,
        "scope": "Reproduced historical predictor, shared byte shuffle and compressors, no truncation",
        "spectra": len(samples),
        "skipped_nonfloating_arrays": skipped,
        "summary": summary,
        "arrays": rows,
        "provenance": provenance,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"spectra": len(samples), "skipped": len(skipped), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
