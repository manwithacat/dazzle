"""Tests for #958 cycle 3 — x-swipe Alpine directive.

Mirrors the test approach for x-pull-to-refresh: pin the
registration path, the touch-only gating, the threshold + dispatch
contract, and the heuristics that distinguish a swipe from a
scroll / drag / tap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DZ_ALPINE_JS = (
    Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/js/dz-alpine.js"
)


@pytest.fixture(scope="module")
def js() -> str:
    assert DZ_ALPINE_JS.is_file(), f"dz-alpine.js not found at {DZ_ALPINE_JS}"
    return DZ_ALPINE_JS.read_text()


@pytest.mark.parametrize(
    "needle",
    [
        # Alpine.directive('swipe', ...) must be present so x-swipe resolves to the handler.
        'Alpine.directive("swipe"',
        # Desktop mouse drag is ambiguous — no-op on mouse-primary inputs.
        "(pointer: coarse)",
        # Dispatch contract: swipe-left / swipe-right CustomEvents.
        '"swipe-left"',
        '"swipe-right"',
        # Ternary shape pins direction logic so a refactor can't silently flip directions.
        'dx < 0 ? "swipe-left" : "swipe-right"',
        # detail carries dx, dy, durationMs for velocity-aware handlers.
        "dx: dx",
        "dy: dy",
        "durationMs: dt",
        # 60px horizontal threshold — sub-threshold motion is a tap, not a swipe.
        "threshold = 60",
        # Vertical motion > 40px means scrolling, not swiping.
        "maxVertical = 40",
        "Math.abs(dy) > maxVertical",
        # Slow drag (>500ms) is a long-press / drag-to-reorder, not a swipe.
        "maxDurationMs = 500",
        "dt > maxDurationMs",
        # Multi-touch: skip when more than one finger is on screen.
        "e.touches.length !== 1",
        # Touch listeners must be passive: true so the browser doesn't block native scroll.
        "{ passive: true }",
        # touchcancel must reset active so stale state doesn't leak into the next gesture.
        "touchcancel",
        # Public-API list at the top of dz-alpine.js.
        "x-swipe",
    ],
    ids=[
        "test_directive_registered",
        "test_touch_only_via_pointer_coarse",
        "test_dispatches_swipe_left_event",
        "test_dispatches_swipe_right_event",
        "test_dispatches_swipe_direction_ternary",
        "test_event_carries_dx_detail",
        "test_event_carries_dy_detail",
        "test_event_carries_duration_detail",
        "test_horizontal_threshold_constant",
        "test_max_vertical_drift_filter_constant",
        "test_max_vertical_drift_filter_check",
        "test_max_duration_filter_constant",
        "test_max_duration_filter_check",
        "test_single_finger_only",
        "test_passive_listeners",
        "test_handles_touchcancel",
        "test_directive_listed_in_module_header",
    ],
)
def test_js_contains(js: str, needle: str) -> None:
    assert needle in js


def test_event_bubbles(js: str) -> None:
    """`bubbles: true` so a parent's listener can catch the swipe —
    useful for delegating from a list container instead of wiring
    every row."""
    # Both pull-to-refresh and swipe set bubbles:true; verify swipe
    # specifically by looking near the swipe-left/right dispatch.
    swipe_idx = js.find('"swipe-left"')
    bubbles_idx = js.find("bubbles: true", swipe_idx)
    assert bubbles_idx > swipe_idx, "swipe dispatch should set bubbles:true"


def test_directive_present_in_dist_bundle() -> None:
    """css_loader / build_dist must bundle the new directive into
    dazzle.min.js."""
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist/dazzle.min.js not built — run scripts/build_dist.py")
    text = dist_js.read_text()
    assert "swipe-left" in text
    assert "swipe-right" in text
