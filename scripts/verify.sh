#!/usr/bin/env bash
# Full verification: lint + test + compare reference JSON outputs.
# Run this before committing to ensure nothing is broken.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Linting ==="
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m pyright src/

echo ""
echo "=== Tests ==="
.venv/bin/python -m pytest tests/ -x --tb=short

echo ""
echo "=== Reference output verification ==="
tmpdir=$(mktemp -d)
trap "rm -rf $tmpdir" EXIT

for year in 2022 2023 2024 2025; do
    ref="test_reference/decaf_U66666666_U66666600_XXX123_${year}.json"
    if [ ! -f "$ref" ]; then
        echo "SKIP $year (no reference file)"
        continue
    fi
    .venv/bin/python -m decaf report --year "$year" --output-dir "$tmpdir" 2>/dev/null
    out="$tmpdir/decaf_U66666666_U66666600_XXX123_${year}.json"
    if diff \
        <(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))" "$ref") \
        <(python3 -c "import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True, indent=2))" "$out") \
        > /dev/null; then
        echo "  $year: MATCH"
    else
        echo "  $year: MISMATCH"
        exit 1
    fi
done

echo ""
echo "=== All checks passed ==="
