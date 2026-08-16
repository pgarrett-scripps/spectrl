test:
    uv run pytest tests/ -q

coverage:
    uv run pytest --cov=spectrl --cov-fail-under=80 tests/ -q

fuzz:
    uv run python scripts/fuzz_decode.py

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
    uv build
    uvx twine check dist/*

release-check: check fuzz build
    cd js && npm ci && npm run typecheck && npm test && npm run build && npm pack --dry-run
    cd demo && npm ci && npm run build

# Build the JS library and launch the browser demo at http://127.0.0.1:8000
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    (cd js && npm install && npm run build)
    (cd demo && npm install && echo "→ open http://127.0.0.1:8000" && npm run dev)
