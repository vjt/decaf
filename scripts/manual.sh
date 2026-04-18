#!/usr/bin/env bash
# Generate the project manual PDF from doc/ markdown files.
# Requires: pandoc, texlive-latex-recommended, texlive-latex-extra
set -euo pipefail

cd "$(dirname "$0")/.."

TIMESTAMP=$(date +%Y-%m-%d)
OUTPUT="doc/decaf_manual.pdf"

# Check dependencies
if ! command -v pandoc &>/dev/null; then
    echo "ERROR: pandoc not installed. Run: sudo apt install pandoc texlive-latex-recommended texlive-latex-extra"
    exit 1
fi

# Strip Mermaid code blocks (pandoc can't render them)
# Replace with a note pointing to the source file
mermaid_filter() {
    sed '/^```mermaid$/,/^```$/{
        /^```mermaid$/c\> *[Diagramma: vedere ARCHITECTURE.md per il sorgente Mermaid]*
        /^```$/d
        d
    }'
}

# Build manual from doc/ files in presentation order:
# 1. Guida Fiscale (what to declare — AdE cares most about this)
# 2. Normativa (legal backing for every number)
# 3. Architecture (how the software computes it)
# 4. Internals (broker-specific data source details)
# 5. Query Setup (how raw data was obtained)

echo "Generating manual..."

# Preprocess: strip cross-reference links that don't work in PDF,
# and handle Mermaid blocks
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

for f in GUIDA_FISCALE.md NORMATIVA.md ARCHITECTURE.md INTERNALS.md QUERY_SETUP.md; do
    # Fix image paths: img/ -> doc/img/ (pandoc runs from project root)
    cat "doc/$f" | mermaid_filter | sed 's|](img/|](doc/img/|g' > "$TMP/$f"
done

# Add generation timestamp page at the end
cat > "$TMP/FOOTER.md" << EOF

# Informazioni sul documento

- **Generato il**: ${TIMESTAMP}
- **Software**: decaf v$(.venv/bin/python -c "from decaf import __version__; print(__version__)")
- **Sorgente documentazione**: \`doc/\` directory del repository decaf

Questo manuale e' generato automaticamente dai file di documentazione
del progetto. Per la versione piu' aggiornata, rigenerare con:

\`\`\`
scripts/manual.sh
\`\`\`
EOF

pandoc \
    --metadata-file=doc/manual_meta.yaml \
    --pdf-engine=xelatex \
    --shift-heading-level-by=0 \
    -o "$OUTPUT" \
    "$TMP/GUIDA_FISCALE.md" \
    "$TMP/NORMATIVA.md" \
    "$TMP/ARCHITECTURE.md" \
    "$TMP/INTERNALS.md" \
    "$TMP/QUERY_SETUP.md" \
    "$TMP/FOOTER.md"

echo "Manual generated: $OUTPUT"
ls -lh "$OUTPUT"
