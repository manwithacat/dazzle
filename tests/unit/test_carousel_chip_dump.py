"""Carousel aspect chips must not dump schema tokens (oral #184)."""

from __future__ import annotations

from dazzle.render.filters import clerk_carousel_chip_label
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin
from dazzle.render.fragment.region._context import RegionContext


class _A(_BuildersMetricsMixin):
    pass


def _render_items(items: list[dict[str, object]]) -> str:
    region = type("R", (), {"name": "asset_carousel", "title": "Assets", "empty_message": None})()
    ctx: RegionContext = {"items": items, "status_entries": []}
    return FragmentRenderer().render(_A()._build_carousel(region, ctx))


def test_clerk_carousel_chip_leftover_and_empty() -> None:
    assert clerk_carousel_chip_label("icon_glyph") == "Icon Glyph"
    assert clerk_carousel_chip_label("logo") == "Logo"
    assert clerk_carousel_chip_label("16/9") == "16/9"
    assert clerk_carousel_chip_label("zzz") == "zzz"
    assert clerk_carousel_chip_label("ghost") == "ghost"
    assert clerk_carousel_chip_label("") == ""
    assert clerk_carousel_chip_label(None) == ""


def test_carousel_chip_is_clerk_not_schema_token() -> None:
    html = _render_items(
        [
            {
                "name": "App icon 1024",
                "preview_url": "https://placehold.co/320x200/png?text=ICON",
                "asset_type": "icon_glyph",
            },
            {
                "name": "Wordmark",
                "preview_url": "https://placehold.co/320x200/png?text=LOGO",
                "asset_type": "logo",
            },
        ]
    )
    assert "dz-carousel__chip" in html
    assert "Icon Glyph" in html
    assert "Logo" in html
    assert "icon_glyph" not in html
    leftover = _render_items(
        [
            {
                "name": "Leftover token stays put",
                "preview_url": "https://placehold.co/320x200/png?text=Z",
                "asset_type": "zzz",
            },
            {
                "name": "Unknown token stays put",
                "preview_url": "https://placehold.co/320x200/png?text=G",
                "asset_type": "ghost",
            },
        ]
    )
    assert ">zzz<" in leftover
    assert ">ghost<" in leftover
    assert ">Zzz<" not in leftover
    assert ">Ghost<" not in leftover


def test_empty_invents_no_carousel_chip() -> None:
    html = _render_items(
        [
            {
                "name": "Untyped slide",
                "preview_url": "https://placehold.co/320x200/png?text=NONE",
            }
        ]
    )
    assert "Untyped slide" in html
    assert "dz-carousel__chip" not in html
