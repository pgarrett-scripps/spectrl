"""Explore array transforms and current API policies without changing the format.

Run with PYTHONPATH=src .venv/bin/python experiments/encoding/benchmark.py.
Use --manifest PATH for the paper's corpus.json, or --paths for mzML inputs.
"""

from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import importlib.metadata
import json
import lzma
import platform
import statistics
import time
import warnings
import zlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cbor2
import numpy as np
import zstandard
from mzmlpy.run import Mzml

from spectrl import decode_token, encode_spectrum, from_mzmlpy
from spectrl.codecs.numpress import (
    active_backend,
    decode_numlin_raw,
    decode_numslof_raw,
    encode_numlin_raw,
    encode_numslof_raw,
)
from spectrl.codecs.raw import _np_dtype
from spectrl.cv import COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB
from spectrl.header import DESC_ARRAY, DESC_COMP, DESC_DATA, DESC_FP, DESC_NAME, DESC_TYPE
from spectrl.peaks import build_array_blobs, canonical_sort


@dataclass
class Sample:
    dataset: str
    source: object
    ms_level: int
    representation: str


def timed(call, repeats):
    result = call()
    elapsed = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        result = call()
        elapsed.append((time.perf_counter_ns() - start) / 1000)
    return result, statistics.median(elapsed)


def transform(raw, width, name, inverse=False):
    """Modular word deltas preserve every input bit, including NaN payloads."""
    if name == "raw":
        return raw
    shuffled = name.endswith("shuffle")
    if shuffled and inverse:
        raw = np.frombuffer(raw, dtype=np.uint8).reshape(width, -1).T.copy().tobytes()
    base = name.removesuffix("-shuffle") if name != "shuffle" else "raw"
    words = np.frombuffer(raw, dtype=f"<u{width}").copy()
    if base in {"delta", "delta2"}:
        for _ in range(2 if base == "delta2" else 1):
            if inverse:
                words = np.cumsum(words, dtype=words.dtype)
            else:
                words[1:] = words[1:] - words[:-1]
    elif base == "xor":
        if inverse:
            words = np.bitwise_xor.accumulate(words)
        else:
            words[1:] = words[1:] ^ words[:-1]
    elif base != "raw":
        raise ValueError(name)
    raw = words.astype(f"<u{width}").tobytes()
    if shuffled and not inverse:
        raw = np.frombuffer(raw, dtype=np.uint8).reshape(-1, width).T.copy().tobytes()
    return raw


TRANSFORMS = ("raw", "shuffle", "delta", "delta-shuffle", "delta2-shuffle", "xor", "xor-shuffle")


def compressors():
    result = {"none": (lambda b: b, lambda b: b)}
    for level in (1, 6, 9):
        result[f"zlib-{level}"] = (lambda b, level=level: zlib.compress(b, level), zlib.decompress)
    result["gzip-6"] = (lambda b: gzip.compress(b, compresslevel=6, mtime=0), gzip.decompress)
    for level in (1, 3, 9, 19):
        # Include context construction, matching the library's current implementation.
        result[f"zstd-{level}"] = (
            lambda b, level=level: zstandard.ZstdCompressor(level=level).compress(b),
            lambda b: zstandard.ZstdDecompressor().decompress(b),
        )
    result["bz2-9"] = (bz2.compress, bz2.decompress)
    result["xz-3"] = (lambda b: lzma.compress(b, preset=3), lzma.decompress)
    try:
        import brotli
    except ImportError:
        pass
    else:
        result["brotli-5"] = (lambda b: brotli.compress(b, quality=5), brotli.decompress)
    try:
        import lz4.frame
    except ImportError:
        pass
    else:
        result["lz4-0"] = (lz4.frame.compress, lz4.frame.decompress)
    return result


