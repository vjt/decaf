"""Auto-populate the AdE precompilata Quadro RT + Quadro RM via CDP.

Reads a decaf YAML report and fills:
- Quadro RT Sez. II-A rigo RT11 col.1 + col.2 (single rigo aggregate)
- Quadro RM Sez. II-A rigo RM31 (one rigo per source country + tipo)

USAGE:
    chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-prof &
    # log into the precompilata
    python -m decaf.scripts.fill_rt_rm private/decaf_2025.yaml

    # --dry-run        Print actions without filling
    # --force          Overwrite existing values
    # --rt-only        Skip RM
    # --rm-only        Skip RT

Safety:
- Refuses to overwrite a non-empty field without --force.
- Aborts on save failure.
- Never clicks 'Calcola, stampa e invia'. Final review + submit is
  always a manual step.

RM31 is the recommended path for non-qualified foreign dividends and
broker interest (art. 27 c. 4-bis DPR 600/1973). RL2 + Quadro CE is
mutually exclusive and not handled by this script — see GUIDA_FISCALE.md
if you want to take that route instead.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

import yaml

from decaf.country_codes import iso_to_ade_country_code
from decaf.models import RLLine, TaxReport
from decaf.quadro_rl import aggregate_rl_for_rm31
from decaf.scripts._cdp import (
    CDP,
    click_add_module,
    confirm_modal_if_present,
    connect_to_precompilata,
    field_value,
    quadro_url,
    save_and_verify,
    set_field,
)

# --- Quadro RT (Sez. II-A, rigo RT11) ---


async def fill_rt(cdp: CDP, report: TaxReport, year_yy: str, dry_run: bool, force: bool) -> bool:
    """Fill Quadro RT rigo RT11 with the totals from decaf rt_lines."""
    proceeds = report.rt_total_proceeds_eur.quantize(Decimal("1"))
    cost = report.rt_total_cost_basis_eur.quantize(Decimal("1"))
    print("\n=== Quadro RT — Sez. II-A, rigo RT11 ===")
    print(f"  RT11 col.1 (corrispettivi): EUR {proceeds}")
    print(f"  RT11 col.2 (costi):         EUR {cost}")
    if dry_run:
        return True

    url = quadro_url(year_yy, "RT")
    print(f"  Navigating to {url}")
    await cdp.navigate(url, expect_field_prefix="RT")

    # Safety: check if RT011001 / RT011002 already have values
    for col, val in [(1, str(proceeds)), (2, str(cost))]:
        field_name = f"RT011{col:03d}"
        existing = await field_value(cdp, field_name)
        if existing and existing != val and not force:
            print(f"  SKIP: {field_name} already has {existing!r} != {val!r}. Use --force.")
            return False

    for col, val in [(1, str(proceeds)), (2, str(cost))]:
        field_name = f"RT011{col:03d}"
        actual = await set_field(cdp, field_name, val)
        ok = "✓" if actual == val else "✗"
        print(f"  {ok} {field_name} (col.{col}) = {val!r} (actual: {actual!r})")

    return await save_and_verify(cdp)


# --- Quadro RM (Sez. II-A, rigo RM31, multiple righi) ---


def _rm31_value_for_col(group: dict, col: int) -> str | None:
    """Compute the value for RM31 col.N from an aggregated RL group."""
    if col == 1:
        return group["tipo"]  # 'A' or 'B'
    if col == 2:
        return iso_to_ade_country_code(group["stato"]) or None
    if col == 3:
        v = Decimal(group["gross_eur"]).quantize(Decimal("1"))
        return str(v) if v != 0 else None
    if col == 4:
        return "26"
    if col == 8:
        imposta = Decimal(group["gross_eur"]) * Decimal("0.26")
        v = imposta.quantize(Decimal("1"))
        return str(v) if v != 0 else None
    return None


RM31_COLS_TO_SET: list[int] = [1, 2, 3, 4, 8]


async def fill_rm31_in_module(
    cdp: CDP,
    group: dict,
    module_n: int,
    dry_run: bool,
    force: bool,
) -> bool:
    """Fill RM31 in the current Modulo (one (stato, tipo) group per modulo).

    Unlike what its name suggests, RM31 is a single rigo per Modulo —
    different sources (e.g. dividends USA + interest IBKR) require
    distinct Moduli of Quadro RM (RM/1, RM/2, RM/3, ...). Within each
    modulo the field is always RM031xxx.

    Assumes the browser is on /quadro/RM/{module_n} already.
    """
    label = f"M{module_n}/RM31"
    print(f"\n  [{label}] {group['label']} ({group['count']} entries)")
    if dry_run:
        for col in RM31_COLS_TO_SET:
            v = _rm31_value_for_col(group, col)
            print(f"    col.{col} = {v!r}")
        return True

    existing = await field_value(cdp, "RM031001")
    if existing and not force:
        print(f"    SKIP: Modulo {module_n} RM031001 already filled ({existing!r}). Use --force.")
        return False

    for col in RM31_COLS_TO_SET:
        v = _rm31_value_for_col(group, col)
        field_name = f"RM031{col:03d}"
        if v is None:
            current = await field_value(cdp, field_name)
            if current:
                await set_field(cdp, field_name, "")
                print(f"    - col.{col} ({field_name}) cleared (was {current!r})")
            continue
        actual = await set_field(cdp, field_name, v)
        ok = "✓" if actual == v else "✗"
        print(f"    {ok} col.{col} ({field_name}) = {v!r} (actual: {actual!r})")
    return True


async def fill_rm(
    cdp: CDP, rl_lines: list[RLLine], year_yy: str, dry_run: bool, force: bool
) -> bool:
    groups = aggregate_rl_for_rm31(rl_lines)
    if not groups:
        print("\n=== Quadro RM — no RL lines to declare ===")
        return True

    print(
        f"\n=== Quadro RM — Sez. II-A, {len(groups)} righi RM31 (one per Modulo of Quadro RM) ==="
    )
    for idx, g in enumerate(groups, start=1):
        ade = iso_to_ade_country_code(g["stato"]) or "?"
        imposta = Decimal(g["gross_eur"]) * Decimal("0.26")
        print(
            f"  Modulo {idx}: tipo {g['tipo']}, stato {ade} ({g['stato']}), "
            f"lordo EUR {g['gross_eur']:.2f}, imposta EUR {imposta:.2f} — {g['label']}"
        )

    if dry_run:
        for idx, g in enumerate(groups, start=1):
            await fill_rm31_in_module(cdp, g, idx, dry_run=True, force=force)
        return True

    for module_n, group in enumerate(groups, start=1):
        url = quadro_url(year_yy, "RM", module_n)
        print(f"\n  Navigating to {url}")
        await cdp.navigate(url, expect_field_prefix="RM")

        # The form falls back to the highest existing Modulo when asked
        # for one that doesn't exist yet (e.g. /RM/3 silently serves M2's
        # data). Checking only that RM031001 exists is not enough — we
        # also need location.pathname to actually contain '/RM/N'. If it
        # doesn't, go back to N-1, click 'Aggiungi modulo', confirm, then
        # re-navigate.
        on_correct_module = await cdp.eval_js(f"location.pathname.endsWith('/RM/{module_n}')")
        if not on_correct_module:
            here = await cdp.eval_js("location.pathname")
            prev_url = quadro_url(year_yy, "RM", module_n - 1)
            print(f"  Form fell back to {here!r} — adding Modulo via {prev_url}")
            await cdp.navigate(prev_url, expect_field_prefix="RM")
            res = await click_add_module(cdp)
            print(f"  Aggiungi modulo: {res}")
            if res != "CLICKED":
                print(f"\nABORT: cannot add Modulo {module_n} (got {res})")
                return False
            await asyncio.sleep(0.5)
            modal = await confirm_modal_if_present(cdp)
            print(f"  Modal: {modal}")
            await asyncio.sleep(1.0)
            await cdp.navigate(url, expect_field_prefix="RM")
            # Sanity check: did the click actually create Modulo N?
            confirmed = await cdp.eval_js(f"location.pathname.endsWith('/RM/{module_n}')")
            if not confirmed:
                here = await cdp.eval_js("location.pathname")
                print(f"\nABORT: still on {here!r} after Aggiungi modulo — won't overwrite.")
                return False

        ok = await fill_rm31_in_module(cdp, group, module_n, dry_run=False, force=force)
        if not ok:
            print(f"\nABORT: RM31 Modulo {module_n} fill failed.")
            return False
        # Save this module before moving on (or finishing)
        if not await save_and_verify(cdp):
            print(f"\nABORT: Modulo {module_n} did not save cleanly.")
            return False

    return True


# --- main ---


async def main_async(args: argparse.Namespace) -> None:
    raw = yaml.safe_load(Path(args.yaml).read_text())
    report = TaxReport.model_validate(raw)
    year_yy = str(report.tax_year + 1)[-2:]
    print(f"Tax year {report.tax_year} -> RPF{year_yy}")

    ws, current_url = await connect_to_precompilata()
    cdp = CDP(ws)
    print(f"Connected to: {current_url}")

    try:
        await cdp.call("Page.enable")

        rt_failed = not args.rm_only and not await fill_rt(
            cdp, report, year_yy, args.dry_run, args.force
        )
        if rt_failed and not args.dry_run:
            print("\nABORT: Quadro RT did not save cleanly.")
            sys.exit(1)

        rm_failed = not args.rt_only and not await fill_rm(
            cdp, report.rl_lines, year_yy, args.dry_run, args.force
        )
        if rm_failed and not args.dry_run:
            print("\nABORT: Quadro RM did not save cleanly.")
            sys.exit(1)
    finally:
        await ws.close()


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("yaml", help="Path to decaf YAML report (e.g. private/decaf_2025.yaml)")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without filling the form")
    ap.add_argument(
        "--force", action="store_true", help="Overwrite fields that already have values"
    )
    ap.add_argument("--rt-only", action="store_true", help="Fill only Quadro RT")
    ap.add_argument("--rm-only", action="store_true", help="Fill only Quadro RM")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
