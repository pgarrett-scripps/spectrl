#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
smoke_root=$(mktemp -d)
trap 'test -n "${smoke_root:-}" && rm -rf "$smoke_root"' EXIT

mkdir -p "$smoke_root/python-dist"
uv build --out-dir "$smoke_root/python-dist"
uv venv --python 3.13 --seed "$smoke_root/python-venv"
"$smoke_root/python-venv/bin/pip" install "$smoke_root"/python-dist/*.whl
cp "$repo_root/scripts/package_smoke.py" "$smoke_root/python-smoke.py"
"$smoke_root/python-venv/bin/python" "$smoke_root/python-smoke.py"

(cd "$repo_root/js" && npm ci && npm run typecheck && npm test)

mkdir -p "$smoke_root/npm-dist" "$smoke_root/npm-project"
(cd "$repo_root/js" && npm pack --pack-destination "$smoke_root/npm-dist")
(cd "$smoke_root/npm-project" && npm init --yes >/dev/null && npm install "$smoke_root"/npm-dist/*.tgz >/dev/null)
cp "$repo_root/js/scripts/package_smoke.mjs" "$smoke_root/npm-project/smoke.mjs"
(cd "$smoke_root/npm-project" && node smoke.mjs)

echo "Clean wheel and npm tarball installs passed"
