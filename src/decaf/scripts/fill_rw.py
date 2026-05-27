"""Auto-populate the AdE precompilata RW form via CDP.

Reads a decaf YAML report and pushes each `rw_lines[i]` into a Modulo N
of the Quadro RW form running in a Chrome instance with --remote-debugging-port=9222.

USAGE:
    chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-prof &
    # log into https://dichiarazioneprecompilata.agenziaentrate.gov.it
    # open the Quadro RW page for RPF<YY> manually
    python -m decaf.scripts.fill_rw private/decaf_2025.yaml

    # add --dry-run to print actions without filling
    # add --start-module N to skip the first N-1 lines (already filled)

Safety:
- The script will refuse to overwrite a module that already has a non-empty
  RW00N001 (codice titolo possesso). Pass --force to clobber.
- It never clicks 'Calcola, stampa e invia'. The final review + submit is
  always a manual step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

import websockets
import yaml

from decaf.country_codes import iso_to_ade_country_code

CDP_BASE = "http://localhost:9222"
PRECOM_BASE = "https://dichiarazioneprecompilata.agenziaentrate.gov.it/PrecomWeb"


async def _connect_to_page() -> tuple[websockets.ClientConnection, str]:
    """Find the open precompilata tab and return a CDP websocket to it."""
    import urllib.request

    with urllib.request.urlopen(f"{CDP_BASE}/json/list") as resp:
        tabs = json.loads(resp.read())
    for t in tabs:
        if "dichiarazioneprecompilata.agenziaentrate.gov.it" in t.get("url", ""):
            ws = await websockets.connect(t["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
            return ws, t["url"]
    raise RuntimeError(
        "No precompilata tab open. Navigate to dichiarazioneprecompilata.agenziaentrate.gov.it "
        "and try again."
    )


class CDP:
    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._id = 0

    async def call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"CDP {method} failed: {msg['error']}")
                return msg

    async def eval_js(self, expr: str, await_promise: bool = False) -> object:
        r = await self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
        )
        return r["result"]["result"].get("value")

    async def navigate(self, url: str) -> None:
        await self.call("Page.navigate", {"url": url})
        # wait for the page to render fields
        for _ in range(20):
            ready = await self.eval_js(
                "document.readyState === 'complete' && "
                "document.querySelectorAll('input[name^=RW]').length > 0"
            )
            if ready:
                # extra settle so angular hydrates
                await asyncio.sleep(0.4)
                return
            await asyncio.sleep(0.25)
        raise RuntimeError(f"Page did not load in time: {url}")


# Field values are dispatched with native input + change events so angular
# picks them up.
SET_FIELD_JS = r"""
((name, value) => {
    const el = document.querySelector(`[name=${name}]`);
    if (!el) return 'NOT FOUND';
    const proto = el.tagName === 'SELECT'
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    return el.value;
})
"""


async def set_field(cdp: CDP, name: str, value: str) -> str:
    """Set a form field by name to value, return the actual value after dispatch."""
    res = await cdp.eval_js(f"({SET_FIELD_JS})('{name}', '{value}')")
    return str(res) if res is not None else ""


async def find_save_button_state(cdp: CDP) -> dict:
    expr = r"""
    (() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const save = btns.find(b => (b.textContent || '').trim() === 'Salva');
        if (!save) return {found: false};
        return {found: true, disabled: save.disabled};
    })()
    """
    return await cdp.eval_js(expr)  # type: ignore[return-value]


async def click_save(cdp: CDP) -> None:
    """Click the 'Salva' button if enabled."""
    expr = r"""
    (() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const save = btns.find(b => (b.textContent || '').trim() === 'Salva');
        if (!save) return 'NOT FOUND';
        if (save.disabled) return 'DISABLED';
        save.click();
        return 'CLICKED';
    })()
    """
    res = await cdp.eval_js(expr)
    print(f"  Salva: {res}")


def rw_field_value(line: dict, n: int, col: int) -> str | None:
    """Compute the value for field RW{n:03}{col:03} from a decaf rw_lines entry.

    Money values are quantized to whole EUR — the form has separate ',00'
    cents box and the IVAFE rounding rule (art. 19 D.L. 201/2011) is whole
    EUR anyway.

    NOTE: col.30 (IVAFE dovuta) is NOT set by this script — the AdE form
    computes it server-side from col.7 (valore iniziale), col.8 (valore
    finale), col.10 (giorni) and col.5 (quota possesso).
    """
    if col == 1:
        return "1"  # codice titolo possesso: proprietà
    if col == 3:
        return str(line["codice_investimento"])
    if col == 4:
        return iso_to_ade_country_code(line["country"])
    if col == 5:
        return "100"  # quota di possesso
    if col == 6:
        return "1"  # criterio determinazione valore: valore di mercato
    if col == 7:
        return str(Decimal(line["initial_value_eur"]).quantize(Decimal("1")))
    if col == 8:
        return str(Decimal(line["final_value_eur"]).quantize(Decimal("1")))
    if col == 10:
        return str(line["days_held"])
    return None


# Columns to set in order (col.30 IVAFE is computed by the AdE form)
RW_COLS_TO_SET: list[int] = [1, 3, 4, 5, 6, 7, 8, 10]


async def click_add_module(cdp: CDP) -> str:
    """Click the 'Aggiungi modulo' link if enabled. Returns the new URL or a status code."""
    expr = r"""
    (() => {
        const links = Array.from(document.querySelectorAll('a, button'));
        const add = links.find(b => /aggiungi modulo/i.test(b.textContent || ''));
        if (!add) return 'NOT FOUND';
        const cls = (add.className || '').toString();
        if (cls.includes('disabled')) return 'DISABLED';
        // The link has href but is rendered by router — click is the safe path
        add.click();
        return 'CLICKED';
    })()
    """
    return await cdp.eval_js(expr)  # type: ignore[return-value]


async def fill_module(cdp: CDP, line: dict, module_n: int, dry_run: bool, force: bool) -> bool:
    """Fill RW module N with values from a decaf rw_lines entry.

    Assumes the browser is already on Quadro RW page for module N (either
    because it's the first module or because we just clicked 'Aggiungi modulo').
    Returns True if saved cleanly.
    """
    print(f"\n[RW{module_n}] {line['symbol']} {line.get('isin', '')} ({line['country']})")
    if dry_run:
        for col in RW_COLS_TO_SET:
            v = rw_field_value(line, module_n, col)
            print(f"  col.{col:2d} = {v!r}")
        return False

    # safety: check if module already has values
    existing = await cdp.eval_js(
        f"document.querySelector('[name=RW{module_n:03d}001]')?.value || ''"
    )
    if existing and not force:
        print(f"  SKIP: module {module_n} already filled (col.1={existing!r}). Use --force.")
        return False

    for col in RW_COLS_TO_SET:
        v = rw_field_value(line, module_n, col)
        if v is None or v == "":
            print(f"  col.{col:2d}: SKIP (no value)")
            continue
        field_name = f"RW{module_n:03d}{col:03d}"
        actual = await set_field(cdp, field_name, v)
        ok = "✓" if actual == v else "✗"
        print(f"  {ok} col.{col:2d} ({field_name}) = {v!r} (actual: {actual!r})")

    await asyncio.sleep(0.3)
    state = await find_save_button_state(cdp)
    print(f"  Salva state: {state}")
    if state.get("found") and not state.get("disabled"):
        await click_save(cdp)
        # wait for save to settle
        await asyncio.sleep(1.5)
        return True
    return False


async def main_async(args: argparse.Namespace) -> None:
    report = yaml.safe_load(Path(args.yaml).read_text())
    rw = report["rw_lines"]
    year = str(report["tax_year"] + 1)[-2:]  # RPF26 for tax_year=2025
    print(f"Tax year {report['tax_year']} -> RPF{year}, {len(rw)} RW lines")

    ws, current_url = await _connect_to_page()
    cdp = CDP(ws)
    print(f"Connected to: {current_url}")

    try:
        await cdp.call("Page.enable")
        # Navigate to the first module the user wants (skip in dry-run mode)
        if not args.dry_run:
            start_url = f"{PRECOM_BASE}/compila/RPF{year}/M/quadro/RW/{args.start_module}"
            print(f"Navigating to {start_url}")
            await cdp.navigate(start_url)

        for i, line in enumerate(rw, start=1):
            if i < args.start_module:
                continue
            saved = await fill_module(cdp, line, i, args.dry_run, args.force)
            if not saved and not args.dry_run:
                if not args.continue_on_error:
                    print(
                        f"\nABORT: module {i} did not save cleanly. "
                        "Use --continue-on-error to skip."
                    )
                    sys.exit(1)
                continue
            # Need to click 'Aggiungi modulo' to create module i+1 (unless this was the last)
            if not args.dry_run and i < len(rw):
                print(f"  Clicking 'Aggiungi modulo' to create RW{i + 1}...")
                res = await click_add_module(cdp)
                print(f"  Aggiungi modulo: {res}")
                if res != "CLICKED":
                    print(f"\nABORT: cannot add module {i + 1}: {res}")
                    sys.exit(1)
                # wait for navigation to new module
                for _ in range(20):
                    await asyncio.sleep(0.2)
                    cur = await cdp.eval_js("location.pathname")
                    if isinstance(cur, str) and cur.rstrip("/").endswith(f"/RW/{i + 1}"):
                        await asyncio.sleep(0.5)
                        break
                else:
                    print(f"  WARN: did not detect navigation to RW/{i + 1}")
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
        "--force", action="store_true", help="Overwrite modules that already have values"
    )
    ap.add_argument("--start-module", type=int, default=1, help="Start from module N (1-indexed)")
    ap.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Skip modules that fail to save instead of aborting",
    )
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
