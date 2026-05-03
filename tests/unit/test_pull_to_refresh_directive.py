"""Tests for #958 cycle 2 — x-pull-to-refresh Alpine directive.

Browser-level behaviour (touch event sequencing) isn't testable
without a browser harness, so these pin the registration path,
the touch-only gating, the threshold + dispatch contract, and the
prefers-reduced-motion guard.
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
    """Alpine.directive('pull-to-refresh', ...) call must be present
    so x-pull-to-refresh in templates resolves to the handler."""
    assert 'Alpine.directive("pull-to-refresh"' in js


def test_touch_only_via_pointer_coarse(js: str) -> None:
    """Desktop mouse drag would hijack scroll. The directive must
    no-op when `pointer: coarse` doesn't match — same gating as
    touch-targets.css."""
    assert "(pointer: coarse)" in js


def test_dispatches_refresh_custom_event(js: str) -> None:
    """The dispatch contract is `refresh` CustomEvent so adopters
    can wire `hx-trigger=\"refresh\"` and have htmx pick it up.
    `bubbles: true` so a parent's listener can also catch it."""
    assert 'CustomEvent("refresh"' in js
    assert "bubbles: true" in js


def test_threshold_constant_present(js: str) -> None:
    """80px threshold is documented + tunable. If a refactor drops
    the named threshold the snap-back / dispatch decision boundary
    becomes magic. Pin the value."""
    assert "threshold = 80" in js


def test_only_triggers_when_scrollTop_zero(js: str) -> None:
    """Pull-to-refresh must NOT engage mid-scroll — otherwise the
    user trying to scroll up gets a refresh instead. The directive
    only captures touchstart when the container is at the top."""
    assert "el.scrollTop > 0" in js


def test_reduced_motion_skips_transform_keeps_dispatch(js: str) -> None:
    """Users with prefers-reduced-motion still get the refresh
    behaviour, just without the visual pull animation. The dispatch
    must NOT be inside the `if (!reduce)` branch."""
    assert "prefers-reduced-motion: reduce" in js
    # Find the refresh dispatch position relative to the reduce check.
    # The CustomEvent dispatch comes BEFORE the `if (!reduce)` snap-back
    # block — it must always fire on threshold cross.
    dispatch_idx = js.find('CustomEvent("refresh"')
    snap_back_idx = js.find("if (!reduce)", dispatch_idx)
    assert snap_back_idx > dispatch_idx, (
        "refresh dispatch must precede the reduced-motion snap-back guard"
    )


def test_passive_listeners(js: str) -> None:
    """Touch listeners must be `passive: true` so the browser doesn't
    block native scroll on JS execution. Especially important for
    touchmove which fires often."""
    assert "{ passive: true }" in js


def test_handles_touchcancel_alongside_touchend(js: str) -> None:
    """A touchcancel (e.g. notification interrupting the gesture)
    must reset state the same way touchend does — otherwise a
    subsequent touchstart finds `pulling=true` from a stale gesture."""
    assert "touchcancel" in js


def test_directive_listed_in_module_header(js: str) -> None:
    """Public-API list at the top of dz-alpine.js. New directive
    needs the entry so future readers can find it."""
    assert "x-pull-to-refresh" in js


def test_directive_present_in_dist_bundle() -> None:
    """css_loader / build_dist must bundle the new directive into
    dazzle.min.js so customer apps that include the dist actually
    get it."""
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle_ui/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist/dazzle.min.js not built — run scripts/build_dist.py")
    text = dist_js.read_text()
    assert "pull-to-refresh" in text
