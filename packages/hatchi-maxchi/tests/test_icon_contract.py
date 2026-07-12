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
        # Lucide stroke defaults — required on the referencing element so
        # sprite `<use>` shadow content inherits them (not from the sheet).
        "stroke-width: 2",
        "stroke-linecap: round",
        "stroke-linejoin: round",
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


# ── build-time fail-loud on an unknown icon token ─────────────────────────


def test_unknown_icon_token_fails_loud() -> None:
    from build_site import expand_icons

    with pytest.raises((KeyError, ValueError)) as exc:
        expand_icons("<i>{svg:definitely-not-an-icon}</i>")
    assert "definitely-not-an-icon" in str(exc.value)


def test_known_icon_token_still_expands() -> None:
    from build_site import expand_icons

    assert "<svg" in expand_icons("<i>{svg:check}</i>")


# ── mock-htmx {i:} map: complete + fail-loud (drawer Work Orders regression) ─


def test_mock_htmx_i_tokens_are_known_icons() -> None:
    """Every {i:name} in MOCK_HTMX must resolve in ICONS (build fails otherwise)."""
    from build_site import mock_htmx_icon_names

    names = mock_htmx_icon_names()
    assert names, "MOCK_HTMX should use at least one {i:} icon"
    # Drawer open-record body — the regression that shipped empty spans
    for required in ("clipboard-list", "circle-check", "map-pin", "triangle-alert"):
        assert required in names, f"drawer mock expects {{i:{required}}}"


def test_unknown_mock_i_token_fails_loud() -> None:
    from build_site import mock_htmx_icon_names

    with pytest.raises(ValueError) as exc:
        mock_htmx_icon_names("{i:definitely-not-an-icon}")
    assert "definitely-not-an-icon" in str(exc.value)


def test_mock_icon_map_js_includes_every_i_token() -> None:
    from build_site import build_mock_icon_map_js, mock_htmx_icon_names

    names = mock_htmx_icon_names()
    js = build_mock_icon_map_js(names)
    assert js.startswith("window.__HM_ICONS__")
    for name in names:
        assert f"'{name}':" in js, f"__HM_ICONS__ missing {name}"
        assert "<svg" in js


def test_committed_gallery_js_carries_full_mock_icon_map() -> None:
    """Committed hatchi-maxchi.js must not lag the MOCK_HTMX token set."""
    from build_site import mock_htmx_icon_names

    names = mock_htmx_icon_names()
    js = (PKG / "site" / "hatchi-maxchi.js").read_text(encoding="utf-8")
    assert "window.__HM_ICONS__" in js
    for name in names:
        assert f"'{name}':" in js, (
            f"site/hatchi-maxchi.js missing mock icon {name!r} — "
            "re-run python site/build_site.py and commit"
        )


# ── sprite: one symbol sheet + short <use> references ─────────────────────


def test_sheet_has_a_symbol_per_icon() -> None:
    from icons import ICONS
    from icons.sprite import build_symbol_sheet

    sheet = build_symbol_sheet(ICONS)
    assert sheet.startswith("<svg") and "display:none" in sheet
    for name in ("check", "circle-check", "chevron-down"):
        assert f'<symbol id="i-{name}" viewBox="0 0 24 24">' in sheet


def test_sprite_use_is_short_and_decorative() -> None:
    from icons.sprite import sprite_use_html

    assert (
        sprite_use_html("circle-check")
        == '<svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg>'
    )


def test_committed_sprite_sheet_is_current() -> None:
    from icons import ICONS
    from icons.sprite import build_symbol_sheet

    committed = (PKG / "icons" / "sprite_sheet.svg").read_text(encoding="utf-8")
    assert committed == build_symbol_sheet(ICONS), (
        "sprite_sheet.svg is stale — run icons/gen_registry.py --sync"
    )


# ── gallery pedagogy: sprite snippets + one injected sheet ────────────────


def _gallery_html() -> str:
    return (PKG / "site" / "index.html").read_text(encoding="utf-8")


def test_gallery_injects_one_symbol_sheet() -> None:
    html = _gallery_html()
    assert 'style="display:none"' in html, "symbol sheet not injected into the gallery"
    assert '<symbol id="i-circle-check"' in html


def test_gallery_component_snippets_use_sprite_reference() -> None:
    html = _gallery_html()
    assert '<use href="#i-' in html, "gallery icons are not the sprite <use> form"
    assert html.count('<use href="#i-') >= 5
