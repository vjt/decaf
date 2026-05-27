"""Archive / unarchive: pack and restore decaf state across machines.

What goes in the tarball:
- ~/.cache/decaf/statements.db (the deduplicated broker store — essential)
- ~/.cache/decaf/ecb_rates.db (BCE rate cache — regenerable but slow)
- any extra directories passed by the user (e.g. private/ holding the
  raw broker exports + generated YAML/PDF/XLS reports)
- a metadata.yaml describing version, date, and what's inside

Tarball internal layout (rooted at 'decaf-archive/'):
    metadata.yaml
    cache/
        statements.db
        ecb_rates.db
    trees/
        <abs-or-rel-path-of-included-dir>/...

Unarchive refuses to overwrite an existing ~/.cache/decaf/*.db unless
--force is given. Extra trees are restored under --target-dir
(default: current working directory), preserving their original
relative layout.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import yaml

from decaf import __version__

CACHE_DIR = Path.home() / ".cache" / "decaf"
DB_NAMES = ("statements.db", "ecb_rates.db")
ARCHIVE_ROOT = "decaf-archive"


def _add_file(tar: tarfile.TarFile, src: Path, arcname: str) -> None:
    tar.add(src, arcname=arcname, recursive=False)


def _add_bytes(tar: tarfile.TarFile, data: bytes, arcname: str) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mtime = int(datetime.now(UTC).timestamp())
    tar.addfile(info, BytesIO(data))


def cmd_archive(args: argparse.Namespace) -> None:
    """Pack decaf state into a single .tgz."""
    output: Path = args.output
    extra_trees: list[Path] = [Path(p).resolve() for p in args.trees]

    if output.exists() and not args.force:
        print(f"ERROR: {output} already exists. Use --force to overwrite.")
        sys.exit(1)

    dbs_present = [p for p in (CACHE_DIR / n for n in DB_NAMES) if p.exists()]
    if not dbs_present:
        print(f"WARNING: no decaf databases found in {CACHE_DIR}")

    for tree in extra_trees:
        if not tree.exists():
            print(f"ERROR: tree {tree} does not exist")
            sys.exit(1)

    metadata = {
        "decaf_version": __version__,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_host_cache": str(CACHE_DIR),
        "databases": [p.name for p in dbs_present],
        "trees": [str(t) for t in extra_trees],
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as tar:
        _add_bytes(
            tar,
            yaml.safe_dump(metadata, sort_keys=False).encode("utf-8"),
            f"{ARCHIVE_ROOT}/metadata.yaml",
        )
        for db in dbs_present:
            _add_file(tar, db, f"{ARCHIVE_ROOT}/cache/{db.name}")
        for tree in extra_trees:
            # store under trees/<absolute-path-without-leading-slash> so
            # unarchive can either restore in place or rebase under
            # --target-dir, at the user's choice.
            anchor = tree.as_posix().lstrip("/")
            tar.add(tree, arcname=f"{ARCHIVE_ROOT}/trees/{anchor}")

    print(f"Wrote {output} ({output.stat().st_size:,} bytes)")
    print(f"  databases: {', '.join(p.name for p in dbs_present) or 'none'}")
    print(f"  trees:     {', '.join(str(t) for t in extra_trees) or 'none'}")


def cmd_unarchive(args: argparse.Namespace) -> None:
    """Restore decaf state from a .tgz produced by `decaf archive`."""
    src: Path = args.input
    target_dir: Path = args.target_dir.resolve()

    if not src.exists():
        print(f"ERROR: {src} does not exist")
        sys.exit(1)

    with tarfile.open(src, "r:gz") as tar:
        names = tar.getnames()
        meta_member = next(
            (n for n in names if n.endswith("/metadata.yaml")),
            None,
        )
        if not meta_member:
            print(f"ERROR: {src} is not a decaf archive (no metadata.yaml)")
            sys.exit(1)
        meta_file = tar.extractfile(meta_member)
        assert meta_file is not None
        metadata = yaml.safe_load(meta_file.read())
        print("Archive metadata:")
        print(f"  decaf version: {metadata.get('decaf_version', '?')}")
        print(f"  created:       {metadata.get('created_at', '?')}")
        print(f"  databases:     {metadata.get('databases', [])}")
        print(f"  trees:         {metadata.get('trees', [])}")

        # 1. Restore databases (refuse to overwrite without --force)
        db_members = [n for n in names if n.startswith(f"{ARCHIVE_ROOT}/cache/")]
        for m in db_members:
            name = Path(m).name
            dest = CACHE_DIR / name
            if dest.exists() and not args.force:
                print(f"\nABORT: {dest} already exists. Use --force to overwrite.")
                sys.exit(1)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        for m in db_members:
            name = Path(m).name
            dest = CACHE_DIR / name
            data = tar.extractfile(m)
            assert data is not None
            dest.write_bytes(data.read())
            print(f"  restored {dest}")

        # 2. Restore trees under --target-dir, stripping decaf-archive/trees/
        tree_members = [
            m
            for m in tar.getmembers()
            if m.name.startswith(f"{ARCHIVE_ROOT}/trees/") and m.isfile()
        ]
        for m in tree_members:
            rel = m.name[len(f"{ARCHIVE_ROOT}/trees/") :]
            dest = target_dir / rel
            if dest.exists() and not args.force:
                print(f"\nABORT: {dest} already exists. Use --force to overwrite.")
                sys.exit(1)
        for m in tree_members:
            rel = m.name[len(f"{ARCHIVE_ROOT}/trees/") :]
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = tar.extractfile(m)
            assert data is not None
            dest.write_bytes(data.read())
        if tree_members:
            print(f"  restored {len(tree_members)} file(s) under {target_dir}")

    print("\nDone.")
