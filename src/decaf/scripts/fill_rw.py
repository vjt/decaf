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


def rw_field_value(line: dict, col: int) -> str | None:
    """Compute the value for column `col` of a Quadro RW row from a decaf rw_lines entry.

    Money values are quantized to whole EUR — the form has a separate ',00'
    cents box and the IVAFE rounding rule (art. 19 D.L. 201/2011) is whole
    EUR anyway. Returns None for zero money values so the caller leaves the
    field blank — the AdE form rejects an explicit '0' in valore iniziale /
    valore finale ("formato non corretto" + Salva fails silently).

    NOT set by this script:
    - col.6  (Criterio determinazione valore) — computed server-side
    - col.30 (IVAFE dovuta) — computed server-side from cols. 5, 7, 8, 10
    """
    if col == 1:
        return "1"  # codice titolo possesso: proprietà
    if col == 3:
        return str(line["codice_investimento"])
    if col == 4:
        return iso_to_ade_country_code(line["country"])
    if col == 5:
        return "100"  # quota di possesso
    if col == 7:
        v = Decimal(line["initial_value_eur"]).quantize(Decimal("1"))
        return str(v) if v != 0 else None
    if col == 8:
        v = Decimal(line["final_value_eur"]).quantize(Decimal("1"))
        return str(v) if v != 0 else None
    if col == 10:
        return str(line["days_held"])
    return None


# Columns to set in order. col.6 and col.30 are computed by the AdE form.
RW_COLS_TO_SET: list[int] = [1, 3, 4, 5, 7, 8, 10]
# Each Modulo of the Quadro RW contains up to ROWS_PER_MODULE righi (RW1..RW5).
ROWS_PER_MODULE = 5


async def confirm_modal_if_present(cdp: CDP) -> str:
    """If a 'Conferma' modal is open, click 'Conferma'. Returns status."""
    expr = r"""
    (() => {
        const modal = document.querySelector('.modal.show, .modal-content');
        if (!modal) return 'NO_MODAL';
        const btn = Array.from(modal.querySelectorAll('button')).find(b =>
            (b.textContent || '').trim() === 'Conferma'
        );
        if (!btn) return 'NO_CONFIRM_BUTTON';
        btn.click();
        return 'CONFIRMED';
    })()
    """
    return await cdp.eval_js(expr)  # type: ignore[return-value]


async def click_add_module(cdp: CDP) -> str:
    """Click the 'Aggiungi modulo' link. Returns CLICKED/DISABLED/NOT FOUND.

    Opens a confirm modal; call confirm_modal_if_present() after a short wait.
    """
    expr = r"""
    (() => {
        const links = Array.from(document.querySelectorAll('a, button'));
        const add = links.find(b => /aggiungi modulo/i.test(b.textContent || ''));
        if (!add) return 'NOT FOUND';
        const cls = (add.className || '').toString();
        if (cls.includes('disabled')) return 'DISABLED';
        add.click();
        return 'CLICKED';
    })()
    """
    return await cdp.eval_js(expr)  # type: ignore[return-value]


async def fill_row(cdp: CDP, line: dict, row_n: int, dry_run: bool, force: bool) -> bool:
    """Fill row RW{row_n} (1..5) of the current module with values from a decaf entry.

    Returns True on success (or dry-run), False if skipped due to existing data.
    """
    label = f"M?/RW{row_n}"
    print(f"  [{label}] {line['symbol']} {line.get('isin', '')} ({line['country']})")
    if dry_run:
        for col in RW_COLS_TO_SET:
            v = rw_field_value(line, col)
            print(f"    col.{col:2d} = {v!r}")
        return True

    existing = await cdp.eval_js(f"document.querySelector('[name=RW{row_n:03d}001]')?.value || ''")
    if existing and not force:
        print(f"    SKIP: row {row_n} already filled (col.1={existing!r}). Use --force.")
        return False

    for col in RW_COLS_TO_SET:
        v = rw_field_value(line, col)
        if v is None or v == "":
            continue
        field_name = f"RW{row_n:03d}{col:03d}"
        actual = await set_field(cdp, field_name, v)
        ok = "✓" if actual == v else "✗"
        print(f"    {ok} col.{col:2d} ({field_name}) = {v!r} (actual: {actual!r})")
    return True


