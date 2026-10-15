"""Client-script regressions pinned on the shipped source, one row per fix.

These scripts have no DOM test runner on the Dazzle side (``feedback-widget.js``
is the exception: ``test_feedback_widget_client.py`` runs it under Node). Each
row names the fix it guards and the source fragments that fix consists of,
optionally inside one region of the file (``anchor`` .. ``end`` or a character
``window``) and optionally in order. Behavioural coverage of the HaTchi-MaXchi
controllers lives in the HM gallery two-engine tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
JS = "src/dazzle/page/runtime/static/js"
HM_CONTROLLERS = "packages/hatchi-maxchi/controllers"


@dataclass(frozen=True)
class Pin:
    path: str
    present: tuple[str, ...]
    absent: tuple[str, ...] = ()
    anchor: str | None = None  # region starts at this text...
    last: bool = False  # ...its last occurrence (default: first)
    end: str | None = None  # ...and stops at this text
    window: int | None = None  # ...or after this many characters
    ordered: bool = False  # ``present`` must appear in this order
    pattern: str | None = field(default=None)  # a regex the whole file must match


_PINS: dict[str, Pin] = {
    # #853: stale hidden-column keys are pruned before the first style write.
    "grid-cols-prune-before-apply-853": Pin(
        f"{HM_CONTROLLERS}/dz-grid-cols.js",
        ("prune(grids[g])", "apply(grids[g])"),
        anchor="// Init:",
        ordered=True,
    ),
    "grid-cols-prune-skips-unrendered-and-persists-853": Pin(
        f"{HM_CONTROLLERS}/dz-grid-cols.js",
        (
            "function prune(",
            "if (!cells.length) return;",
            "if (cleaned.length !== hidden.length) writeHidden(root, cleaned);",
        ),
    ),
    "grid-cols-reset-clears-storage-853": Pin(
        f"{HM_CONTROLLERS}/dz-grid-cols.js",
        ("localStorage.removeItem",),
        anchor="data-dz-grid-cols-reset",
        last=True,
        window=800,
    ),
    # #862: Safari ignores <a download> for same-origin text/csv; fetch -> Blob.
    "download-csv-fetch-blob-862": Pin(
        f"{JS}/dz-utils.js",
        (
            "window.dz.downloadCsv",
            'await fetch(url, { credentials: "same-origin" })',
            "await response.blob()",
            "URL.createObjectURL(blob)",
            "link.download = filename",
            "URL.revokeObjectURL(objectUrl)",
            'endpoint + "&format=csv"',
            'endpoint + "?format=csv"',
            "window.dz.toast(",
            "CSV export failed",
        ),
    ),
    # #973: navigation-cancelled ref-select fetches are aborted and swallowed;
    # real failures still warn.
    "filter-ref-select-aborts-on-navigation-973": Pin(
        f"{JS}/dz-utils.js",
        (
            "new AbortController()",
            "controller.signal",
            "controller.abort",
            "AbortError",
            "document.body.contains(selectEl)",
            "console.warn",
        ),
        anchor="window.dz.filterRefSelect = function",
        end="// Auto-mount",
    ),
    "filter-ref-select-detached-check-before-warn-973": Pin(
        f"{JS}/dz-utils.js",
        ("document.body.contains(selectEl)", "console.warn"),
        anchor="window.dz.filterRefSelect = function",
        end="// Auto-mount",
        ordered=True,
    ),
    "filter-ref-select-swap-listener-one-shot-973": Pin(
        f"{JS}/dz-utils.js",
        ("once: true",),
        anchor='addEventListener("htmx:before:swap"',
        window=200,
    ),
    "filter-ref-select-pagehide-listener-one-shot-973": Pin(
        f"{JS}/dz-utils.js",
        ("once: true",),
        anchor='addEventListener("pagehide"',
        window=200,
    ),
    "filter-ref-select-listeners-removed-in-finally-973": Pin(
        f"{JS}/dz-utils.js",
        ('removeEventListener("htmx:before:swap"', 'removeEventListener("pagehide"'),
        anchor=".finally(",
        window=600,
    ),
    # #974: #main-content's view-transition-name is cleared for the swap and
    # handed back to the CSS cascade after settle.
    "view-transition-cleared-before-swap-974": Pin(
        f"{JS}/dz-islands.js",
        ("main-content", 'viewTransitionName = "none"'),
        anchor='"htmx:before:swap"',
        window=2000,
    ),
    "view-transition-restored-after-settle-974": Pin(
        f"{JS}/dz-islands.js",
        ("main-content", 'viewTransitionName = ""'),
        anchor='"htmx:after:settle"',
        window=2000,
    ),
    # Widget bridge: mounts on settle, unmounts before swap, no global leak.
    "component-bridge-lifecycle": Pin(
        f"{JS}/dz-component-bridge.js",
        ("htmx:before:swap", "htmx:after:settle", "data-dz-widget", "registerWidget"),
        pattern=r"\A\s*(?:/\*.*?\*/\s*)?\(function",
    ),
    # Toast host (C3 orphan sweep): both event shapes, server-parity markup,
    # text-only message, pause/cap, delays, leave motion, icons, cues.
    "toast-host-renders-server-parity-markup": Pin(
        f"{JS}/dz-toast.js",
        (
            '"showToast"',
            '"toast"',
            'getElementById("dz-toast")',
            "dz-toast-level",
            "data-dz-remove-after",
            "dz-toast__title",
            "dz-toast__message",
            "dz-toast__actions",
            "textContent",
            "__dzToastPause",
            "__dzToastResume",
            "data-dz-toast-cap",
            "data-dz-toast-dismiss",
            'DEFAULT_DELAY = "8s"',
            'ERROR_DELAY = "10s"',
            "dz-toast__progress",
            "dz-toast-leave",
            "animationend",
            "dz-toast__icon",
            "makeAvatar",
            "data-dz-toast-composition",
            "wireSwipe",
            "playEnterCue",
            "dzCue",
        ),
        absent=("innerHTML",),
    ),
    # Opt-in sound cues (stem chrome-cue-opt-in): silent by default, synthesised.
    "cue-opt-in-and-synthesised": Pin(
        f"{HM_CONTROLLERS}/dz-cue.js",
        ("dz-sound", "data-dz-cue-sound", "prefers-reduced-motion", "window.dzCue", "AudioContext"),
        absent=("cloudinary",),
    ),
    "cue-bundled-before-toast": Pin(
        "packages/hatchi-maxchi/build.py",
        ("controllers/dz-cue.js", "controllers/dz-toast.js"),
        ordered=True,
    ),
    # Cycle 2170: grid hx-get carries include_closed / as_of; junk does not invent.
    "grid-temporal-leftover-keys-2170": Pin(
        f"{HM_CONTROLLERS}/dz-grid.js",
        (
            "function parseIncludeClosed",
            "function parseAsOf",
            "include_closed: 1",
            "as_of: 1",
            "readIncludeClosed(root)",
            "readAsOf(root)",
            'q.push("include_closed=" + encodeURIComponent(ic.value))',
            'q.push("as_of=" + encodeURIComponent(ao.value))',
        ),
    ),
    "grid-temporal-not-field-filters-in-gallery-mock-2170": Pin(
        "packages/hatchi-maxchi/site/build_site.py",
        ("include_closed: 1", "as_of: 1", "GRID_CONTROL"),
    ),
    "grid-contract-names-temporal-keys-2170": Pin(
        "packages/hatchi-maxchi/contracts/grid.py",
        ("include_closed", "as_of"),
    ),
    # #26: the site theme toggle markup, script and dark-mode tokens.
    "site-theme-toggle-markup-26": Pin(
        "src/dazzle/http/runtime/site_routes.py",
        ("dz-theme-toggle", "Toggle dark mode", "dz-theme-toggle__sun", "dz-theme-toggle__moon"),
    ),
    "site-theme-script-26": Pin(
        "src/dazzle/page/static/js/site.js",
        ("initTheme()", "toggleTheme()", "prefers-color-scheme", "dz-theme-variant"),
    ),
    "site-dark-tokens-declared-and-consumed-26": Pin(
        "packages/hatchi-maxchi/base/design-system.css",
        ("--dz-header-bg:", "--dz-logo-color:", "--dz-text-body:"),
    ),
    "site-dark-tokens-consumed-26": Pin(
        "packages/hatchi-maxchi/components/sitespec.css",
        ("var(--dz-header-bg)", "var(--dz-logo-color)", "var(--dz-text-body)"),
    ),
}


def _region(src: str, pin: Pin) -> str:
    if pin.anchor is None:
        return src
    start = src.rfind(pin.anchor) if pin.last else src.find(pin.anchor)
    assert start >= 0, f"anchor {pin.anchor!r} is gone"
    if pin.end is not None:
        stop = src.find(pin.end, start)
        assert stop > start, f"end marker {pin.end!r} is gone"
        return src[start:stop]
    return src[start : start + pin.window] if pin.window else src[start:]


@pytest.mark.parametrize("pin", list(_PINS.values()), ids=list(_PINS))
def test_source_pin(pin: Pin) -> None:
    src = (REPO / pin.path).read_text(encoding="utf-8")
    region = _region(src, pin)
    positions = []
    for text in pin.present:
        idx = region.find(text)
        assert idx >= 0, f"{pin.path}: {text!r} is gone"
        positions.append(idx)
    if pin.ordered:
        assert positions == sorted(positions), f"{pin.path}: order changed: {pin.present}"
    for text in pin.absent:
        assert text not in region, f"{pin.path}: {text!r} is back"
    if pin.pattern:
        assert re.match(pin.pattern, src, re.S), f"{pin.path} does not match {pin.pattern!r}"


def test_dazzle_toast_host_is_the_hm_controller() -> None:
    """Dual-lock: the Dazzle static copy must not drift from the HM controller."""
    dazzle = (REPO / JS / "dz-toast.js").read_text(encoding="utf-8")
    assert dazzle == (REPO / HM_CONTROLLERS / "dz-toast.js").read_text(encoding="utf-8")
