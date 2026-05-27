"""Tests for IBKR FlexQuery XML on-disk archive."""

from __future__ import annotations

import gzip
from datetime import UTC, date, datetime
from pathlib import Path

from decaf.flex_archive import _sniff_account_id, save_ibkr_flex_xml


def test_sniff_account_id_finds_attribute() -> None:
    xml = '<?xml version="1.0"?><Foo accountId="U1234567" other="x"/>'
    assert _sniff_account_id(xml) == "U1234567"


def test_sniff_account_id_falls_back_when_missing() -> None:
    assert _sniff_account_id("<Foo/>") == "unknown"


def test_save_writes_gzipped_xml_with_deterministic_name(tmp_path: Path) -> None:
    xml = '<FlexStatement accountId="U9999"><Trades/></FlexStatement>'
    when = datetime(2026, 5, 27, 14, 30, 0, tzinfo=UTC)
    out = save_ibkr_flex_xml(
        xml,
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        archive_dir=tmp_path,
        fetched_at=when,
    )
    assert out.name == "ibkr_U9999_2025-01-01_2025-12-31_20260527T143000Z.xml.gz"
    assert out.parent == tmp_path
    # Round-trip the gzip and verify content
    with gzip.open(out, "rb") as fh:
        assert fh.read().decode("utf-8") == xml


def test_save_creates_archive_dir_if_missing(tmp_path: Path) -> None:
    archive_dir = tmp_path / "nested" / "flexquery"
    out = save_ibkr_flex_xml(
        "<x/>",
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        archive_dir=archive_dir,
    )
    assert out.exists()
    assert archive_dir.is_dir()


def test_save_two_fetches_dont_collide(tmp_path: Path) -> None:
    """Different fetched_at timestamps produce distinct filenames so a
    re-fetch of the same period never overwrites the prior archive."""
    common = {
        "xml": '<x accountId="U1"/>',
        "from_date": date(2025, 1, 1),
        "to_date": date(2025, 12, 31),
        "archive_dir": tmp_path,
    }
    a = save_ibkr_flex_xml(**common, fetched_at=datetime(2026, 5, 27, 10, tzinfo=UTC))
    b = save_ibkr_flex_xml(**common, fetched_at=datetime(2026, 5, 27, 11, tzinfo=UTC))
    assert a != b
    assert a.exists() and b.exists()
