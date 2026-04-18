#!/usr/bin/env bash
# decaf launcher — manages venv + deps automatically.
#
# First run: creates .venv/ and installs the package + vendor deps.
# Later runs: re-installs only when pyproject.toml changes.
# Always: activates venv and execs `python -m decaf "$@"`.
#
# Usage examples:
#   ./decaf.sh fetch --file private/flexquery.xml
#   ./decaf.sh report --year 2025
#   ./decaf.sh backtest private/
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo ">> Creating .venv/ (first run)..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Reinstall only when pyproject.toml (root or vendored) changes.
hash_file=.venv/.decaf_deps_hash
current_hash=$(cat pyproject.toml vendor/*/pyproject.toml 2>/dev/null | sha256sum | awk '{print $1}')
if [ ! -f "$hash_file" ] || [ "$(cat "$hash_file")" != "$current_hash" ]; then
    echo ">> Installing/updating dependencies..."
    pip install -q -e vendor/ibkr-flex-client -e vendor/ecb-fx-rates -e ".[dev]"
    echo "$current_hash" > "$hash_file"
fi

exec python -m decaf "$@"
