"""Fail when release metadata or an optional vX.Y.Z tag disagree."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _citation_version() -> str:
    text = (ROOT / "CITATION.cff").read_text()
    match = re.search(r'^version:\s*["\']?([^"\'\s]+)', text, re.MULTILINE)
    if not match:
        raise SystemExit("CITATION.cff has no version")
    return match.group(1)


python_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
npm_version = json.loads((ROOT / "js/package.json").read_text())["version"]
npm_lock_version = json.loads((ROOT / "js/package-lock.json").read_text())["version"]
uv_packages = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
uv_version = next(package["version"] for package in uv_packages if package["name"] == "spectrl")
zenodo_version = json.loads((ROOT / ".zenodo.json").read_text())["version"]
versions = {
    "pyproject.toml": python_version,
    "js/package.json": npm_version,
    "js/package-lock.json": npm_lock_version,
    "uv.lock": uv_version,
    "CITATION.cff": _citation_version(),
    ".zenodo.json": zenodo_version,
}

if len(set(versions.values())) != 1:
    raise SystemExit("release versions disagree: " + ", ".join(f"{path}={value}" for path, value in versions.items()))

tag = sys.argv[1] if len(sys.argv) > 1 else ""
if tag:
    expected = f"v{python_version}"
    if tag != expected:
        raise SystemExit(f"release tag {tag!r} does not match package version {expected!r}")

changelog = (ROOT / "CHANGELOG.md").read_text()
if f"## [{python_version}]" not in changelog:
    raise SystemExit(f"CHANGELOG.md has no release section for {python_version}")

print(f"Release metadata agrees on {python_version}" + (f" ({tag})" if tag else ""))
