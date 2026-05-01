"""Tests for #973 — dzFilterRefSelect swallows navigation-cancelled fetches.

Background: when navigation cancels the fetch mid-flight, browsers
reject with `TypeError: Failed to fetch`. The user has navigated
away — there's nothing useful to log.

#973 round 1 (v0.63.17): checked `document.body.contains(selectEl)`
in `.catch`. Worked for in-page htmx swaps but failed for full
browser navigation (Playwright `page.goto`, link clicks, form
submits) — the fetch rejected BEFORE the element left the DOM, so
the contains-check fired too early and the warn still logged.

#973 round 2 (v0.63.21): wire an explicit `AbortController` to two
events:
  - `htmx:beforeSwap` (htmx is about to morph the DOM)
  - `pagehide` (full browser navigation, also covers BFCache)

Both fire BEFORE the fetch is cancelled, so the rejection arrives as
a known `AbortError` we can swallow cleanly. The `document.body.contains`
check stays as defense-in-depth for ancestor-removal edge cases.

Real failures (5xx, JSON parse) still log because they arrive while
the element is still mounted with a non-AbortError name.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_ALPINE = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"


def _helper_block() -> str:
    """Return the dzFilterRefSelect helper body."""
    js = DZ_ALPINE.read_text()
    start = js.find("window.dz.filterRefSelect = function")
    assert start >= 0, "missing dz.filterRefSelect helper"
    end = js.find("\nwindow.dzFilterRefSelect", start)
    assert end > start
    return js[start:end]


def test_catch_short_circuits_when_select_detached() -> None:
    """The catch must early-return when selectEl is no longer in the DOM."""
    block = _helper_block()
    assert "document.body.contains(selectEl)" in block, (
        "Helper must check `document.body.contains(selectEl)` in the "
        ".catch to swallow navigation-cancelled fetches (#973)."
    )


def test_catch_short_circuits_on_abort_error() -> None:
    """The catch must also short-circuit on err.name === 'AbortError'."""
    block = _helper_block()
    assert "AbortError" in block, (
        "Helper must short-circuit on AbortError in the .catch — "
        "future-proofing for explicit AbortController cancellation (#973)."
    )


def test_real_failures_still_log() -> None:
    """The console.warn must remain in place for real failures."""
    block = _helper_block()
    # The console.warn is the fallback after the early returns.
    assert "console.warn" in block, (
        "Helper must still console.warn for real failures (5xx, JSON "
        "parse errors) — only navigation-cancelled fetches should be "
        "swallowed (#973)."
    )
    # Order matters: early-return checks must come before the warn.
    contains_idx = block.find("document.body.contains(selectEl)")
    warn_idx = block.find("console.warn")
    assert contains_idx > 0 and warn_idx > 0
    assert contains_idx < warn_idx, (
        "The DOM-detached check must happen BEFORE console.warn — "
        "otherwise navigation-cancelled fetches still log (#973)."
    )


# ───────────────── #973 round 2: AbortController + pagehide ─────────────────


def test_uses_abort_controller() -> None:
    """An explicit AbortController must be created per fetch."""
    block = _helper_block()
    assert "new AbortController()" in block, (
        "Helper must instantiate an AbortController so we can deterministically "
        "cancel the fetch on navigation events (#973 round 2)."
    )
    assert "controller.signal" in block, (
        "Fetch must receive `signal: controller.signal` so the AbortController "
        "can actually cancel it (#973 round 2)."
    )


def test_aborts_on_htmx_before_swap() -> None:
    """The controller must abort on htmx:beforeSwap."""
    block = _helper_block()
    assert "htmx:beforeSwap" in block and "controller.abort" in block, (
        "Helper must wire `controller.abort()` to `htmx:beforeSwap` so "
        "in-page htmx swaps cancel the fetch deterministically (#973 round 2)."
    )


def test_aborts_on_pagehide() -> None:
    """The controller must also abort on pagehide (full browser nav)."""
    block = _helper_block()
    assert "pagehide" in block, (
        "Helper must wire abort to `pagehide` so full browser navigation "
        "(page.goto, link clicks, form submits, BFCache) cancels the "
        "fetch as AbortError rather than racing through as TypeError "
        "(#973 round 2 — round 1 missed this code path)."
    )


def test_listeners_are_one_shot() -> None:
    """Abort listeners must be `{ once: true }` to prevent leaks."""
    block = _helper_block()
    # Both listeners attached with once: true.
    htmx_listener_idx = block.find('addEventListener("htmx:beforeSwap"')
    pagehide_listener_idx = block.find('addEventListener("pagehide"')
    assert htmx_listener_idx > 0 and pagehide_listener_idx > 0
    # Find `{ once: true }` near each.
    htmx_window = block[htmx_listener_idx : htmx_listener_idx + 200]
    pagehide_window = block[pagehide_listener_idx : pagehide_listener_idx + 200]
    assert "once: true" in htmx_window, (
        "htmx:beforeSwap listener must use `{ once: true }` so it self-removes "
        "after firing (#973 round 2)."
    )
    assert "once: true" in pagehide_window, (
        "pagehide listener must use `{ once: true }` (#973 round 2)."
    )


def test_listeners_cleaned_up_in_finally() -> None:
    """`.finally()` must remove both listeners to prevent accumulation."""
    block = _helper_block()
    assert ".finally(" in block, (
        "Helper must use `.finally()` to remove abort listeners so they "
        "don't accumulate across many filter dropdowns on one page (#973 round 2)."
    )
    finally_idx = block.find(".finally(")
    finally_block = block[finally_idx : finally_idx + 600]
    assert "removeEventListener" in finally_block and "htmx:beforeSwap" in finally_block, (
        "finally must remove the htmx:beforeSwap listener (#973 round 2)."
    )
    assert "removeEventListener" in finally_block and "pagehide" in finally_block, (
        "finally must remove the pagehide listener (#973 round 2)."
    )