def load_samples(args):
    if args.manifest:
        manifest = json.loads(args.manifest.read_text())
        root = args.manifest.resolve().parents[2]
        inputs = [(item["key"], root / item["local_path"], item) for item in manifest["datasets"]]
    else:
        inputs = [(p.stem, p, {}) for p in args.paths]
    samples, provenance = [], []
    for key, path, item in inputs:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if item.get("sha256") and digest != item["sha256"]:
            raise ValueError(f"hash mismatch for {path}")
        groups = defaultdict(list)
        with Mzml(str(path)) as mzml:
            refs = mzml.referenceable_param_groups
            if not isinstance(refs, dict):
                refs = {g.id: g for g in refs}
            for spectrum in mzml.spectra:
                source = from_mzmlpy(spectrum, ref_groups=refs)
                if source.mz is None or not len(source.mz):
                    continue
                accessions = {str(p.accession): p.value for p in source.params}
                if item.get("select_spectrum_accession") not in (None, *accessions):
                    continue
                level = int(accessions.get("MS:1000511", 0))
                representation = "profile" if "MS:1000128" in accessions else "centroid"
                groups[level, representation].append(source)
        selected = []
        for (level, representation), group in sorted(groups.items()):
            ordered = sorted(group, key=lambda s: s.default_array_length)
            positions = np.linspace(0, len(ordered) - 1, min(args.per_group, len(ordered))).round().astype(int)
            for pos in positions:
                source = canonical_sort(ordered[pos])
                samples.append(Sample(key, source, level, representation))
                selected.append(
                    {
                        "id": source.id,
                        "peaks": source.default_array_length,
                        "ms_level": level,
                        "representation": representation,
                    }
                )
        provenance.append({"dataset": key, "path": str(path), "sha256": digest, "selected": selected})
    return samples, provenance


def array_key(desc):
    return {1000514: "mz", 1000515: "intensity", 1000516: "charge"}.get(
        desc[DESC_ARRAY],
        desc.get(DESC_NAME, f"MS:{desc[DESC_ARRAY]:07d}"),
    )


def arrays(spec):
    return {
        k: np.asarray(v)
        for k, v in {
            "mz": spec.mz,
            "intensity": spec.intensity,
            "charge": spec.charge,
            **spec.extra_arrays,
        }.items()
        if v is not None
    }


def error_metrics(original, decoded):
    a, b = np.asarray(original, dtype=np.float64), np.asarray(decoded, dtype=np.float64)
    error = np.abs(a - b)
    nonzero = a != 0
    scale = float(np.max(np.abs(a), initial=0)) or 1
    return {
        "max_abs": float(np.max(error, initial=0)),
        "max_relative": float(np.max(error[nonzero] / np.abs(a[nonzero]), initial=0)),
        "max_peak_normalized": float(np.max(error, initial=0) / scale),
        "changed_zeros": int(np.sum(b[~nonzero] != 0)),
    }


def pipeline_rows(sample, repeats, engines):
    source_arrays = arrays(sample.source)
    _, lossless_desc = build_array_blobs(sample.source, lossless=True)
    lossy_blobs, lossy_desc = build_array_blobs(sample.source, lossless=False)
    defaults = {array_key(d): d for d in lossy_desc}
    baseline_sizes = {array_key(d): len(b) for b, d in zip(lossy_blobs, lossy_desc, strict=True)}
    for desc in lossless_desc:
        key = array_key(desc)
        original = source_arrays[key]
        dtype = np.dtype(_np_dtype(desc[DESC_TYPE]))
        raw = original.astype(dtype).tobytes()
        default = defaults[key]
        baseline_lossless = len(zlib.compress(raw))
        baseline_lossy = baseline_sizes[key]
        variants = []
        for name in TRANSFORMS:
            variants.append(
                (
                    "lossless",
                    name,
                    lambda name=name, raw=raw, dtype=dtype: transform(raw, dtype.itemsize, name),
                    lambda b, name=name, dtype=dtype: np.frombuffer(
                        transform(b, dtype.itemsize, name, inverse=True), dtype=dtype
                    ),
                )
            )
        # Keep the current fixed point and decoded values while varying only the compressor.
        comp = default[DESC_COMP]
        if comp in (COMP_NUMLIN_ZLIB, COMP_NUMSLOF_ZLIB):
            enc, dec = (
                (encode_numlin_raw, decode_numlin_raw)
                if comp == COMP_NUMLIN_ZLIB
                else (encode_numslof_raw, decode_numslof_raw)
            )
            variants.append(
                ("lossy", "numpress", lambda enc=enc, original=original, fp=default[DESC_FP]: enc(original, fp), dec)
            )
        if key in ("mz", "intensity"):
            # Experimental precision reduction. This is not part of the public API.
            for name in ("raw", "shuffle", "delta-shuffle"):
                variants.append(
                    (
                        "lossy",
                        f"float32-{name}",
                        lambda name=name, original=original: transform(original.astype("<f4").tobytes(), 4, name),
                        lambda b, name=name: np.frombuffer(transform(b, 4, name, inverse=True), dtype="<f4"),
                    )
                )
        for mode, name, enc, dec in variants:
            transformed = enc()
            reference = dec(transformed)
            if mode == "lossless":
                assert reference.tobytes() == raw, (sample.dataset, key, name)
            metrics = error_metrics(original, reference)
            for engine, (compress, decompress) in engines.items():
                blob, enc_us = timed(lambda compress=compress, enc=enc: compress(enc()), repeats)
                recovered, dec_us = timed(
                    lambda dec=dec, decompress=decompress, blob=blob: dec(decompress(blob)), repeats
                )
                assert recovered.tobytes() == reference.tobytes(), (key, name, engine)
                yield {
                    "dataset": sample.dataset,
                    "id": sample.source.id,
                    "array": key,
                    "representation": sample.representation,
                    "ms_level": sample.ms_level,
                    "peaks": len(original),
                    "mode": mode,
                    "transform": name,
                    "compressor": engine,
                    "raw_bytes": len(raw),
                    "bytes": len(blob),
                    "encode_us": enc_us,
                    "decode_us": dec_us,
                    "baseline_bytes": baseline_lossless if mode == "lossless" else baseline_lossy,
                    "error": metrics,
                }


