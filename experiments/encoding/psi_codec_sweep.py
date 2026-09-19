"""Sweep standalone PSI-MS array compression modes, with per-array results.

This experiment does not change public codecs or emit experimental tokens.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import time
import warnings
import zlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import zstandard
from benchmark import array_key, arrays, load_samples
from psi_transforms import dictionary_decode, dictionary_encode, mzmlb_decode, mzmlb_encode, self_check, shuffle

from spectrl.codecs._delta import delta_shuffle, delta_unshuffle
from spectrl.codecs.numpress import (
    decode_numlin_raw,
    decode_numpic_raw,
    decode_numslof_raw,
    encode_numlin_raw,
    encode_numpic_raw,
    encode_numslof_raw,
)
from spectrl.codecs.raw import _np_dtype
from spectrl.header import DESC_TYPE
from spectrl.peaks import build_array_blobs

ZSTD_LEVELS = (1, 3, 9, 19)
ZLIB_LEVELS = (1, 6, 9)


def inventory(path):
    blocks = path.read_text().split("\n[Term]\n")
    terms = []
    for block in blocks:
        if "is_a: MS:1000572 " not in block:
            continue
        lines = block.splitlines()
        terms.append(
            {
                "accession": next(line[4:] for line in lines if line.startswith("id: ")),
                "name": next(line[6:] for line in lines if line.startswith("name: ")),
            }
        )
    return terms


def transformed_variants(values, skipped):
    raw = values.tobytes()
    width = values.dtype.itemsize
    yield "raw", {}, lambda: raw, lambda data: data
    yield "shuffle", {}, lambda: shuffle(raw, width), lambda data: shuffle(data, width, True)
    yield "dictionary", {}, lambda: dictionary_encode(raw, width), lambda data: dictionary_decode(data, width)
    yield "modular-delta-shuffle", {}, lambda: delta_shuffle(raw, width), lambda data: delta_unshuffle(data, width)

    for family, encoder, decoder, params in (
        ("numpress-linear", encode_numlin_raw, decode_numlin_raw, {"fixed_point": 100000}),
        ("numpress-slof", encode_numslof_raw, decode_numslof_raw, {"requested_fixed_point": 3600}),
        ("numpress-pic", encode_numpic_raw, decode_numpic_raw, {}),
    ):
        # Domain validation occurs before calling the native Numpress backend.
        try:
            payload = encoder(values)
        except ValueError as error:
            skipped.append({"family": family, "reason": str(error)})
            continue
        if family == "numpress-slof":
            import struct

            params = {**params, "actual_fixed_point": struct.unpack(">d", payload[:8])[0]}
        yield (
            family,
            params,
            lambda encoder=encoder: encoder(values),
            lambda data, decoder=decoder: decoder(data).astype(values.dtype).tobytes(),
        )

    truncations = (0, 16, 29, 36) if width == 8 else (0, 8, 16)
    for predictor in ("none", "delta", "linear"):
        for bits in truncations:
            yield (
                f"mzmlb-{predictor}",
                {"truncated_mantissa_bits": bits},
                lambda predictor=predictor, bits=bits: mzmlb_encode(values, predictor, bits).tobytes(),
                lambda data, predictor=predictor: mzmlb_decode(
                    np.frombuffer(data, dtype=values.dtype), predictor
                ).tobytes(),
            )


def wrappers(family):
    if family == "raw":
        yield "MS:1000576", "none", 0
        for level in ZLIB_LEVELS:
            yield "MS:1000574", "zlib", level
        for level in ZSTD_LEVELS:
            yield "MS:1003780", "zstd", level
    elif family in ("shuffle", "dictionary"):
        for level in ZSTD_LEVELS:
            yield {"shuffle": "MS:1003781", "dictionary": "MS:1003782"}[family], "zstd", level
    elif family == "modular-delta-shuffle":
        for level in ZLIB_LEVELS:
            yield "experimental:delta-shuffle-zlib", "zlib", level
        for level in ZSTD_LEVELS:
            yield "experimental:delta-shuffle-zstd", "zstd", level
    elif family.startswith("numpress"):
        accessions = {
            "numpress-linear": (1002312, 1002746, 1003783),
            "numpress-pic": (1002313, 1002747, 1003784),
            "numpress-slof": (1002314, 1002748, 1003785),
        }[family]
        for accession, compressor, level in zip(accessions, ("none", "zlib", "zstd"), (0, 6, 3), strict=True):
            yield f"MS:{accession}", compressor, level
    else:
        accession = {"mzmlb-none": 1003088, "mzmlb-delta": 1003089, "mzmlb-linear": 1003090}[family]
        yield f"MS:{accession}", "zlib", 6


def run_array(values, context):
    raw = values.tobytes()
    unsigned = np.dtype(f"<u{values.dtype.itemsize}")
    skipped = []
    rows = []
    for family, params, encode_transform, decode_transform in transformed_variants(values, skipped):
        start = time.perf_counter_ns()
        transformed = encode_transform()
        transform_encode_us = (time.perf_counter_ns() - start) / 1000
        start = time.perf_counter_ns()
        recovered = decode_transform(transformed)
        transform_decode_us = (time.perf_counter_ns() - start) / 1000
        decoded = np.frombuffer(recovered, dtype=values.dtype)
        assert len(decoded) == len(values)
        changed = int(np.count_nonzero(values.view(unsigned) != decoded.view(unsigned)))
        error = np.abs(values.astype(np.float64) - decoded.astype(np.float64))
        nonzero = values != 0
        max_abs = float(error.max(initial=0))
        max_relative = float((error[nonzero] / np.abs(values[nonzero])).max(initial=0))
        scale = float(np.abs(values).max(initial=0)) or 1.0
        promised_exact = family in ("raw", "shuffle", "dictionary", "modular-delta-shuffle")
        if promised_exact or (family == "mzmlb-none" and params["truncated_mantissa_bits"] == 0):
            assert recovered == raw, (context, family)
        for accession, compressor, level in wrappers(family):
            start = time.perf_counter_ns()
            if compressor == "none":
                blob = transformed
            elif compressor == "zlib":
                blob = zlib.compress(transformed, level)
            else:
                blob = zstandard.ZstdCompressor(level=level).compress(transformed)
            compress_us = (time.perf_counter_ns() - start) / 1000
            start = time.perf_counter_ns()
            if compressor == "none":
                unpacked = blob
            elif compressor == "zlib":
                unpacked = zlib.decompress(blob)
            else:
                unpacked = zstandard.ZstdDecompressor().decompress(blob)
            decompress_us = (time.perf_counter_ns() - start) / 1000
            assert unpacked == transformed
            rows.append(
                {
                    **context,
                    "codec": accession,
                    "family": family,
                    "parameters": params,
                    "compressor": compressor,
                    "level": level,
                    "values": len(values),
                    "raw_bytes": len(raw),
                    "bytes": len(blob),
                    "changed_values": changed,
                    "bit_exact": changed == 0,
                    "max_abs_error": max_abs,
                    "max_relative_error": max_relative,
                    "max_peak_normalized_error": max_abs / scale,
                    "encode_us": transform_encode_us + compress_us,
                    "decode_us": transform_decode_us + decompress_us,
                }
            )
    return rows, [{**context, **item} for item in skipped]


def summarize(rows):
    by_array = defaultdict(list)
    by_mode = defaultdict(list)
    for row in rows:
        identity = row["dataset"], row["id"], row["array"]
        by_array[identity].append(row)
        key = row["codec"], row["level"], row["parameters"].get("truncated_mantissa_bits", -1)
        by_mode[key].append(row)
    policies = defaultdict(list)
    for identity, candidates in by_array.items():
        baseline = next(row for row in candidates if row["codec"] == "MS:1000574" and row["level"] == 6)
        standard = [row for row in candidates if row["family"] in ("raw", "shuffle", "dictionary")]
        defaults = [row for row in standard if row["level"] in (0, 3, 6)]
        current = [row for row in defaults if row["family"] != "dictionary" and row["compressor"] != "none"]
        experimental = [row for row in candidates if row["family"] == "modular-delta-shuffle"]
        pools = {
            "current_supported": current,
            "psi_lossless_defaults": defaults,
            "psi_lossless_tuned": standard,
            "psi_defaults_plus_delta_zlib6": defaults
            + [row for row in experimental if row["compressor"] == "zlib" and row["level"] == 6],
            "psi_defaults_plus_delta": defaults + [row for row in experimental if row["level"] in (3, 6)],
            "psi_tuned_plus_delta": standard + experimental,
            "psi_verified_exact_defaults": [
                row
                for row in candidates
                if row["codec"].startswith("MS:") and row["bit_exact"] and row["level"] in (0, 3, 6)
            ],
            "psi_verified_exact_defaults_plus_delta": [
                row
                for row in candidates
                if row["codec"].startswith("MS:") and row["bit_exact"] and row["level"] in (0, 3, 6)
            ]
            + [row for row in experimental if row["level"] in (3, 6)],
        }
        for policy, pool in pools.items():
            winner = min(pool, key=lambda row: row["bytes"])
            policies[policy].append(
                {
                    "dataset": identity[0],
                    "id": identity[1],
                    "array": identity[2],
                    "representation": winner["representation"],
                    "baseline_bytes": baseline["bytes"],
                    "bytes": winner["bytes"],
                    "winner": f"{winner['codec']} level {winner['level']}",
                }
            )
    summaries = {}
    for policy, selected in policies.items():
        groups = defaultdict(list)
        for row in selected:
            groups["all"].append(row)
            groups[row["array"]].append(row)
            groups["representation:" + row["representation"]].append(row)
        summaries[policy] = {}
        for group, entries in groups.items():
            total = sum(row["bytes"] for row in entries)
            baseline = sum(row["baseline_bytes"] for row in entries)
            summaries[policy][group] = {
                "arrays": len(entries),
                "bytes": total,
                "saving_vs_zlib6_pct": 100 * (1 - total / baseline),
                "median_saving_vs_zlib6_pct": statistics.median(
                    100 * (1 - row["bytes"] / row["baseline_bytes"]) for row in entries
                ),
                "winners": dict(Counter(row["winner"] for row in entries)),
            }
    modes = []
    for (codec, level, truncation), entries in by_mode.items():
        for group in ("all", *sorted({row["array"] for row in entries})):
            subset = entries if group == "all" else [row for row in entries if row["array"] == group]
            modes.append(
                {
                    "codec": codec,
                    "level": level,
                    "truncated_bits": truncation,
                    "array": group,
                    "arrays": len(subset),
                    "bytes": sum(row["bytes"] for row in subset),
                    "exact_arrays": sum(row["bit_exact"] for row in subset),
                    "changed_values": sum(row["changed_values"] for row in subset),
                    "max_abs_error": max(row["max_abs_error"] for row in subset),
                    "max_relative_error": max(row["max_relative_error"] for row in subset),
                    "max_peak_normalized_error": max(row["max_peak_normalized_error"] for row in subset),
                    "encode_us": sum(row["encode_us"] for row in subset),
                    "decode_us": sum(row["decode_us"] for row in subset),
                }
            )
    return summaries, modes, policies


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--per-group", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("experiments/encoding/psi-sweep.json"))
    parser.add_argument("--rows", type=Path, default=Path("/tmp/spectrl-psi-sweep-rows.json"))
    args = parser.parse_args()
    self_check()
    terms = inventory(args.vocabulary)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        samples, provenance = load_samples(args)
    rows, skipped = [], []
    for index, sample in enumerate(samples):
        source = arrays(sample.source)
        _, descriptors = build_array_blobs(sample.source, lossless=True)
        for descriptor in descriptors:
            key = array_key(descriptor)
            dtype = np.dtype(_np_dtype(descriptor[DESC_TYPE]))
            values = source[key].astype(dtype)
            context = {
                "dataset": sample.dataset,
                "id": sample.source.id,
                "array": key,
                "representation": sample.representation,
                "ms_level": sample.ms_level,
                "dtype": dtype.str,
                "distinct_values": len(np.unique(values.view(f"<u{dtype.itemsize}"))),
            }
            measured, ineligible = run_array(values, context)
            rows.extend(measured)
            skipped.extend(ineligible)
        print(f"Measured spectrum {index + 1}/{len(samples)}: {sample.dataset}", flush=True)
    summaries, modes, selections = summarize(rows)
    represented = {row["codec"] for row in rows}
    for term in terms:
        term["status"] = "measured" if term["accession"] in represented else "not measured"
        if term["accession"] == "MS:1003826":
            term["reason"] = (
                "Requires an external coordinate grid and spacing model, absent from these standalone arrays"
            )
        else:
            assert term["accession"] in represented, term
    result = {
        "inventory": terms,
        "vocabulary_sha256": hashlib.sha256(args.vocabulary.read_bytes()).hexdigest(),
        "dictionary_reference": (
            "https://github.com/mobiusklein/mzdata/blob/"
            "ebe2e9a8f3db8f11de8726aaa5a04920d00aa580/crates/mzdata-bindata/src/encodings.rs"
        ),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "zstandard": importlib.metadata.version("zstandard"),
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
            "timing": "One measurement per operation, exploratory Python implementation timings only",
        },
        "spectra": len(samples),
        "array_count": len({(row["dataset"], row["id"], row["array"]) for row in rows}),
        "provenance": provenance,
        "policies": summaries,
        "modes": modes,
        "selections": selections,
        "skipped": skipped,
        "variants_measured": len(rows),
        "detailed_rows_file": str(args.rows),
    }
    args.rows.write_text(json.dumps(rows, indent=2) + "\n")
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {"variants_measured": len(rows), "policies": {key: value["all"] for key, value in summaries.items()}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
