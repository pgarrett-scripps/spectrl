"""Exercise real mzML spectra through import, encode, and decode."""

from __future__ import annotations

import argparse
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from mzmlpy.spectra import Spectrum

from spectrl import decode_token, encode_spectrum, from_mzmlpy


def check_file(path: Path, limit: int) -> int:
    checked = 0
    for _event, element in ET.iterparse(path, events=("end",)):
        if element.tag.rsplit("}", 1)[-1] != "spectrum":
            continue
        source = Spectrum(element)
        inline = from_mzmlpy(source)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            decoded = decode_token(encode_spectrum(inline, lossless=checked == 0))
        assert decoded.id == inline.id
        assert decoded.default_array_length == inline.default_array_length
        assert set(decoded.extra_arrays) == set(inline.extra_arrays)
        assert decoded.array_units == inline.array_units
        for array in (decoded.mz, decoded.intensity, decoded.charge, *decoded.extra_arrays.values()):
            if array is not None:
                assert len(array) == inline.default_array_length
                assert bool(np.isfinite(array).all())
        checked += 1
        element.clear()
        if checked >= limit:
            break
    if checked == 0:
        raise RuntimeError(f"{path} contained no spectra")
    print(f"{path}: {checked} spectra passed")
    return checked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    total = sum(check_file(path, args.limit) for path in args.paths)
    print(f"Real mzML smoke test passed for {total} spectra across {len(args.paths)} files")


if __name__ == "__main__":
    main()
