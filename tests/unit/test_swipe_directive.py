"""Tests for #958 cycle 3 — x-swipe Alpine directive.

Mirrors the test approach for x-pull-to-refresh: pin the
registration path, the touch-only gating, the threshold + dispatch
contract, and the heuristics that distinguish a swipe from a
scroll / drag / tap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DZ_ALPINE_JS = Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/js/dz-alpine.js"


@pytest.fixture(scope="module")
def js() -> str:
    assert DZ_ALPINE_JS.is_file(), f"dz-alpine.js not found at {DZ_ALPINE_JS}"
    return DZ_ALPINE_JS.read_text()


def test_directive_registered(js: str) -> None:
    """Alpine.directive('swipe', ...) must be present so x-swipe in
    templates resolves to the handler."""
    assert 'Alpine.directive("swipe"' in js


def test_touch_only_via_pointer_coarse(js: str) -> None:
    """Desktop mouse drag is ambiguous with text selection — directive
    no-ops on mouse-primary inputs (same gate as pull-to-refresh)."""
    # The swipe directive lives below the pull-to-refresh one; both
    # use the same matchMedia check. Verify at least one usage.
    assert "(pointer: coarse)" in js


def test_dispatches_swipe_left_and_right_events(js: str) -> None:
    """The dispatch contract is `swipe-left` / `swipe-right`
    CustomEvents — chosen so adopters can wire both directions to
    independent actions."""
    assert '"swipe-left"' in js
    assert '"swipe-right"' in js
    # The dispatch uses `dx < 0` to pick left vs right; pin the
    # ternary shape so a refactor can't silently flip directions.
    assert 'dx < 0 ? "swipe-left" : "swipe-right"' in js


def test_event_carries_dx_dy_duration_detail(js: str) -> None:
    """Handlers may want velocity / direction info — `detail` must
    carry dx, dy, durationMs so adopters can do velocity-aware
    decisions (e.g. snap-back vs commit threshold)."""
    assert "dx: dx" in js
    assert "dy: dy" in js
    assert "durationMs: dt" in js


def test_horizontal_threshold_constant(js: str) -> None:
    """Pin the 60px horizontal threshold — sub-threshold motion is
    a tap or a small adjustment, not a swipe."""
    assert "threshold = 60" in js


def test_max_vertical_drift_filter(js: str) -> None:
    """Vertical motion > 40px means the user is scrolling, not
    swiping. Skipping this check would make every list-scroll
    trigger spurious swipe events."""
    assert "maxVertical = 40" in js
    assert "Math.abs(dy) > maxVertical" in js


def test_max_duration_filter(js: str) -> None:
    """Slow drag (>500ms) is a long-press / drag-to-reorder, not a
    swipe. The duration cap keeps the gesture vocabulary clean."""
    assert "maxDurationMs = 500" in js
    assert "dt > maxDurationMs" in js


def test_single_finger_only(js: str) -> None:
    """Multi-touch pinch / two-finger swipe is the browser's
    navigation gesture — directive must skip when more than one
    finger is on the screen."""
    assert "e.touches.length !== 1" in js


def test_passive_listeners(js: str) -> None:
    """Touch listeners must be `passive: true` so the browser doesn't
    block native scroll on JS execution."""
    assert "{ passive: true }" in js


def test_handles_touchcancel(js: str) -> None:
    """A touchcancel (e.g. system gesture interruption) must reset
    `active` so a stale state doesn't leak into the next gesture."""
    assert "touchcancel" in js


def test_event_bubbles(js: str) -> None:
    """`bubbles: true` so a parent's listener can catch the swipe —
    useful for delegating from a list container instead of wiring
    every row."""
    # Both pull-to-refresh and swipe set bubbles:true; verify swipe
    # specifically by looking near the swipe-left/right dispatch.
    swipe_idx = js.find('"swipe-left"')
    bubbles_idx = js.find("bubbles: true", swipe_idx)
    assert bubbles_idx > swipe_idx, "swipe dispatch should set bubbles:true"


def test_directive_listed_in_module_header(js: str) -> None:
    """Public-API list at the top of dz-alpine.js — new directive
    needs the entry."""
    assert "x-swipe" in js


def test_directive_present_in_dist_bundle() -> None:
    """css_loader / build_dist must bundle the new directive into
    dazzle.min.js."""
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist/dazzle.min.js not built — run scripts/build_dist.py")
    text = dist_js.read_text()
    assert "swipe-left" in text
    assert "swipe-right" in text
