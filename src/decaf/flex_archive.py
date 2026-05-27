"""On-disk archive for IBKR FlexQuery XML fetches.

IBKR retains only ~365 days of FlexQuery history. Every successful API
fetch is gzipped to ~/.cache/decaf/flexquery/ so the raw source data
stays around forever. If decaf or IBKR itself ever changes the parse
contract, the archived XML can be re-fed via `decaf load --file`.

Naming: ibkr_<account_or_unknown>_<from>_<to>_<fetched_at>.xml.gz
- account is extracted via a cheap regex pre-parse, falling back to
  'unknown' so a malformed XML still gets saved
- fetched_at is UTC ISO basic format so files sort by fetch time
"""

from __future__ import annotations

import gzip
import re
from datetime import UTC, date, datetime
from pathlib import Path

FLEXQUERY_DIR_NAME = "flexquery"

# Pulls the first accountId="U1234567" we can find in the XML. The Flex
# schema repeats this attribute on most rows, so the first occurrence is
# always the statement's account when the statement covers a single
# account. For consolidated multi-account queries we accept that the
# filename only names the first one.
_ACCOUNT_ID_RE = re.compile(rb'accountId="([^"]+)"')


def _sniff_account_id(xml: str | bytes) -> str:
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    m = _ACCOUNT_ID_RE.search(data)
    return m.group(1).decode("ascii", errors="replace") if m else "unknown"


def save_ibkr_flex_xml(
    xml: str,
    from_date: date,
    to_date: date,
    archive_dir: Path,
    fetched_at: datetime | None = None,
) -> Path:
    """Gzip-archive a FlexQuery XML payload. Returns the written path."""
    archive_dir.mkdir(parents=True, exist_ok=True)
    when = fetched_at or datetime.now(UTC)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    account = _sniff_account_id(xml)
    name = f"ibkr_{account}_{from_date.isoformat()}_{to_date.isoformat()}_{stamp}.xml.gz"
    path = archive_dir / name
    with gzip.open(path, "wb", compresslevel=6) as fh:
        fh.write(xml.encode("utf-8"))
    return path
