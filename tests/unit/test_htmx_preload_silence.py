"""Tests for #967 — silence htmx-ext-preload console errors on 401/403.

Background: `htmx-ext-preload` fires speculative XHRs on hover/mousedown,
each carrying `HX-Preloaded: true`. When a low-privilege persona hovers a
link they don't have permission for, the prefetch returns 401/403 and
htmx logs a console error — pure noise that drowns real signal.

Fix: `dz-alpine.js` installs a `htmx:responseError` listener that
consumes events from prefetch requests (HX-Preloaded: true) with 401/403
status. Real user-clicked navigations still log normally.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DZ_ALPINE = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"


def test_response_error_listener_present() -> None:
    """The htmx:responseError listener for #967 must be present."""
    js = DZ_ALPINE.read_text()
    # Multiple `htmx:responseError` listeners may exist — ensure at least
    # one of them is the prefetch-silence handler keyed off HX-Preloaded.
    assert "htmx:responseError" in js and "HX-Preloaded" in js, (
        "Missing the htmx-preload silence listener (#967). "
        "Look for `addEventListener('htmx:responseError', ...)` that "
        "checks `HX-Preloaded` header in dz-alpine.js."
    )


def test_silence_filters_on_401_and_403() -> None:
    """Listener must filter on 401/403 specifically (not all error statuses)."""
    js = DZ_ALPINE.read_text()
    # Find the relevant block by anchoring on HX-Preloaded.
    idx = js.find("HX-Preloaded")
    assert idx >= 0
    block = js[max(0, idx - 600) : idx + 200]
    assert "401" in block and "403" in block, (
        "The preload-silence listener must filter on status 401 or 403 — "
        "other errors (5xx, 404) should still surface as real signal (#967)."
    )


def test_silence_calls_prevent_default() -> None:
    """Consuming the event requires `preventDefault()`."""
    js = DZ_ALPINE.read_text()
    # Anchor on the actual code reference (not the comment block).
    idx = js.find('headers["HX-Preloaded"]')
    assert idx >= 0
    block = js[idx : idx + 400]
    assert "preventDefault" in block, (
        "The listener must call `event.preventDefault()` to suppress the console error path (#967)."
    )


def test_silence_does_not_apply_when_header_missing() -> None:
    """The listener must early-return when HX-Preloaded is not 'true'."""
    js = DZ_ALPINE.read_text()
    idx = js.find('headers["HX-Preloaded"]')
    assert idx >= 0, "Listener must read headers['HX-Preloaded'] explicitly"
    # Window covering the conditional + early return.
    block = js[idx : idx + 200]
    assert "return" in block, (
        "Listener must early-return when HX-Preloaded != 'true' so real "
        "(non-prefetch) errors keep logging (#967)."
    )
