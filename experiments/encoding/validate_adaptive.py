"""Validate the production adaptive default against the recorded corpus search."""

import argparse
import json
import statistics
import warnings
from pathlib import Path

from benchmark import arrays, load_samples

from spectrl import decode_token, encode_spectrum, spectrum_to_dict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--per-group", type=int, default=3)
    parser.add_argument("--recorded", type=Path, default=Path("experiments/encoding/results.json"))
    parser.add_argument("--output", type=Path, default=Path("experiments/encoding/adaptive-validation.json"))
    args = parser.parse_args()
    recorded = json.loads(args.recorded.read_text())
    expected = {
        (row["dataset"], row["id"]): row["chars"]
        for row in recorded["token_rows"]
        if row["mode"] == "lossless" and row["policy"] == "adaptive"
    }
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        samples, _ = load_samples(args)
        for sample in samples:
            spec = sample.source
            source = arrays(spec)
            token = encode_spectrum(spec, lossless=True)
            baseline = encode_spectrum(spec, lossless=True, array_encodings=dict.fromkeys(source, "zlib"))
            assert len(token) == expected[sample.dataset, spec.id]
            assert len(token) <= len(baseline)
            decoded = decode_token(token)
            recovered = arrays(decoded)
            for key, values in source.items():
                assert recovered[key].astype(values.dtype).tobytes() == values.tobytes(), (sample.dataset, key)
            # Both decoders canonicalize metadata order, allowing a direct comparison.
            assert spectrum_to_dict(decoded) == spectrum_to_dict(decode_token(baseline)), sample.dataset
            rows.append(
                {
                    "dataset": sample.dataset,
                    "id": spec.id,
                    "baseline_chars": len(baseline),
                    "adaptive_chars": len(token),
                }
            )
    summary = {
        "spectra": len(rows),
        "all_arrays_bit_exact": True,
        "all_metadata_equal_to_zlib": True,
        "matches_prior_exhaustive_selector": True,
        "size_regressions": 0,
        "total_saving_pct": 100 * (1 - sum(r["adaptive_chars"] for r in rows) / sum(r["baseline_chars"] for r in rows)),
        "median_saving_pct": statistics.median(100 * (1 - r["adaptive_chars"] / r["baseline_chars"]) for r in rows),
    }
    args.output.write_text(json.dumps({"summary": summary, "spectra": rows}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
