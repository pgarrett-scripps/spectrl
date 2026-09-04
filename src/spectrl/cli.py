"""CLI for spectrl: encode, decode, and inspect tokens."""

from __future__ import annotations

import argparse
import json
import sys


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path) as f:
        return f.read()


def _encode_cmd(args: argparse.Namespace) -> None:
    from . import encode_spectrum

    spec = _input_spectrum(args)
    array_encodings = {}
    for item in args.array_encoding:
        key, separator, codec = item.partition("=")
        if not separator or not key or not codec:
            raise SystemExit("spectrl encode: --array-encoding must be ARRAY=CODEC")
        array_encodings[key] = codec
    token = encode_spectrum(
        spec,
        lossless=args.lossless,
        max_len=args.max_len,
        array_encodings=array_encodings,
        allow_unsafe_lossy_custom=args.allow_unsafe_lossy_custom,
        drop_user_params=args.drop_user_params,
    )
    print(token)


def _decode_cmd(args: argparse.Namespace) -> None:
    from . import SpectrlDecodeError, decode_token

    token = _input_token(args.input)
    try:
        decoded = decode_token(token)
    except SpectrlDecodeError as e:
        raise SystemExit(f"spectrl decode: {e}") from None
    from .serialization import spectrum_to_dict

    if args.output_format == "json":
        print(json.dumps(spectrum_to_dict(decoded), indent=2, allow_nan=False))
    else:
        from .peaklist import format_peak_list

        print(format_peak_list(decoded, delimiter="," if args.output_format == "csv" else "\t"), end="")


def _inspect_cmd(args: argparse.Namespace) -> None:
    from .cbor_format import read_token_document
    from .header import DESC_DATA
    from .introspection import inspect_token
    from .token import b64url_decode

    token = _input_token(args.input)
    doc, _ = read_token_document(token)
    raw = b64url_decode(token.split(".")[2])
    arrays = doc.get(6, [])
    print(f"CBOR document: {len(raw)} bytes ({len(arrays)} array(s))")
    for i, info in enumerate(inspect_token(token)):
        unit = f" unit={info['unit_accession']}" if "unit_accession" in info else ""
        fp = f" fp={info['fixed_point']}" if info["fixed_point"] is not None else ""
        print(
            f"  array {i}: {info['accession']} type={info['type_accession']} "
            f"comp={info['compression_accession']}{fp}{unit} blob={info['compressed_bytes']} bytes"
        )

    # Show the header without the (large) embedded blobs.
    def _strip(o):
        if isinstance(o, dict):
            return {
                k: (f"<{len(v)} bytes>" if k == DESC_DATA and isinstance(v, bytes) else _strip(v)) for k, v in o.items()
            }
        if isinstance(o, list):
            return [_strip(x) for x in o]
        return o

    print("Header (decoded):")
    print(json.dumps(_strip(doc), indent=2, default=str))


def _input_token(path: str) -> str:
    from . import extract_token

    value = _read_input(path).strip()
    return value if value.startswith("spectrl.v1.") else extract_token(value)


def _input_spectrum(args):
    from .peaklist import parse_peak_list
    from .serialization import spectrum_from_dict

    text = _read_input(args.input)
    if args.input_format == "json":
        return spectrum_from_dict(json.loads(text))
    delimiter = {"csv": ",", "tsv": "\t", "text": None}[args.input_format]
    return parse_peak_list(text, delimiter=delimiter)


def _report_cmd(args):
    from .workflows import encoding_report

    result = encoding_report(_input_spectrum(args), lossless=args.lossless, drop_user_params=args.drop_user_params)
    print(json.dumps(result, indent=2, allow_nan=False))


def _fit_cmd(args):
    from .serialization import spectrum_to_dict
    from .workflows import fit_to_budget

    result = fit_to_budget(
        _input_spectrum(args),
        args.max_bytes,
        base_url=args.base_url,
        allow_peak_trimming=args.allow_peak_trimming,
        min_peaks=args.min_peaks,
        lossless=args.lossless,
        drop_user_params=args.drop_user_params,
    )
    result["spectrum"] = spectrum_to_dict(result["spectrum"])
    print(json.dumps(result, indent=2, allow_nan=False))


