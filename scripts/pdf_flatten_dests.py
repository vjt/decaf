#!/usr/bin/env python3
"""Rewrite named-string PDF destinations to explicit page arrays.

Pandoc + xelatex + hyperref produces internal /GoTo links whose /D
attribute is a *string* like 'section.2.3' that resolves via the
/Root/Names/Dests tree. Apple PDFKit (Safari iOS' PDF viewer) handles
those erratically — taps on section cross-references surface an
"address invalid" message.

This post-processor walks every /Link annotation and replaces each
named-string /D with the resolved explicit dest (a [page_ref /XYZ x y
zoom] array). Explicit page-ref destinations are broadly supported.

Usage: scripts/pdf_flatten_dests.py input.pdf output.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject


def _resolve_named_dests(reader: PdfReader) -> dict[str, ArrayObject]:
    """Return {name: dest_array} for every entry under /Root/Names/Dests."""
    root = reader.trailer["/Root"]
    names = root.get("/Names")
    if not names:
        return {}
    dests = names.get_object().get("/Dests")
    if not dests:
        return {}

    out: dict[str, ArrayObject] = {}

    def walk(node) -> None:
        node = node.get_object() if hasattr(node, "get_object") else node
        if "/Names" in node:
            lst = node["/Names"]
            for i in range(0, len(lst), 2):
                name = str(lst[i])
                dest = lst[i + 1]
                dest = dest.get_object() if hasattr(dest, "get_object") else dest
                # dest entry may be a dict {/D: array} or an array directly
                if isinstance(dest, DictionaryObject) and "/D" in dest:
                    out[name] = dest["/D"]
                else:
                    out[name] = dest
        if "/Kids" in node:
            for kid in node["/Kids"]:
                walk(kid)

    walk(dests)
    return out


def flatten(src_path: Path, dst_path: Path) -> int:
    reader = PdfReader(str(src_path))
    writer = PdfWriter(clone_from=reader)
    dest_map = _resolve_named_dests(reader)

    flattened = 0
    unresolved = 0
    for page in writer.pages:
        annots = page.get("/Annots")
        if not annots:
            continue
        for annot_ref in annots:
            annot = annot_ref.get_object()
            if annot.get("/Subtype") != "/Link":
                continue
            action = annot.get("/A")
            if action is None:
                continue
            action = action.get_object()
            if action.get("/S") != NameObject("/GoTo"):
                continue
            d = action.get("/D")
            if d is None:
                continue
            # If /D is already an array (explicit), leave alone
            if isinstance(d, ArrayObject):
                continue
            name = str(d)
            resolved = dest_map.get(name)
            if resolved is None:
                unresolved += 1
                continue
            action[NameObject("/D")] = resolved
            flattened += 1

    with dst_path.open("wb") as fh:
        writer.write(fh)

    print(
        f"pdf_flatten_dests: flattened {flattened} named /GoTo dests, "
        f"{unresolved} unresolved ({src_path.name} → {dst_path.name})",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    return flatten(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    sys.exit(main())
