"""Generate synthetic Schwab PDFs for fixture testing.

Produces two file types that mirror the real Schwab statements enough
to satisfy decaf's parsers (schwab_gains_pdf, schwab_vest_pdf):

  - Year-End Summary PDF — realized gains (Short/Long-Term sections)
  - Annual Withholding Statement PDF — RSU vest FMVs

The parsers run `pdftotext -layout` and match column-oriented regex,
so this generator uses Courier (monospaced) and positions each cell
at designed x-coordinates. The printed text only has to satisfy the
regex; it does not need to look exactly like the real thing.

Library usage::

    from scripts.gen_schwab_pdfs import (
        LotRow, VestRow, write_year_end_summary, write_annual_withholding
    )

CLI for ad-hoc smoke-testing — real fixtures build via Python call.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas

_PORTRAIT = letter
_LANDSCAPE = landscape(letter)
_LEFT = 36
_LINE = 10
_FONT = "Courier"
_FONT_SZ = 8


def _top(pagesize: tuple[float, float]) -> float:
    return pagesize[1] - 54


@dataclass(frozen=True)
class LotRow:
    """One realized gain/loss line in the Year-End Summary."""

    description: str        # e.g. "META PLATFORMS INC            CLASS"
    cusip: str              # 5 digits + 1 letter + 3 digits (e.g. 30303M102)
    quantity: Decimal
    date_acquired: date
    date_sold: date
    proceeds: Decimal
    cost_basis: Decimal
    gain_loss: Decimal
    is_long_term: bool


@dataclass(frozen=True)
class VestRow:
    """One RSU vest entry in the Annual Withholding Statement."""

    vest_date: date
    transaction_id: int     # 7-digit
    award_id: int           # 9-digit
    award_date: date
    fmv_ita: Decimal        # ITA jurisdiction FMV (what decaf uses)
    fmv_irl: Decimal        # IRL FMV (parser also recognises it)
    shares_vested: int
    net_shares: int
    taxable_income_ita: Decimal = Decimal(0)


@dataclass
class _Cursor:
    c: canvas.Canvas
    pagesize: tuple[float, float]
    y: float = field(init=False)

    def __post_init__(self) -> None:
        self.y = _top(self.pagesize)

    def line(self, text: str, x: float = _LEFT) -> None:
        if self.y < 60:
            self.c.showPage()
            self.c.setFont(_FONT, _FONT_SZ)
            self.y = _top(self.pagesize)
        self.c.drawString(x, self.y, text)
        self.y -= _LINE

    def blank(self, n: int = 1) -> None:
        self.y -= _LINE * n
        if self.y < 60:
            self.c.showPage()
            self.c.setFont(_FONT, _FONT_SZ)
            self.y = _top(self.pagesize)


def _fmt_date(d: date) -> str:
    return d.strftime("%m/%d/%y")


def _fmt_amount(d: Decimal) -> str:
    sign = "-" if d < 0 else ""
    ad = abs(d).quantize(Decimal("0.01"))
    s = f"{ad:,.2f}"
    return f"({s})" if sign else s


def _lot_line(lot: LotRow) -> str:
    """One lot row, column-aligned for pdftotext -layout parser."""
    desc = lot.description.ljust(42)[:42]
    cusip = lot.cusip.ljust(12)
    qty = f"{lot.quantity:>10.2f}"
    da = _fmt_date(lot.date_acquired)
    ds = _fmt_date(lot.date_sold)
    proc = f"$ {_fmt_amount(lot.proceeds):>14}"
    cost = f"$ {_fmt_amount(lot.cost_basis):>14}"
    gain = _fmt_amount(lot.gain_loss)
    gain_s = f"$ {gain:>14}"
    return f"{desc}  {cusip} {qty} {da} {ds} {proc} {cost} -- {gain_s}"


def _section_header(cur: _Cursor, title: str) -> None:
    cur.blank()
    cur.line(title)
    cur.blank()
    cur.line(
        "Description OR                               CUSIP                 "
        "              Quantity/Par Acquired Sold   Total Proceeds  "
        "(-)Cost Basis  Wash Sale          Gain or (Loss)"
    )
    cur.blank()


def write_year_end_summary(
    path: Path,
    tax_year: int,
    account_id: str,
    lots: list[LotRow],
) -> None:
    """Write a Year-End Summary PDF that the gains parser can read.

    Short-Term + Long-Term sections are emitted only if populated.
    Totals are computed from the lots list.
    """
    c = canvas.Canvas(str(path), pagesize=_LANDSCAPE)
    c.setFont(_FONT, _FONT_SZ)
    cur = _Cursor(c=c, pagesize=_LANDSCAPE)

    cur.line(f"Charles Schwab — Year-End Summary  Tax Year {tax_year}")
    cur.line(f"Account: {account_id}")
    cur.blank(2)

    short = [lot for lot in lots if not lot.is_long_term]
    long_ = [lot for lot in lots if lot.is_long_term]

    def _section(title: str, rows: list[LotRow]) -> None:
        if not rows:
            return
        _section_header(cur, title)
        for lot in rows:
            cur.line(_lot_line(lot))
        total_proceeds = sum((lot.proceeds for lot in rows), Decimal(0))
        total_cost = sum((lot.cost_basis for lot in rows), Decimal(0))
        total_gain = sum((lot.gain_loss for lot in rows), Decimal(0))
        cur.blank()
        cur.line(
            f"Total {title.split(' ', 1)[0]}"
            f"{'':40}"
            f"  $ {_fmt_amount(total_proceeds):>14}"
            f" $ {_fmt_amount(total_cost):>14}"
            f"           -- $ {_fmt_amount(total_gain):>14}"
        )

    _section("Short-Term Realized Gain or (Loss)", short)
    _section("Long-Term Realized Gain or (Loss)", long_)

    c.showPage()
    c.save()


def _withholding_header(cur: _Cursor, tax_year: int, holder: str, address_lines: list[str]) -> None:
    cur.line("Charles Schwab Stock Plan Services")
    cur.line(f"Annual Statement — Tax withholding year: {tax_year}")
    cur.blank(2)
    cur.line(holder.upper())
    for line in address_lines:
        cur.line(line.upper())
    cur.blank(2)


def _share_txn_row(v: VestRow) -> str:
    # Parser regex anchors on: leading whitespace, MM/DD/YY, 7-digit, 9-digit
    return (
        f"  {_fmt_date(v.vest_date)}  {v.transaction_id:07d}  {v.award_id:09d}  "
        f"{_fmt_date(v.award_date)}  RSU      Lapse  "
        f"{v.shares_vested:>6}  $0.0000  --  {v.net_shares:>6}"
    )


def _tax_detail_block(v: VestRow) -> list[str]:
    """Three lines per award block in the Tax Details section.

    Parser rules:
      - new block starts with 9-digit award ID followed by whitespace.
      - FMV extracted via `$([\\d.]+)\\s+(IRL(?:-1)?|ITA)\\b(?!\\s*Social)`
      - prefers ITA, then IRL, then IRL-1.
    """
    irl_fmv = f"{v.fmv_irl:.4f}"
    ita_fmv = f"{v.fmv_ita:.4f}"
    income = f"${v.taxable_income_ita:,.2f}"
    return [
        f"  {v.award_id:09d}                    $0.00          $0.00         "
        f"${irl_fmv} IRL        0.000000%      0.000000%      $0.00",
        f"                                {income:>12}   {income:>12}         "
        f"${ita_fmv} ITA      100.000000%     46.330000%      $0.00",
        f"                                {income:>12}   {income:>12}         "
        f"${ita_fmv} ITA Social  100.000000%   0.000000%      $0.00",
    ]


def write_annual_withholding(
    path: Path,
    tax_year: int,
    holder_name: str,
    address_lines: list[str],
    vests: list[VestRow],
) -> None:
    """Write an Annual Withholding Statement PDF.

    Contains:
      - Share Transaction table (parser reads vest dates + award IDs)
      - Share Transaction Tax Details (parser reads FMV per award block)
    """
    c = canvas.Canvas(str(path), pagesize=_LANDSCAPE)
    c.setFont(_FONT, _FONT_SZ)
    cur = _Cursor(c=c, pagesize=_LANDSCAPE)

    _withholding_header(cur, tax_year, holder_name, address_lines)

    cur.line("Share Transaction")
    cur.line(
        "Transaction  Transaction  Award ID   Award Date  Award Type  "
        "Transaction  Shares  Award Price  Sale Price  Net Shares"
    )
    cur.line(
        "   Date         ID                                              "
        "Type                                          Issued"
    )
    for v in vests:
        cur.line(_share_txn_row(v))
    cur.blank(2)

    cur.line("Share Transaction Tax Details")
    cur.line(
        "           Taxable         Reportable      Fair Market  Jurisdiction"
        "   Taxable       Tax Rate    Tax"
    )
    cur.line(
        " Award ID  Income*         Income **       Value                     "
        "   Allocation                Paid"
    )
    for v in vests:
        for line in _tax_detail_block(v):
            cur.line(line)
        cur.blank()

    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


def _smoke_test(out_dir: Path) -> None:
    """Emit a trivial pair of PDFs so you can eyeball the generator."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lots = [
        LotRow(
            description="SMOKE CORP CLASS A",
            cusip="12345A678",
            quantity=Decimal("10"),
            date_acquired=date(2024, 3, 15),
            date_sold=date(2024, 9, 20),
            proceeds=Decimal("1500.00"),
            cost_basis=Decimal("1200.00"),
            gain_loss=Decimal("300.00"),
            is_long_term=False,
        ),
    ]
    vests = [
        VestRow(
            vest_date=date(2024, 5, 15),
            transaction_id=1111111,
            award_id=999999999,
            award_date=date(2023, 3, 15),
            fmv_ita=Decimal("123.4500"),
            fmv_irl=Decimal("120.0000"),
            shares_vested=10,
            net_shares=5,
            taxable_income_ita=Decimal("617.25"),
        ),
    ]
    write_year_end_summary(
        out_dir / "Year-End Summary - 2024_2025-01-24_smoke.PDF",
        2024, "XXX999", lots,
    )
    write_annual_withholding(
        out_dir / "Annual Withholding Statement_2024-12-31.PDF",
        2024, "Smoke Tester", ["Via Fumatori 1", "Roma 00100 IT"], vests,
    )
    print(f"Wrote smoke-test PDFs to {out_dir}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--smoke", type=Path, help="Write a pair of trivial PDFs to this dir")
    args = p.parse_args()
    if args.smoke:
        _smoke_test(args.smoke)
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
