"""Tests for #958 cycle 1 — mobile touch-target hit area enforcement.

The framework's interactive primitives (`.dz-button`, icon buttons,
close-X buttons) need to hit 44×44px on touch devices. Cycle 1
adds a `--dz-touch-target-min` token + a `pointer: coarse` media
query that enforces the floor without inflating desktop sizing.

These tests pin the token name + selector coverage so a future CSS
refactor can't silently drop the rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest

CSS_ROOT = Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/css"
HM = Path(__file__).resolve().parents[2] / "packages/hatchi-maxchi"
TOUCH_CSS = HM / "components/touch-targets.css"
TOKENS_CSS = HM / "tokens/tokens.css"


@pytest.fixture(scope="module")
def touch_css() -> str:
    assert TOUCH_CSS.is_file(), f"touch-targets.css not found at {TOUCH_CSS}"
    return TOUCH_CSS.read_text()


@pytest.fixture(scope="module")
def tokens_css() -> str:
    return TOKENS_CSS.read_text()


# ---------------------------------------------------------------------------
# Token presence
# ---------------------------------------------------------------------------


def test_token_and_media_query_invariants(tokens_css: str, touch_css: str) -> None:
    """Combined: token present, token >=44px, pointer:coarse media query, components layer."""
    # token name present
    assert "--dz-touch-target-min:" in tokens_css

    # token value at least 44px
    found_token = False
    for line in tokens_css.splitlines():
        if "--dz-touch-target-min:" in line:
            value = line.split(":", 1)[1].strip().rstrip(";").strip()
            assert value.endswith("px"), f"token value should be px, got {value!r}"
            assert int(value.removesuffix("px")) >= 44
            found_token = True
            break
    if not found_token:
        pytest.fail("token line not found")

    # media query gating
    assert "@media (pointer: coarse)" in touch_css

    # cascade layer
    assert "@layer components" in touch_css


# ---------------------------------------------------------------------------
# Selector coverage
# ---------------------------------------------------------------------------


CORE_SELECTORS = [
    # `.dz-button` covers every button; variants moved to data-dz-variant
    # on the same base element (no per-variant touch selector needed).
    ".dz-button",
    ".dz-icon-button",
    ".dz-card-action-button",
    ".dz-list-action-button",
    ".dz-sidebar-action-button",
    ".dz-add-card-button",
]

CLOSE_BUTTONS = [
    ".dz-modal-close-form",
    ".dz-modal-close-form-floating",
    ".dz-pdf-viewer-help-close",
    ".dz-pdf-viewer-panel-close",
    ".dz-slideover-close",
]


@pytest.mark.parametrize("selector", CORE_SELECTORS)
def test_core_button_selector_present(touch_css: str, selector: str) -> None:
    """Every core interactive primitive must be in the touch-target
    rule. Drift here = some buttons too small to tap reliably."""
    assert selector in touch_css


@pytest.mark.parametrize("selector", CLOSE_BUTTONS)
def test_close_button_selector_present(touch_css: str, selector: str) -> None:
    """Close-X buttons are usually icon-only and the most likely to
    underdeliver hit area on touch — explicit coverage required."""
    assert selector in touch_css


def test_native_button_fallback_present(touch_css: str) -> None:
    """A bare `<button>` (no Dazzle class) still gets the floor —
    customer code shouldn't have to remember to add classes for
    touch comfort."""
    assert "button,\n" in touch_css or "  button," in touch_css


# ---------------------------------------------------------------------------
# Bundle inclusion (#920 css_loader regression guard)
# ---------------------------------------------------------------------------


def test_present_in_dist_bundle() -> None:
    """The css_loader bundles every component file; verify the new
    touch-targets.css landed in the dist .min.css. If the loader
    misses it, mobile users silently get desktop hit areas."""
    dist_css = (
        Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/dist/dazzle.min.css"
    )
    if not dist_css.is_file():
        pytest.skip("dist/dazzle.min.css not built — run scripts/build_dist.py")
    text = dist_css.read_text()
    assert "--dz-touch-target-min" in text
    # The pointer:coarse query (or its compiled minification) must
    # appear; the value sometimes loses spaces in minification.
    assert "pointer:coarse" in text.replace(" ", "") or "pointer: coarse" in text