def options_for(source, policy, lossless):
    if policy == "default":
        # Keep the original experiment baseline stable after default changes.
        return dict.fromkeys(arrays(source), "zlib") if lossless else {}
    source_arrays = arrays(source)
    if policy in ("zstd", "shuffle"):
        return {key: "zstd" if policy == "zstd" else "byte-shuffled-zstd" for key in source_arrays}
    blobs, descriptors = build_array_blobs(
        source, lossless=lossless, array_encodings=options_for(source, "default", lossless)
    )
    mapping = {1002746: "numlin", 1002747: "numpic", 1002748: "numslof"}
    options = {}
    for desc in descriptors:
        key = array_key(desc)
        if desc[DESC_COMP] in mapping:
            options[key] = {"codec": mapping[desc[DESC_COMP]] + "-zstd"}
            if DESC_FP in desc:
                options[key]["fixed_point"] = desc[DESC_FP]
        else:
            options[key] = "zstd"
    if policy == "numpress-zstd":
        return options
    if policy.startswith("fp-"):
        if "mz" in options and isinstance(options["mz"], dict):
            options["mz"]["fixed_point"] = int(policy.removeprefix("fp-"))
        return options
    # Offline minimum among supported codecs. Charge and auxiliary semantics come
    # from the current resolver. Include descriptor overhead in the comparison.
    candidates = [(blobs, descriptors, options_for(source, "default", lossless))]
    for settings in (options, options_for(source, "zstd", lossless), options_for(source, "shuffle", lossless)):
        candidate_blobs, candidate_desc = build_array_blobs(source, lossless=lossless, array_encodings=settings)
        candidates.append((candidate_blobs, candidate_desc, settings))
    selected = {}
    for i, desc in enumerate(descriptors):
        key = array_key(desc)
        winner = min(
            candidates, key=lambda item: len(cbor2.dumps({**item[1][i], DESC_DATA: item[0][i]}, canonical=True))
        )
        if key in winner[2]:
            selected[key] = winner[2][key]
    return selected


def token_rows(sample, repeats):
    for lossless in (True, False):
        policies = (
            ["default", "zstd", "shuffle", "adaptive"]
            if lossless
            else [
                "default",
                "numpress-zstd",
                "adaptive",
                "fp-10000",
                "fp-1000000",
            ]
        )
        baseline = len(
            encode_spectrum(
                sample.source, lossless=lossless, array_encodings=options_for(sample.source, "default", lossless)
            )
        )
        for policy in policies:
            static_options = options_for(sample.source, policy, lossless) if policy != "adaptive" else None

            def encode(policy=policy, lossless=lossless, static_options=static_options):
                options = options_for(sample.source, policy, lossless) if policy == "adaptive" else static_options
                return encode_spectrum(sample.source, lossless=lossless, array_encodings=options)

            try:
                token, enc_us = timed(encode, repeats)
            except ValueError as exc:
                # Explicit finer fixed points can exceed Numpress's integer domain.
                if not policy.startswith("fp-"):
                    raise
                yield {
                    "dataset": sample.dataset,
                    "id": sample.source.id,
                    "mode": "lossless" if lossless else "lossy",
                    "policy": policy,
                    "skip": str(exc),
                }
                continue
            decoded, dec_us = timed(lambda token=token: decode_token(token), repeats)
            metrics = {}
            for key, original in arrays(sample.source).items():
                recovered = arrays(decoded)[key]
                if lossless:
                    assert recovered.astype(original.dtype).tobytes() == original.tobytes(), (key, policy)
                metrics[key] = error_metrics(original, recovered)
            yield {
                "dataset": sample.dataset,
                "id": sample.source.id,
                "representation": sample.representation,
                "ms_level": sample.ms_level,
                "peaks": sample.source.default_array_length,
                "mode": "lossless" if lossless else "lossy",
                "policy": policy,
                "chars": len(token),
                "baseline_chars": baseline,
                "encode_us": enc_us,
                "decode_us": dec_us,
                "error": metrics,
            }


