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

# Chapter filename → slug. Each included doc gets an explicit {#slug}
# injected on its H1, and cross-references to that file rewrite to
# `#slug` so the manual has internal anchors instead of dead URLs.
# Keep the `name:slug` pairs tight — one per file included in pandoc.
CHAPTERS=(
    "README:uso-del-software"
    "GUIDA_FISCALE:guida-fiscale"
    "NORMATIVA:normativa"
    "ARCHITECTURE:architecture"
    "INTERNALS:internals"
    "QUERY_SETUP:query-setup"
)

# Rewrite markdown cross-references to in-PDF anchors.
# For each chapter NAME (no .md suffix) with chapter slug SLUG, match any
# preceding path segment (./ / ../ / doc/ / https://github.com/vjt/decaf/blob/master/
# / combinations) followed by `NAME.md` optionally with a `#anchor`.
#   [text](.../NAME.md#anchor)  → [text](#anchor)
#   [text](.../NAME.md)         → [text](#SLUG)
# Links to non-chapter files (BACKTEST.md, others) are left alone so they
# remain clickable GitHub URLs in the PDF.
# Expects input on stdin, produces output on stdout.
rewrite_cross_refs() {
    local -a sed_args=()
    local entry name slug
    # Generic path prefix — anything before "NAME.md" that might appear
    # in the source docs (GitHub blob URL, ./, ../, doc/, or nothing).
    local pfx='(https://github\.com/vjt/decaf/blob/master/)?(\./)?(\.\./)?(doc/)?'
    for entry in "${CHAPTERS[@]}"; do
        name="${entry%:*}"
        slug="${entry#*:}"
        # With anchor: keep source anchor, drop file prefix ($5 = anchor)
        sed_args+=(-e "s|\\]\\(${pfx}${name}\\.md#([^)]*)\\)|](#\\5)|g")
        # Without anchor: point to chapter slug
        sed_args+=(-e "s|\\]\\(${pfx}${name}\\.md\\)|](#${slug})|g")
    done
    # Remaining `../FILENAME.md` references point to repo-root files that
    # aren't manual chapters (e.g. CLAUDE.md). Point them at the GitHub
    # blob URL so they stay clickable in the PDF instead of appearing as
    # invalid `../foo.md` filesystem URIs.
    sed_args+=(-e "s|\\]\\(\\.\\./([A-Z_]+\\.md)(#[^)]*)?\\)|](https://github.com/vjt/decaf/blob/master/\\1\\2)|g")
    sed -E "${sed_args[@]}"
}

# Inject {#slug} on the file's first H1 so `#slug` anchors resolve to
# the start of the chapter. `0,/^# /` is GNU-sed for "up to first H1";
# within that range the substitution fires only on that matched line.
inject_chapter_id() {
    local slug="$1"
    sed -E "0,/^# /s|^(# .*)\$|\\1 {#${slug}}|"
}

echo "Generating manual..."

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

# Preprocess README into a "Uso del software" chapter:
#   - strip <p align="center">...</p> blocks (cover + logo go on titlepage)
#   - rewrite absolute raw.githubusercontent.com / jsdelivr URLs back to
#     local paths so the PDF can render images
#   - rewrite cross-doc md links to internal PDF anchors (rewrite_cross_refs)
#   - promote the top-level H1 "decaf" to something that reads as a chapter
sed -e '/^<p align="center">$/,/^<\/p>$/d' \
    -e 's|https://raw.githubusercontent.com/vjt/decaf/master/|doc/..\/|g' \
    -e 's|https://cdn.jsdelivr.net/gh/vjt/decaf@master/|doc/..\/|g' \
    -e '1,/^# decaf$/c\# Uso del software' \
    README.md \
    | rewrite_cross_refs \
    | inject_chapter_id "uso-del-software" \
    > "$TMP/README.md"

for entry in "${CHAPTERS[@]}"; do
    name="${entry%:*}"
    slug="${entry#*:}"
    [[ "$name" == "README" ]] && continue
    # Fix image paths: img/ -> doc/img/ (pandoc runs from project root)
    # Rewrite cross-doc references to in-PDF anchors.
    # Inject {#slug} on the H1 so anchors land at the chapter start.
    cat "doc/${name}.md" \
        | mermaid_filter \
        | sed 's|](img/|](doc/img/|g' \
        | rewrite_cross_refs \
        | inject_chapter_id "$slug" \
        > "$TMP/${name}.md"
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

RAW="$TMP/decaf_manual_raw.pdf"
pandoc \
    --metadata-file=doc/manual_meta.yaml \
    --from=markdown+gfm_auto_identifiers \
    --pdf-engine=xelatex \
    --shift-heading-level-by=0 \
    -o "$RAW" \
    "$TMP/README.md" \
    "$TMP/GUIDA_FISCALE.md" \
    "$TMP/NORMATIVA.md" \
    "$TMP/ARCHITECTURE.md" \
    "$TMP/INTERNALS.md" \
    "$TMP/QUERY_SETUP.md" \
    "$TMP/FOOTER.md"

# Flatten named-string /GoTo dests to explicit page arrays so internal
# PDF navigation works in Safari iOS / Apple PDFKit. See header of
# scripts/pdf_flatten_dests.py for the motivation.
.venv/bin/python scripts/pdf_flatten_dests.py "$RAW" "$OUTPUT"

echo "Manual generated: $OUTPUT"
ls -lh "$OUTPUT"
