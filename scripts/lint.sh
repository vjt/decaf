#!/usr/bin/env bash
# Run all linters. Returns non-zero if any check fails.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== ruff check ==="
.venv/bin/python -m ruff check src/ tests/

echo "=== ruff format ==="
.venv/bin/python -m ruff format --check src/ tests/

echo "=== pyright ==="
.venv/bin/python -m pyright src/

echo "=== All clean ==="
