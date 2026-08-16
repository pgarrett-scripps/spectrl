"""The pure-Python numpress backend is byte-for-byte identical to pynumpress.

This is what makes the Pyodide / browser fallback safe: a token encoded where
``pynumpress`` is unavailable must be indistinguishable from one encoded with it
(same bytes, same SHA-256 content hash), and either backend must decode the
other's output. If these ever drift, tokens stop interoperating across
implementations.
"""

from __future__ import annotations

import numpy as np
import pytest

from spectrl import decode_token, encode_spectrum
from spectrl.codecs.numpress import (
    DEFAULT_NUMLIN_FP,
    DEFAULT_NUMSLOF_FP,
    _PurePythonBackend,
    _PynumpressBackend,
)

pynumpress = pytest.importorskip("pynumpress")


@pytest.fixture
def backends():
    return _PynumpressBackend(pynumpress), _PurePythonBackend()


@pytest.mark.parametrize("seed", range(25))
def test_linear_encode_byte_identical(backends, seed):
    c, py = backends
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 60))
    mz = np.sort(rng.uniform(100.0, 2000.0, n)).astype(np.float64) if n else np.empty(0)
    a = c.encode_linear(mz, DEFAULT_NUMLIN_FP)
    b = py.encode_linear(mz, DEFAULT_NUMLIN_FP)
    np.testing.assert_array_equal(a, b)
    # each backend decodes the other's blob to the same values
    np.testing.assert_allclose(c.decode_linear(b), py.decode_linear(a), atol=1e-6)


@pytest.mark.parametrize("seed", range(25))
def test_slof_encode_byte_identical(backends, seed):
    c, py = backends
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 60))
    inten = rng.uniform(0.0, 1e6, n).astype(np.float64) if n else np.empty(0)
    a = c.encode_slof(inten, DEFAULT_NUMSLOF_FP)
    b = py.encode_slof(inten, DEFAULT_NUMSLOF_FP)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_allclose(c.decode_slof(b), py.decode_slof(a), atol=1e-6)


@pytest.mark.parametrize("seed", range(25))
def test_pic_encode_byte_identical(backends, seed):
    c, py = backends
    rng = np.random.default_rng(seed)
    n = int(rng.integers(0, 60))
    vals = rng.integers(0, 5_000_000, n).astype(np.float64) if n else np.empty(0)
    a = c.encode_pic(vals)
    b = py.encode_pic(vals)
    np.testing.assert_array_equal(a, b)
    np.testing.assert_array_equal(c.decode_pic(b), py.decode_pic(a))


def test_single_value_linear_roundtrips_in_pure_backend():
    """The single-peak linear blob (the pynumpress decode gap) is native here."""
    py = _PurePythonBackend()
    blob = py.encode_linear(np.array([723.4141]), DEFAULT_NUMLIN_FP)
    np.testing.assert_allclose(py.decode_linear(blob), [723.4141], atol=1e-4)


def test_token_and_hash_identical_across_backends(monkeypatch, ms2_spectrum):
    """A full token (and its content hash) is the same whichever backend encodes it."""
    import spectrl.codecs.numpress as npmod

    def _with_backend(name):
        npmod._BACKEND = None
        monkeypatch.setenv("SPECTRL_NUMPRESS_BACKEND", name)
        try:
            return encode_spectrum(ms2_spectrum)
        finally:
            npmod._BACKEND = None

    tok_c = _with_backend("pynumpress")
    tok_py = _with_backend("python")
    assert tok_c == tok_py
    assert decode_token(tok_c).hash == decode_token(tok_py).hash
