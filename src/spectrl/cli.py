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
    from .serialization import spectrum_from_dict

    try:
        data = json.loads(_read_input(args.input))
    except json.JSONDecodeError as e:
        raise SystemExit(f"spectrl encode: input is not valid JSON: {e}") from None
    try:
        spec = spectrum_from_dict(data)
    except (KeyError, TypeError, ValueError) as e:
        raise SystemExit(
            f"spectrl encode: bad input ({e}); expected a spectrum object produced by 'spectrl decode'"
        ) from None
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
    )
    print(token)


def _decode_cmd(args: argparse.Namespace) -> None:
    from . import SpectrlDecodeError, decode_token

    token = _read_input(args.input).strip()
    try:
        decoded = decode_token(token)
    except SpectrlDecodeError as e:
        raise SystemExit(f"spectrl decode: {e}") from None
    from .serialization import spectrum_to_dict

    out = spectrum_to_dict(decoded)
    print(json.dumps(out, indent=2))


def _inspect_cmd(args: argparse.Namespace) -> None:
    import cbor2

    from .cbor_format import token_checksum
    from .header import DESC_DATA
    from .introspection import inspect_token
    from .token import MAGIC, b64url_decode

    token = _read_input(args.input).strip()
    prefix = f"{MAGIC}."
    if not token.startswith(prefix):
        raise SystemExit(f"Not a {MAGIC} token.")
    parts = token[len(prefix) :].split(".")
    if len(parts) != 2 or parts[1] != token_checksum(f"{MAGIC}.{parts[0]}"):
        raise SystemExit(f"Not a {MAGIC} token.")
    raw = b64url_decode(parts[0])
    doc = cbor2.loads(raw)
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="spectrl", description="spectrl inline spectrum encoder/decoder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode", help="Encode a spectrum JSON to a spectrl.v1 token")
    enc.add_argument("input", nargs="?", default="-", help="Input JSON file or '-' for stdin")
    enc.add_argument("--lossless", action="store_true", help="Use lossless IEEE-754 + zlib encoding")
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
    dec.set_defaults(func=_decode_cmd)

    ins = sub.add_parser("inspect", help="Inspect a spectrl.v1 token header as readable JSON")
    ins.add_argument("input", nargs="?", default="-", help="Token file or '-' for stdin")
    ins.set_defaults(func=_inspect_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
