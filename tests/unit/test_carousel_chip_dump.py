"""Carousel aspect chips must not dump schema tokens (oral #184)."""

from __future__ import annotations

from pathlib import Path

from dazzle.render.filters import clerk_carousel_chip_label
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin
from dazzle.render.fragment.region._context import RegionContext

DESIGN = Path("examples/design_studio/dsl")


class _A(_BuildersMetricsMixin):
    pass


def _render_items(items: list[dict[str, object]]) -> str:
    region = type("R", (), {"name": "asset_carousel", "title": "Assets", "empty_message": None})()
    ctx: RegionContext = {"items": items, "status_entries": []}
    return FragmentRenderer().render(_A()._build_carousel(region, ctx))


def test_design_studio_asset_carousel_is_live() -> None:
    block = (DESIGN / "app.dsl").read_text()
    asset = block.split('entity Asset "Design Asset":', 1)[1].split("entity ", 1)[0]
    assert "asset_type: enum[logo,icon_glyph,illustration,photo,pattern,typography]=logo" in asset
    region = block.split("  asset_carousel:", 1)[1].split("  campaign_queue:", 1)[0]
    assert "display: carousel" in region
    assert "source: Asset" in region
    seeds = (DESIGN / "seeds/demo_data/Asset.jsonl").read_text()
    assert '"asset_type":"icon_glyph"' in seeds
    catalog = block.split('surface asset_list "Assets":', 1)[1].split("surface ", 1)[0]
    assert 'field asset_type "Type"' in catalog


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
