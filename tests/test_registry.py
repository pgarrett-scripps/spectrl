"""Registry stays in sync with the live CV constants."""

import json
import subprocess
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "schema" / "registry.json"
GENERATOR = Path(__file__).parent.parent / "scripts" / "generate_registry.py"


def _load() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def test_registry_file_exists():
    assert REGISTRY_PATH.exists(), "schema/registry.json is missing; run: just registry"


def test_registry_is_valid_json():
    r = _load()
    assert isinstance(r, dict)


def test_registry_has_required_top_level_keys():
    r = _load()
    required = (
        "spectrl_version",
        "wire_constants",
        "token_format",
        "header_keys",
        "encodings",
        "data_types",
        "array_types",
        "cvparam_encoding",
        "canonical_form",
    )
    for key in required:
        assert key in r, f"Missing top-level key: {key}"


def test_registry_in_sync_with_generator(tmp_path):
    """Regenerate the registry to a temp file and diff against the committed file."""
    out = tmp_path / "registry.json"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), str(out)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Generator failed:\n{result.stderr}"
    fresh = json.loads(out.read_text())
    committed = _load()
    assert fresh == committed, "schema/registry.json is out of date; run: just registry"


def test_generated_format_modules_are_current():
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check-generated"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_all_header_keys_present():
    r = _load()
    keys = set(int(k) for k in r["header_keys"])
    assert keys == set(range(13))


def test_magic_matches_token_module():
    from spectrl.token import FORMAT_VERSION, MAGIC

    r = _load()
    assert r["token_format"]["magic"] == MAGIC
    assert r["spectrl_version"] == FORMAT_VERSION


def test_payload_presets_only_name_supported_modes():
    framing = json.loads(REGISTRY_PATH.read_text())["token_format"]
    assert set(framing["presets"]) <= set(framing["payload_modes"])
    assert set(framing["required_payload_modes"]) <= set(framing["payload_modes"])
