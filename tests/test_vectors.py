"""Conformance vectors: the cross-implementation contract.

The Python reference impl must decode every vector token and reproduce the
recorded values, for BOTH directions:

  * vectors.json          tokens encoded by Python, decoded by everyone
  * reverse-vectors.json  tokens encoded by the JS impl (proves JS → Python)

Together these demonstrate bidirectional interoperability.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from spectrl import decode_token
from spectrl.token import b64url_encode

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "test-vectors" / "vectors.json"
REVERSE = ROOT / "test-vectors" / "reverse-vectors.json"
NEGATIVE = ROOT / "test-vectors" / "negative-vectors.json"
GENERATOR = ROOT / "scripts" / "gen_vectors.py"


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _close(a: float, e: float, tol: dict) -> bool:
    return abs(a - e) <= tol["abs"] + tol["rel"] * abs(e)


def _cmp_params(actual: list, expected: list, tol: dict, label: str) -> None:
    assert len(actual) == len(expected), f"{label}: param count {len(actual)} != {len(expected)}"
    for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
        assert a.accession == e["accession"], f"{label}[{i}].accession"
        av, ev = a.value, e["value"]
        if isinstance(ev, (int, float)) and not isinstance(ev, bool) and isinstance(av, (int, float)):
            assert _close(float(av), float(ev), tol), f"{label}[{i}].value {av} != {ev}"
        else:
            assert av == ev, f"{label}[{i}].value {av!r} != {ev!r}"
        assert (a.unit_accession or None) == (e["unit_accession"] or None), f"{label}[{i}].unit"


def _cmp_user_params(actual: list, expected: list, label: str) -> None:
    assert len(actual) == len(expected), f"{label}: user-param count {len(actual)} != {len(expected)}"
    for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
        assert a.name == e["name"], f"{label}[{i}].name"
        assert a.value == e["value"], f"{label}[{i}].value {a.value!r} != {e['value']!r}"
        assert (a.type or None) == (e["type"] or None), f"{label}[{i}].type"
        assert (a.unit_accession or None) == (e["unit_accession"] or None), f"{label}[{i}].unit"


def _check(vec: dict) -> None:
    tol = vec["tolerance"]
    d = decode_token(vec["token"])  # raises on hash mismatch
    exp = vec["decoded"]

    assert d.default_array_length == exp["default_array_length"]
    assert d.id == exp["id"]
    assert d.hash == exp["hash"]
    assert d.interp == exp["interp"]
    assert d.ion_mobility_type == exp["ion_mobility_type"]
    assert d.format_version == exp["format_version"]

    for name, attr in [
        ("mz", d.mz),
        ("intensity", d.intensity),
        ("charge", d.charge),
        ("ion_mobility", d.ion_mobility),
    ]:
        expected = exp[name]
        if expected is None:
            assert attr is None, name
            continue
        assert attr is not None and len(attr) == len(expected), name
        for a, e in zip(attr, expected, strict=True):
            assert _close(float(a), float(e), tol), f"{name}: {a} vs {e}"
            assert math.isfinite(float(a))

    _cmp_params(d.params, exp["params"], tol, "params")

    assert len(d.scans) == len(exp["scans"]), "scan count"
    for i, (asc, esc) in enumerate(zip(d.scans, exp["scans"], strict=True)):
        _cmp_params(asc.params, esc["params"], tol, f"scan[{i}].params")
        ew = esc.get("windows", [])
        assert len(asc.windows) == len(ew), f"scan[{i}] window count"
        for j, (aw, ewin) in enumerate(zip(asc.windows, ew, strict=True)):
            _cmp_params(aw.params, ewin["params"], tol, f"scan[{i}].window[{j}]")
        _cmp_user_params(asc.user_params, esc.get("user_params", []), f"scan[{i}].user_params")

    _cmp_user_params(d.user_params, exp.get("user_params", []), "user_params")

    assert len(d.precursors) == len(exp["precursors"]), "precursor count"
    for i, (ap, ep) in enumerate(zip(d.precursors, exp["precursors"], strict=True)):
        if ep["isolation_window"]:
            _cmp_params(ap.isolation_window.params, ep["isolation_window"]["params"], tol, f"precursor[{i}].isoWin")
        assert len(ap.selected_ions) == len(ep["selected_ions"]), f"precursor[{i}] selIon count"
        for j, (asi, esi) in enumerate(zip(ap.selected_ions, ep["selected_ions"], strict=True)):
            _cmp_params(asi.params, esi["params"], tol, f"precursor[{i}].selIon[{j}]")
        if ep["activation"]:
            _cmp_params(ap.activation.params, ep["activation"]["params"], tol, f"precursor[{i}].activation")

    assert len(d.products) == len(exp["products"]), "product count"
    for i, (apr, epr) in enumerate(zip(d.products, exp["products"], strict=True)):
        if epr["isolation_window"]:
            _cmp_params(apr.isolation_window.params, epr["isolation_window"]["params"], tol, f"product[{i}].isoWin")

    exp_extra = exp.get("extra_arrays", {})
    assert set(d.extra_arrays) == set(exp_extra), f"extra_arrays keys {set(d.extra_arrays)} != {set(exp_extra)}"
    for k, ee in exp_extra.items():
        ea = d.extra_arrays[k]
        assert str(ea.dtype) == ee["dtype"], f"extra[{k}].dtype {ea.dtype} != {ee['dtype']}"
        assert len(ea) == len(ee["values"]), f"extra[{k}] length"
        for a, e in zip(ea, ee["values"], strict=True):
            assert _close(float(a), float(e), tol), f"extra[{k}]: {a} vs {e}"


# ── forward: Python-authored tokens ───────────────────────────────────────────


def test_vectors_file_exists():
    assert VECTORS.exists(), "test-vectors/vectors.json missing; run: uv run python scripts/gen_vectors.py"


@pytest.mark.parametrize("vec", _load(VECTORS)["vectors"], ids=lambda v: f"fwd-{v['name']}-{v['mode']}")
def test_forward_vector_decodes(vec: dict):
    _check(vec)


# ── reverse: JS-authored tokens (proves JS → Python interop) ──────────────────

_REVERSE_VECS = _load(REVERSE)["vectors"] if REVERSE.exists() else []


@pytest.mark.skipif(not _REVERSE_VECS, reason="reverse-vectors.json not generated (run: cd js && npm run gen-vectors)")
@pytest.mark.parametrize("vec", _REVERSE_VECS, ids=lambda v: f"rev-{v['name']}-{v['mode']}")
def test_reverse_vector_decodes(vec: dict):
    """Python decodes a token the JavaScript implementation produced."""
    _check(vec)


def test_vectors_in_sync_with_generator(tmp_path):
    """Regenerate the vectors to a temp file and diff against the committed file."""
    out = tmp_path / "vectors.json"
    result = subprocess.run([sys.executable, str(GENERATOR), str(out)], capture_output=True, text=True)
    assert result.returncode == 0, f"generator failed:\n{result.stderr}"
    fresh = _load(out)
    assert fresh["vectors"], "no vectors generated"
    committed = _load(VECTORS)
    # generated_by embeds the installed version; compare everything else
    fresh.pop("generated_by"), committed.pop("generated_by")
    assert fresh == committed, "test-vectors/vectors.json is out of date; run: uv run python scripts/gen_vectors.py"


@pytest.mark.parametrize("vec", _load(NEGATIVE)["vectors"], ids=lambda v: f"negative-{v['name']}")
def test_shared_negative_vector_rejected(vec: dict):
    token = "spectrl2." + b64url_encode(bytes.fromhex(vec["cbor_hex"]))
    with pytest.raises(ValueError, match=vec["error"]):
        decode_token(token)
