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
    import numpy as np

    from . import encode_spectrum
    from .model import InlineSpectrum, SpectrlCvParam

    try:
        data = json.loads(_read_input(args.input))
    except json.JSONDecodeError as e:
        raise SystemExit(f"spectrl encode: input is not valid JSON: {e}") from None
    try:
        mz = np.array(data["mz"], dtype=np.float64)
        intensity = np.array(data["intensity"], dtype=np.float64)
        params = [SpectrlCvParam(**p) for p in data.get("params", [])]
    except (KeyError, TypeError, ValueError) as e:
        raise SystemExit(
            f"spectrl encode: bad input ({e}); expected "
            '{"mz": [...], "intensity": [...], "id"?: str, "params"?: [{"accession": ..., "value"?: ...}]}'
        ) from None
    spec = InlineSpectrum(
        default_array_length=len(mz),
        mz=mz,
        intensity=intensity,
        id=data.get("id"),
        params=params,
    )
    token = encode_spectrum(spec, lossless=args.lossless, max_len=args.max_len)
    print(token)


def _decode_cmd(args: argparse.Namespace) -> None:
    from . import SpectrlDecodeError, decode_token

    token = _read_input(args.input).strip()
    try:
        decoded = decode_token(token)
    except SpectrlDecodeError as e:
        raise SystemExit(f"spectrl decode: {e}") from None
    out: dict = {
        "id": decoded.id,
        "default_array_length": decoded.default_array_length,
        "mz": decoded.mz.tolist() if decoded.mz is not None else None,
        "intensity": decoded.intensity.tolist() if decoded.intensity is not None else None,
        "charge": decoded.charge.tolist() if decoded.charge is not None else None,
        "hash": decoded.hash,
        "interp": decoded.interp,
    }
    print(json.dumps(out, indent=2))


def _inspect_cmd(args: argparse.Namespace) -> None:
    import cbor2

    from .header import DESC_ARRAY, DESC_COMP, DESC_DATA
    from .token import MAGIC, b64url_decode

    token = _read_input(args.input).strip()
    parts = token.split(".")
    if parts[0] != MAGIC or len(parts) not in (2, 3):
        raise SystemExit(f"Not a {MAGIC} token.")
    raw = b64url_decode(parts[1])
    doc = cbor2.loads(raw)
    arrays = doc.get(6, [])
    print(f"CBOR document: {len(raw)} bytes ({len(arrays)} array(s))")
    for i, desc in enumerate(arrays):
        blob = desc.get(DESC_DATA, b"")
        print(f"  array {i}: tail={desc.get(DESC_ARRAY)} comp={desc.get(DESC_COMP)} blob={len(blob)} bytes")

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

    enc = sub.add_parser("encode", help="Encode a spectrum JSON to a spectrl2 token")
    enc.add_argument("input", nargs="?", default="-", help="Input JSON file or '-' for stdin")
    enc.add_argument("--lossless", action="store_true", help="Use lossless IEEE-754 + zlib encoding")
    enc.add_argument("--max-len", type=int, default=None, help="Maximum token length in bytes")
    enc.set_defaults(func=_encode_cmd)

    dec = sub.add_parser("decode", help="Decode a spectrl2 token to JSON")
    dec.add_argument("input", nargs="?", default="-", help="Token file or '-' for stdin")
    dec.set_defaults(func=_decode_cmd)

    ins = sub.add_parser("inspect", help="Inspect a spectrl2 token header as readable JSON")
    ins.add_argument("input", nargs="?", default="-", help="Token file or '-' for stdin")
    ins.set_defaults(func=_inspect_cmd)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
