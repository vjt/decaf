#!/usr/bin/env bash
# Run test suite with verbose output.
set -euo pipefail

cd "$(dirname "$0")/.."

.venv/bin/python -m pytest tests/ -x -v --rootdir=. "$@"
