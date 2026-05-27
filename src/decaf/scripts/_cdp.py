"""Shared CDP helpers for AdE precompilata auto-fill scripts.

Talks to a Chrome instance running with --remote-debugging-port=9222.
The AdE form is a React app, so:
- field values must be set via the native HTMLInputElement value setter
  to bypass React's controlled-input identity check,
- a native input/change event must be dispatched so React's onChange
  prop fires,
- when re-applying the same value (e.g. to mark a previously-blank
  required dropdown as filled) we also invoke the onChange prop
  directly so the controlled-component state mutates even when the
  underlying value is unchanged.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request

import websockets

CDP_BASE = "http://localhost:9222"


async def connect_to_precompilata() -> tuple[websockets.ClientConnection, str]:
    """Find the open precompilata tab and return a CDP websocket to it."""
    with urllib.request.urlopen(f"{CDP_BASE}/json/list") as resp:
        tabs = json.loads(resp.read())
    for t in tabs:
        if "dichiarazioneprecompilata.agenziaentrate.gov.it" in t.get("url", ""):
            ws = await websockets.connect(t["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
            return ws, t["url"]
    raise RuntimeError(
        "No precompilata tab open. Navigate to "
        "dichiarazioneprecompilata.agenziaentrate.gov.it and try again."
    )


class CDP:
    """Minimal CDP wrapper: send a method, wait for the matching id."""

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

    async def navigate(self, url: str, expect_field_prefix: str = "") -> None:
        """Navigate and wait for the page to render fields with the given prefix.

        Defaults to no prefix check (just readyState=complete). Set
        expect_field_prefix='RW' / 'RT' / 'RM' to wait for that quadro's
        form fields to appear.
        """
        await self.call("Page.navigate", {"url": url})
        selector = (
            f"input[name^={expect_field_prefix}], select[name^={expect_field_prefix}]"
            if expect_field_prefix
            else "input, select"
        )
        for _ in range(20):
            ready = await self.eval_js(
                f"document.readyState === 'complete' && "
                f"document.querySelectorAll('{selector}').length > 0"
            )
            if ready:
                await asyncio.sleep(0.4)  # extra settle for angular/react hydration
                return
            await asyncio.sleep(0.25)
        raise RuntimeError(f"Page did not load in time: {url}")


# Setting a field value via native setter + dispatching the React-style
# onChange. See module docstring for the why.
_SET_FIELD_JS = r"""
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
    const propsKey = Object.keys(el).find(k => k.startsWith('__reactProps'));
    if (propsKey && el[propsKey] && typeof el[propsKey].onChange === 'function') {
        try {
            el[propsKey].onChange({
                target: el,
                currentTarget: el,
                type: 'change',
                bubbles: true,
                preventDefault: () => {},
                stopPropagation: () => {},
                persist: () => {},
            });
        } catch (e) { /* swallow */ }
    }
    el.dispatchEvent(new Event('blur', {bubbles: true}));
    return el.value;
})
"""


async def set_field(cdp: CDP, name: str, value: str) -> str:
    """Set a form field by name to value, return actual value after dispatch."""
    res = await cdp.eval_js(f"({_SET_FIELD_JS})('{name}', '{value}')")
    return str(res) if res is not None else ""


async def field_value(cdp: CDP, name: str) -> str:
    """Read the current value of a form field by name (empty if not present)."""
    res = await cdp.eval_js(f"document.querySelector('[name={name}]')?.value || ''")
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


async def click_save(cdp: CDP) -> str:
    """Click the 'Salva' button if enabled. Returns CLICKED/DISABLED/NOT FOUND."""
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
    return await cdp.eval_js(expr)  # type: ignore[return-value]


async def save_and_verify(cdp: CDP) -> bool:
    """Click Salva and check that the inline 'Salvataggio non effettuato' banner
    didn't appear. Returns True on success (including 'already pristine')."""
    await asyncio.sleep(0.3)
    state = await find_save_button_state(cdp)
    print(f"  Salva state: {state}")
    if not state.get("found"):
        return False
    if state.get("disabled"):
        print("  (Salva disabled — module already in sync, continuing)")
        return True
    res = await click_save(cdp)
    print(f"  Salva: {res}")
    await asyncio.sleep(1.5)
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

    Opens a confirm modal — call confirm_modal_if_present() after a short
    wait to actually add the module.
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


PRECOM_BASE = "https://dichiarazioneprecompilata.agenziaentrate.gov.it/PrecomWeb"


def quadro_url(year_yy: str, quadro: str, module_n: int = 1) -> str:
    """Build the precompilata URL for a quadro page.

    year_yy is the RPF year suffix ('26' for RPF26 = tax year 2025).
    """
    return f"{PRECOM_BASE}/compila/RPF{year_yy}/M/quadro/{quadro}/{module_n}"
