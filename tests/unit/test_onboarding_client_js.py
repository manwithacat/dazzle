"""Tests for the client-side onboarding JS (v0.71.6).

Two layers:

1. Content gate on ``dz-onboarding.js`` — pins the invariants the
   page-routes wiring depends on (the script handles auto-dismiss for
   nudge, focus for blocking_task, htmx swap re-arming, optional
   anchored positioning).
2. Chrome wiring — when an AppSpec declares guides, ``resolve_app_chrome``
   adds ``/static/js/dz-onboarding.js`` to the JS bundle list. Apps
   without guides don't pay the cost.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.ui.runtime.app_chrome import resolve_app_chrome

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_PATH = REPO_ROOT / "src/dazzle/ui/runtime/static/js/dz-onboarding.js"


# ---------------------------------------------------------------------------
# JS content gate
# ---------------------------------------------------------------------------


def test_js_file_exists() -> None:
    assert JS_PATH.is_file(), f"missing client JS at {JS_PATH}"


def test_js_handles_all_lifecycle_events() -> None:
    """The script must run on initial load AND on htmx:after:swap so
    fragment-injected overlays get wired."""
    text = JS_PATH.read_text()
    assert 'addEventListener("DOMContentLoaded"' in text or "DOMContentLoaded" in text
    assert "htmx:after:swap" in text


def test_js_arms_nudge_autodismiss_with_correct_url_shape() -> None:
    """nudge dismissal posts to ``/api/onboarding/<guide>/<step>/dismiss``."""
    text = JS_PATH.read_text()
    # URL is built from the data attributes; assert the path-segment
    # shape is intact.
    assert '"/api/onboarding/"' in text
    assert "/dismiss" in text
    # Reads the timer from data-autodismiss-ms.
    assert 'getAttribute("data-autodismiss-ms")' in text


def test_js_focus_management_for_blocking_task() -> None:
    text = JS_PATH.read_text()
    assert "blocking_task" in text
    # First-tabbable selector covers a/button/input/[tabindex]
    assert "a[href]" in text
    assert "button:not([disabled])" in text
    assert "[tabindex]" in text


def test_js_positions_against_data_onboarding_anchor() -> None:
    """Positioning is opt-in via a ``data-onboarding-anchor`` attribute
    on the page element the overlay should attach to."""
    text = JS_PATH.read_text()
    assert "data-onboarding-anchor" in text
    # Handles all five placement values.
    for placement in ["top", "bottom", "left", "right", "center"]:
        assert f'"{placement}"' in text


def test_js_wired_guard_prevents_double_arm() -> None:
    """``htmx:after:swap`` calls initAll; the script must not re-arm
    elements it's already wired (auto-dismiss timer would fire twice)."""
    text = JS_PATH.read_text()
    assert "data-dz-wired" in text


def test_js_uses_credentials_same_origin() -> None:
    """The auto-dismiss fetch needs the auth cookie — same-origin
    credentials are required for the route's 401 guard to pass."""
    text = JS_PATH.read_text()
    assert '"same-origin"' in text


def test_js_has_css_escape_fallback() -> None:
    """CSS.escape isn't on every browser surface; the script must
    degrade gracefully for the anchor-selector lookup."""
    text = JS_PATH.read_text()
    assert "CSS.escape" in text
    # And a fallback path that escapes quotes/backslashes.
    assert "cssEscape" in text


# ---------------------------------------------------------------------------
# Chrome wiring
# ---------------------------------------------------------------------------


def _appspec(*, guides=None):
    """Minimal AppSpec stand-in — resolve_app_chrome only reads a few fields."""
    return SimpleNamespace(
        app_config=None,
        feedback_widget=None,
        guides=guides or [],
    )


def test_chrome_omits_onboarding_js_when_no_guides() -> None:
    chrome = resolve_app_chrome(_appspec(guides=[]))
    assert "/static/js/dz-onboarding.js" not in chrome.js_scripts


def test_chrome_mounts_onboarding_js_when_guides_declared() -> None:
    chrome = resolve_app_chrome(_appspec(guides=[SimpleNamespace(name="g1")]))
    assert "/static/js/dz-onboarding.js" in chrome.js_scripts


def test_chrome_mounts_onboarding_js_after_framework_bundle() -> None:
    """Order matters — the framework bundle must load first so htmx is
    defined by the time dz-onboarding registers its afterSwap listener."""
    chrome = resolve_app_chrome(_appspec(guides=[SimpleNamespace(name="g1")]))
    scripts = list(chrome.js_scripts)
    framework_idx = next((i for i, s in enumerate(scripts) if s.endswith("dazzle.min.js")), -1)
    onboarding_idx = scripts.index("/static/js/dz-onboarding.js")
    assert framework_idx >= 0, "framework bundle missing from js_scripts"
    assert framework_idx < onboarding_idx, (
        "dz-onboarding.js must load AFTER the framework bundle "
        "(htmx needs to be defined first); got "
        f"framework={framework_idx} onboarding={onboarding_idx}"
    )
