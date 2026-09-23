"""Versioned numeric array encodings for spectrl v3."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ._format import MAX_BLOB_BYTES, MAX_SAFE_INTEGER
from .codecs import quantized, rounded
from .codecs._delta import delta_shuffle, delta_unshuffle
from .codecs.raw import _np_dtype
from .codecs.shuffle import shuffle
from .cv import TYPE_FLOAT32, TYPE_FLOAT64

DESC_ENCODING = 2
DESC_FIDELITY = 7
DESC_PARAMS = 8
DESC_USER_PARAMS = 9
DESC_PROCESSING = 10
DESC_EXTENSIONS = 11

ENCODING_NAMES = {"raw": 0, "byte-shuffle": 1, "modular-delta-shuffle": 2, "quantized": 3, "rounded-float": 4}
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z0-9._/-]+$")


def descriptor(value, names=None):
    """Normalize public operation settings or validate a wire tuple."""
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value, 1]
    elif isinstance(value, dict):
        if set(value) - {"id", "revision", "parameters"} or "id" not in value:
            raise ValueError("invalid operation descriptor")
        value = [value["id"], value.get("revision", 1), value.get("parameters", {})]
    if not isinstance(value, list) or len(value) not in (2, 3):
        raise ValueError("operation must be [identifier, revision, optional parameters]")
    identifier, revision = value[:2]
    if names and isinstance(identifier, str):
        identifier = names.get(identifier.removeprefix("spectrl:"), identifier)
    if not (
        (type(identifier) is int and 0 <= identifier <= MAX_SAFE_INTEGER)
        or (isinstance(identifier, str) and _ID.fullmatch(identifier))
    ):
        raise ValueError("operation identifier must be a built-in integer or namespaced string")
    if type(revision) is not int or not 1 <= revision <= MAX_SAFE_INTEGER:
        raise ValueError("operation revision must be a positive safe integer")
    params = value[2] if len(value) == 3 else {}
    if not isinstance(params, dict) or not all(isinstance(k, str) for k in params):
        raise ValueError("operation parameters must be a string-keyed map")
    return [identifier, revision, params] if params else [identifier, revision]


@dataclass(frozen=True)
class Encoding:
    """Callbacks encode(array, type, parameters) and decode(bytes, type, count, parameters)."""

    encode: Callable
    decode: Callable
    validate: Callable
    lossless: bool = True
    types: tuple[int, ...] = (1000521, 1000523, 1000519)


ENCODINGS: dict[tuple[int | str, int], Encoding] = {}


def _register(registry, identifier, implementation, revision):
    desc = descriptor([identifier, revision])
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier) or identifier.startswith("spectrl:"):
        raise ValueError("custom registrations require a non-spectrl namespaced identifier")
    key = tuple(desc[:2])
    if key in registry:
        raise ValueError(f"operation is already registered: {identifier}@{revision}")
    registry[key] = implementation


def register_encoding(identifier: str, implementation: Encoding, *, revision: int = 1):
    if not isinstance(implementation, Encoding):
        raise TypeError("implementation must be an Encoding")
    _register(ENCODINGS, identifier, implementation, revision)


def operation(registry, desc):
    desc = descriptor(desc)
    try:
        impl = registry[tuple(desc[:2])]
    except KeyError:
        raise ValueError(f"unsupported operation {desc[0]!r} revision {desc[1]}") from None
    params = desc[2] if len(desc) == 3 else {}
    impl.validate(params)
    return impl, params


def _empty(params):
    if params:
        raise ValueError("this operation does not accept parameters")


def _raw(data, tail, params):
    return np.asarray(data).astype(_np_dtype(tail)).tobytes()


def _from_raw(raw, tail, n, params):
    dtype = np.dtype(_np_dtype(tail))
    if len(raw) != n * dtype.itemsize:
        raise ValueError("decoded byte length does not match dtype and count")
    return np.frombuffer(raw, dtype).copy()


def _transform(forward, inverse):
    return Encoding(
        lambda a, t, p: forward(_raw(a, t, p), np.dtype(_np_dtype(t)).itemsize),
        lambda b, t, n, p: _from_raw(inverse(b, np.dtype(_np_dtype(t)).itemsize), t, n, p),
        _empty,
    )


ENCODINGS.update(
    {
        (0, 1): Encoding(_raw, _from_raw, _empty),
        (1, 1): _transform(shuffle, lambda b, w: shuffle(b, w, inverse=True)),
        (2, 1): _transform(delta_shuffle, delta_unshuffle),
        (3, 1): Encoding(quantized.encode, quantized.decode, quantized.validate, False, (TYPE_FLOAT32, TYPE_FLOAT64)),
        (4, 1): Encoding(rounded.encode, rounded.decode, rounded.validate, False, (TYPE_FLOAT32, TYPE_FLOAT64)),
    }
)


def encode_pipeline(data, tail, enc):
    encoding, params = operation(ENCODINGS, enc)
    if tail not in encoding.types:
        raise ValueError("encoding does not support the declared dtype")
    blob = encoding.encode(data, tail, params)
    if not isinstance(blob, bytes) or len(blob) > min(MAX_BLOB_BYTES, 64 + 16 * len(data)):
        raise ValueError("encoding exceeds the intermediate byte limit")
    return blob, 0 if encoding.lossless else 1


def decode_pipeline(blob, tail, count, enc, fidelity):
    encoding, params = operation(ENCODINGS, enc)
    if tail not in encoding.types or fidelity != (0 if encoding.lossless else 1):
        raise ValueError("encoding dtype or fidelity declaration mismatch")
    if len(blob) > min(MAX_BLOB_BYTES, 64 + 16 * count):
        raise ValueError("encoded data exceeds byte limit")
    result = encoding.decode(blob, tail, count, params)
    if not isinstance(result, np.ndarray) or result.ndim != 1 or len(result) != count:
        raise ValueError("encoding returned an invalid array shape")
    if result.dtype != np.dtype(_np_dtype(tail)):
        raise ValueError("encoding returned an incorrect dtype")
    return result