def _mzml_cmd(args):
    from mzmlpy.run import Mzml

    from . import conversion_report
    from .serialization import spectrum_to_dict
    from .workflows import encoding_report

    if args.index < 0:
        raise ValueError("index must be non-negative")
    with Mzml(args.input) as mzml:
        if args.index >= len(mzml.spectra):
            raise ValueError("spectrum index is out of range")
        groups = mzml.referenceable_param_groups
        report = conversion_report(mzml.spectra[args.index], groups, strict=args.strict)
        report["encoding"] = encoding_report(report["spectrum"], lossless=args.lossless)
        report["spectrum"] = spectrum_to_dict(report["spectrum"])
    print(json.dumps(report, indent=2, allow_nan=False))


def _spectrum_input(parser):
    parser.add_argument("input", nargs="?", default="-", help="Input spectrum file or '-' for stdin")
    parser.add_argument("--input-format", choices=["json", "text", "csv", "tsv"], default="json")
    parser.add_argument("--lossless", action="store_true", help="Preserve exact array values")
    parser.add_argument("--drop-user-params", action="store_true", help="Explicitly omit free-text user parameters")


def main() -> None:
    parser = argparse.ArgumentParser(prog="spectrl", description="spectrl inline spectrum encoder/decoder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode", help="Encode a spectrum JSON to a spectrl.v1 token")
    _spectrum_input(enc)
    enc.add_argument("--max-len", type=int, default=None, help="Maximum token length in bytes")
    enc.add_argument(
        "--array-encoding",
        action="append",
        default=[],
        metavar="ARRAY=CODEC",
        help="Override an array codec, for example mz=numlin-zstd. Repeat for multiple arrays.",
    )
    enc.add_argument(
        "--allow-unsafe-lossy-custom",
        action="store_true",
        help="Allow explicit lossy codecs for semantically unknown custom arrays.",
    )
    enc.set_defaults(func=_encode_cmd)

    dec = sub.add_parser("decode", help="Decode a spectrl.v1 token to JSON")
    dec.add_argument("input", nargs="?", default="-", help="Token file or '-' for stdin")
    dec.add_argument(
        "--output-format", choices=["json", "csv", "tsv"], default="json", help="CSV/TSV exports only m/z and intensity"
    )
    dec.set_defaults(func=_decode_cmd)

    ins = sub.add_parser("inspect", help="Inspect a spectrl.v1 token header as readable JSON")
    ins.add_argument("input", nargs="?", default="-", help="Token file or '-' for stdin")
    ins.set_defaults(func=_inspect_cmd)

    report = sub.add_parser("report", help="Encode a spectrum and report measured errors and sizes")
    _spectrum_input(report)
    report.set_defaults(func=_report_cmd)

    fit = sub.add_parser("fit", help="Find a candidate within a token or URL byte budget")
    _spectrum_input(fit)
    fit.add_argument("--max-bytes", type=int, required=True)
    fit.add_argument("--base-url", help="Include this fragment carrier URL in the budget")
    fit.add_argument("--allow-peak-trimming", action="store_true")
    fit.add_argument("--min-peaks", type=int, default=1)
    fit.set_defaults(func=_fit_cmd)

    mzml = sub.add_parser("convert-mzml", help="Convert one mzML spectrum and report fidelity")
    mzml.add_argument("input")
    mzml.add_argument("--index", type=int, default=0, help="Zero-based spectrum index")
    mzml.add_argument("--strict", action="store_true")
    mzml.add_argument("--lossless", action="store_true")
    mzml.set_defaults(func=_mzml_cmd)

    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, OSError, ImportError) as exc:
        parser.exit(2, f"spectrl {args.cmd}: {exc}\n")


if __name__ == "__main__":
    main()
