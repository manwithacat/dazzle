"""Icon-system contract gates (docs/superpowers/plans/2026-07-04-hm-icon-system-*).

Phase 1: the canonical `.dz-icon` base contract in the built CSS.
Later phases append: label a11y, sprite sheet, sprite-use helpers.
"""

import re
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "site"))

from build import build_css  # noqa: E402
from icons.html import lucide_icon_html, lucide_svg_html  # noqa: E402

pytestmark = pytest.mark.gate


def _css(prefix: str = "dz-") -> str:
    return build_css(prefix)


def test_dz_icon_base_declares_the_full_contract() -> None:
    css = _css("dz-")
    block = re.search(r"\.dz-icon\b[^{]*\{([^}]*)\}", css)
    assert block, ".dz-icon base rule missing"
    body = block.group(1)
    for decl in (
        "width: 1em",
        "height: 1em",
        "vertical-align: -0.125em",
        "flex-shrink: 0",
        "stroke: currentColor",
        "fill: none",
    ):
        assert decl in body, f".dz-icon base missing `{decl}`"


def test_dz_icon_size_scale_is_complete() -> None:
    css = _css("dz-")
    for size in ("xs", "sm", "md", "lg", "xl"):
        assert f".dz-icon--size-{size}" in css, f"missing .dz-icon--size-{size}"


def test_dz_icon_solid_variant_exists() -> None:
    assert ".dz-icon-solid" in _css("dz-")


def test_gallery_publishes_unprefixed_icon_contract() -> None:
    css = _css("")  # gallery default: dz- stripped
    assert ".icon--size-xl" in css and ".icon-solid" in css
    assert ".dz-icon" not in css  # fully stripped


# ── a11y: decorative by default, `label` makes an icon meaningful ──────────


def test_decorative_default_is_aria_hidden() -> None:
    out = lucide_svg_html("check", cls="dz-icon")
    assert 'aria-hidden="true"' in out and "role=" not in out


def test_svg_label_makes_icon_meaningful() -> None:
    out = lucide_svg_html("trash-2", cls="dz-icon", label="Delete")
    assert 'role="img"' in out and 'aria-label="Delete"' in out
    assert "aria-hidden" not in out


def test_icon_span_label_makes_icon_meaningful() -> None:
    out = lucide_icon_html("info", cls="dz-icon", label="Information")
    assert 'role="img"' in out and 'aria-label="Information"' in out
    assert "aria-hidden" not in out


def test_label_is_escaped() -> None:
    out = lucide_svg_html("check", cls="dz-icon", label='a"b')
    assert 'aria-label="a&quot;b"' in out
