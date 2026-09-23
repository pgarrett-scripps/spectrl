test:
    uv run pytest tests/ -q

coverage:
    uv run pytest --cov=spectrl --cov-fail-under=80 tests/ -q

fuzz:
    uv run python scripts/fuzz_decode.py

# Named adversarial cases only; the cross-implementation check is `adversarial-parity`
adversarial:
    uv run python scripts/adversarial_corpus.py --out /dev/null --mutations 0

# Full corpus through both decoders; requires `cd js && npm ci`
adversarial-parity:
    uv run python scripts/check_adversarial_parity.py

adversarial-vectors:
    uv run python scripts/gen_adversarial_vectors.py

lint:
    uv run ruff check src/ tests/

format-check:
    uv run ruff format --check src/ tests/

whitespace-check:
    git diff --check

format:
    uv run ruff format src/ tests/

registry:
    uv run python scripts/generate_registry.py

check: lint format-check whitespace-check test

build:
    rm -rf dist/python
    uv build --out-dir dist/python
    uvx twine check dist/python/*

release-version:
    uv run python scripts/check_release_version.py

mzml-smoke:
    uv run python scripts/release_mzml_smoke.py tests/data/example.mzML tests/data/BSA1.mzML

clean-install-smoke:
    bash scripts/clean_install_smoke.sh

release-check: check coverage fuzz adversarial build release-version mzml-smoke clean-install-smoke
    cd js && npm ci && npm run typecheck && npm test && npm run fuzz && npm run build && npm pack --dry-run
    uv run python scripts/check_adversarial_parity.py
    cd demo && npm ci && npm test

# Build the JS library and launch the browser demo at http://127.0.0.1:8000
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    (cd js && npm install && npm run build)
    (cd demo && npm install && echo "→ open http://127.0.0.1:8000" && npm run dev)
