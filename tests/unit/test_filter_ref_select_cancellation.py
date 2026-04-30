"""Tests for #973 — dzFilterRefSelect swallows navigation-cancelled fetches.

Background: when htmx swap removes the `<select>` mid-fetch, browsers
reject the in-flight fetch with `TypeError: Failed to fetch`. The user
has navigated away — there's nothing useful to log. Pre-#973 the helper
unconditionally `console.warn`'d on every rejection, drowning genuine
backend failures in expected navigation-cancellation noise.

Fix: the `.catch` short-circuits on two signals:
  1. `selectEl` is no longer in the DOM (navigation removed it)
  2. `err.name === 'AbortError'` (future-proofing for an explicit
     AbortController if we add one)

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