async def save_module(cdp: CDP) -> bool:
    """Click 'Salva' and verify the save succeeded. Returns True on success.

    The form may report 'Salvataggio non effettuato' inline (e.g. when a
    field value is rejected by validation); detect that and treat as failure.
    """
    await asyncio.sleep(0.3)
    state = await find_save_button_state(cdp)
    print(f"  Salva state: {state}")
    if not state.get("found") or state.get("disabled"):
        return False
    await click_save(cdp)
    await asyncio.sleep(1.5)
    # Check for inline error banner
    err = await cdp.eval_js(
        r"""
        (() => {
            const txt = document.body.innerText || '';
            const m = txt.match(/Salvataggio non effettuato[^\n]*\n?[^\n]*/);
            return m ? m[0].slice(0, 300) : '';
        })()
        """
    )
    if err:
        print(f"  ERROR: {err}")
        return False
    return True


async def add_module(cdp: CDP, next_module_n: int) -> bool:
    """Click 'Aggiungi modulo' and confirm. Returns True if module was created."""
    print(f"  Clicking 'Aggiungi modulo' to create Modulo {next_module_n}...")
    res = await click_add_module(cdp)
    print(f"  Aggiungi modulo: {res}")
    if res != "CLICKED":
        return False
    await asyncio.sleep(0.5)
    modal = await confirm_modal_if_present(cdp)
    print(f"  Modal: {modal}")
    return modal in ("CONFIRMED", "NO_MODAL")


async def main_async(args: argparse.Namespace) -> None:
    report = yaml.safe_load(Path(args.yaml).read_text())
    rw = report["rw_lines"]
    year = str(report["tax_year"] + 1)[-2:]  # RPF26 for tax_year=2025
    n_modules = (len(rw) + ROWS_PER_MODULE - 1) // ROWS_PER_MODULE
    print(
        f"Tax year {report['tax_year']} -> RPF{year}, "
        f"{len(rw)} RW lines -> {n_modules} Modulo(s) of up to {ROWS_PER_MODULE} righi each"
    )

    ws, current_url = await _connect_to_page()
    cdp = CDP(ws)
    print(f"Connected to: {current_url}")

    try:
        await cdp.call("Page.enable")

        for module_n in range(args.start_module, n_modules + 1):
            # Lots that go into this module (slice of rw_lines)
            lo = (module_n - 1) * ROWS_PER_MODULE
            hi = min(lo + ROWS_PER_MODULE, len(rw))
            module_lines = rw[lo:hi]
            print(f"\n=== Modulo {module_n}/{n_modules} (lots {lo + 1}..{hi} of {len(rw)}) ===")

            if not args.dry_run:
                url = f"{PRECOM_BASE}/compila/RPF{year}/M/quadro/RW/{module_n}"
                print(f"  Navigating to {url}")
                await cdp.navigate(url)

            # Fill each row in the module
            for row_idx, line in enumerate(module_lines, start=1):
                ok = await fill_row(cdp, line, row_idx, args.dry_run, args.force)
                if not ok and not args.dry_run and not args.continue_on_error:
                    print("\nABORT: row skipped. Use --continue-on-error to skip.")
                    sys.exit(1)

            if args.dry_run:
                continue

            # Save the module
            if not await save_module(cdp):
                if not args.continue_on_error:
                    print(f"\nABORT: Modulo {module_n} did not save cleanly.")
                    sys.exit(1)
                print(f"  WARN: Modulo {module_n} not saved, continuing")
                continue

            # Add next module if we have more lots to fill
            if module_n < n_modules:
                if not await add_module(cdp, module_n + 1):
                    print(f"\nABORT: could not add Modulo {module_n + 1}.")
                    sys.exit(1)
                # The 'Aggiungi modulo' navigates to /quadro/RW/{module_n+1}
                # automatically — next loop iteration navigates explicitly anyway.
                await asyncio.sleep(1.0)
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
