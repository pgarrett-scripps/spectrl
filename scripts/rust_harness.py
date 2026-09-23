"""Run the Rust implementation (`rust/`) from the parity scripts.

The Rust crate is the third independent implementation of spectrl.v3. Its
`spectrl batch` command reads JSON-lines requests on stdin and writes one
result line per request. When cargo is not installed the parity scripts skip
Rust with a message instead of failing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "rust" / "Cargo.toml"


def rust_binary() -> Path | None:
    """Build the release binary and return its path, or None when cargo is missing."""
    cargo = shutil.which("cargo")
    if cargo is None:
        print("skipping Rust: cargo is not installed (install Rust or pass --no-rust to silence this)")
        return None
    subprocess.run([cargo, "build", "--release", "--quiet", "--manifest-path", str(MANIFEST)], check=True)
    target = subprocess.run(
        [cargo, "metadata", "--format-version", "1", "--no-deps", "--manifest-path", str(MANIFEST)],
        capture_output=True,
        text=True,
        check=True,
    )
    directory = Path(json.loads(target.stdout)["target_directory"])
    binary = directory / "release" / ("spectrl.exe" if (directory / "release" / "spectrl.exe").exists() else "spectrl")
    return binary


def batch(binary: Path, requests: list[dict]) -> list[dict]:
    """Send requests to `spectrl batch` and return one result per request."""
    run = subprocess.run(
        [str(binary), "batch"],
        input="".join(json.dumps(r) + "\n" for r in requests),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    results = [json.loads(line) for line in run.stdout.splitlines() if line.strip()]
    if len(results) != len(requests):
        raise RuntimeError(f"spectrl batch returned {len(results)} results for {len(requests)} requests")
    return results


def rustc_version() -> str | None:
    rustc = shutil.which("rustc")
    return subprocess.check_output([rustc, "--version"], text=True).strip() if rustc else None