def summarize(rows, group_keys, size_key, baseline_key):
    groups = defaultdict(list)
    for row in rows:
        if "skip" not in row:
            groups[tuple(row[k] for k in group_keys)].append(row)
    output = []
    for keys, group in sorted(groups.items()):
        total = sum(r[size_key] for r in group)
        baseline = sum(r[baseline_key] for r in group)
        ratios = [r[size_key] / r[baseline_key] for r in group]
        output.append(
            {
                **dict(zip(group_keys, keys, strict=True)),
                "n": len(group),
                "total": total,
                "baseline_total": baseline,
                "saving_pct": 100 * (1 - total / baseline),
                "median_saving_pct": 100 * (1 - statistics.median(ratios)),
                "worst_growth_pct": 100 * (max(ratios) - 1),
                "wins": sum(r[size_key] < r[baseline_key] for r in group),
                "encode_us_total": sum(r["encode_us"] for r in group),
                "decode_us_total": sum(r["decode_us"] for r in group),
            }
        )
    return output


def self_check():
    rng = np.random.default_rng(927)
    for width in (4, 8):
        for n in (0, 1, 2, 3, 127):
            raw = rng.bytes(width * n)
            for name in TRANSFORMS:
                assert transform(transform(raw, width, name), width, name, inverse=True) == raw
    special = np.array([0.0, -0.0, np.inf, -np.inf, np.nan, np.nextafter(0.0, 1.0), -1.0, 1.0], dtype="<f8")
    for name in TRANSFORMS:
        raw = special.tobytes()
        assert transform(transform(raw, 8, name), 8, name, inverse=True) == raw
    # A concrete counterexample to treating floating-point differences as lossless.
    values = np.array([1e-20, 1.0, 1e20])
    restored = np.cumsum(np.r_[values[0], np.diff(values)])
    # Use a cancellation case if this monotonic example happens to be exact.
    values = np.array([1.0, 1e20, 1.0]) if restored.tobytes() == values.tobytes() else values
    restored = np.cumsum(np.r_[values[0], np.diff(values)])
    assert restored.tobytes() != values.tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--paths", nargs="+", type=Path, default=[Path("tests/data/BSA1.mzML")])
    parser.add_argument("--per-group", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("experiments/encoding/results.json"))
    parser.add_argument("--rows", type=Path, help="Optional detailed JSON results, potentially large")
    parser.add_argument("--compressors", nargs="+", help="Run a subset of compressor names")
    args = parser.parse_args()
    if args.per_group < 1 or args.repeats < 1:
        parser.error("per-group and repeats must be positive")
    self_check()
    engines = compressors()
    if args.compressors:
        engines = {key: engines[key] for key in args.compressors}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        samples, provenance = load_samples(args)
        if not samples:
            raise ValueError("no nonempty spectra selected")
        pipelines, tokens = [], []
        for i, sample in enumerate(samples):
            print(f"[{i + 1}/{len(samples)}] {sample.dataset}: {sample.source.default_array_length} peaks", flush=True)
            pipelines.extend(pipeline_rows(sample, args.repeats, engines))
            tokens.extend(token_rows(sample, args.repeats))
    result = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "numpress_backend": active_backend(),
            "repeats": args.repeats,
            "packages": {p: importlib.metadata.version(p) for p in ("numpy", "zstandard", "mzmlpy")},
            "compressors": list(engines),
            "zlib": zlib.ZLIB_RUNTIME_VERSION,
        },
        "provenance": provenance,
        "spectra": len(samples),
        "pipeline_rows": len(pipelines),
        "pipeline_summary": summarize(pipelines, ["mode", "transform", "compressor"], "bytes", "baseline_bytes"),
        "pipeline_by_array": summarize(
            pipelines, ["mode", "array", "transform", "compressor"], "bytes", "baseline_bytes"
        ),
        "pipeline_by_representation": summarize(
            pipelines, ["mode", "representation", "transform", "compressor"], "bytes", "baseline_bytes"
        ),
        "token_summary": summarize(tokens, ["mode", "policy"], "chars", "baseline_chars"),
        "token_by_dataset": summarize(tokens, ["dataset", "mode", "policy"], "chars", "baseline_chars"),
        "token_rows": tokens,
    }
    if args.rows:
        args.rows.write_text(json.dumps({"pipelines": pipelines, "tokens": tokens}, indent=2) + "\n")
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["token_summary"], indent=2))


if __name__ == "__main__":
    main()
