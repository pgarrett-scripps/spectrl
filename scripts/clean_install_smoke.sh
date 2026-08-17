#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "$0")/.." && pwd)
smoke_root=$(mktemp -d)
trap 'test -n "${smoke_root:-}" && rm -rf "$smoke_root"' EXIT

mkdir -p "$smoke_root/python-dist"
uv build --out-dir "$smoke_root/python-dist"
uv venv --python 3.13 --seed "$smoke_root/python-venv"
"$smoke_root/python-venv/bin/pip" install "$smoke_root"/python-dist/*.whl
"$smoke_root/python-venv/bin/python" -c \
  "from spectrl import InlineSpectrum, encode_spectrum, decode_token; s=InlineSpectrum(1,[100.0],[42.0]); assert decode_token(encode_spectrum(s)).default_array_length == 1"

mkdir -p "$smoke_root/npm-dist" "$smoke_root/npm-project"
(cd "$repo_root/js" && npm pack --pack-destination "$smoke_root/npm-dist")
(cd "$smoke_root/npm-project" && npm init --yes >/dev/null && npm install "$smoke_root"/npm-dist/*.tgz >/dev/null)
(cd "$smoke_root/npm-project" && node --input-type=module -e \
  "import {encodeSpectrum,decodeToken} from '@spectrl-ms/spectrl'; const t=encodeSpectrum({defaultArrayLength:1,mz:[100],intensity:[42]},{quiet:true}); if(decodeToken(t).defaultArrayLength!==1) process.exit(1)")

echo "Clean wheel and npm tarball installs passed"
