"""Smoke tests for decaf.archive: roundtrip pack -> unpack."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from decaf import archive as ar


@pytest.fixture
def fake_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ar.CACHE_DIR to a temp dir with two dummy db files."""
    cache = tmp_path / "cache" / "decaf"
    cache.mkdir(parents=True)
    (cache / "statements.db").write_bytes(b"fake statements")
    (cache / "ecb_rates.db").write_bytes(b"fake ecb")
    monkeypatch.setattr(ar, "CACHE_DIR", cache)
    return cache


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def test_archive_then_unarchive_roundtrip(fake_cache: Path, tmp_path: Path) -> None:
    tree = tmp_path / "private"
    tree.mkdir()
    (tree / "report.yaml").write_text("hello: world")
    out = tmp_path / "backup.tgz"

    ar.cmd_archive(_ns(output=out, trees=[tree], force=False))
    assert out.exists()
    assert out.stat().st_size > 0

    # Wipe the source state and restore into a fresh target
    (fake_cache / "statements.db").unlink()
    (fake_cache / "ecb_rates.db").unlink()
    target = tmp_path / "restored"

    ar.cmd_unarchive(_ns(input=out, target_dir=target, force=False))

    assert (fake_cache / "statements.db").read_bytes() == b"fake statements"
    assert (fake_cache / "ecb_rates.db").read_bytes() == b"fake ecb"
    # The tree was archived under its absolute path; the restored copy
    # mirrors that path under target/.
    restored = target / tree.as_posix().lstrip("/") / "report.yaml"
    assert restored.read_text() == "hello: world"


def test_unarchive_refuses_to_overwrite_existing_db(fake_cache: Path, tmp_path: Path) -> None:
    out = tmp_path / "backup.tgz"
    ar.cmd_archive(_ns(output=out, trees=[], force=False))

    # DBs still exist from fixture — unarchive must refuse
    with pytest.raises(SystemExit) as exc:
        ar.cmd_unarchive(_ns(input=out, target_dir=tmp_path / "out", force=False))
    assert exc.value.code == 1


def test_archive_refuses_to_overwrite_existing_output(fake_cache: Path, tmp_path: Path) -> None:
    out = tmp_path / "backup.tgz"
    out.write_bytes(b"already here")
    with pytest.raises(SystemExit) as exc:
        ar.cmd_archive(_ns(output=out, trees=[], force=False))
    assert exc.value.code == 1


def test_unarchive_rejects_non_decaf_tarball(tmp_path: Path) -> None:
    import tarfile
    from io import BytesIO

    bogus = tmp_path / "bogus.tgz"
    with tarfile.open(bogus, "w:gz") as tar:
        info = tarfile.TarInfo("hello.txt")
        info.size = 5
        tar.addfile(info, BytesIO(b"hello"))

    with pytest.raises(SystemExit) as exc:
        ar.cmd_unarchive(_ns(input=bogus, target_dir=tmp_path / "out", force=False))
    assert exc.value.code == 1
