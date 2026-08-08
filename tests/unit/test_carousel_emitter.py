"""display: carousel hyperpart emitter — unit pins (cycle 1764)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import Carousel, CarouselSlide, FragmentRenderer
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin
from dazzle.render.fragment.region._context import RegionContext

ROOT = Path(__file__).resolve().parents[2]
SIMPLE = ROOT / "examples" / "simple_task"
DESIGN = ROOT / "examples" / "design_studio"


def test_carousel_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Carousel(
            slides=(
                CarouselSlide(
                    src="https://placehold.co/640x360/png?text=A",
                    alt="Slide A",
                    chip="16/9",
                ),
                CarouselSlide(
                    src="https://placehold.co/640x360/png?text=B",
                    alt="Slide B",
                ),
            ),
            label="Demo gallery",
            wrap="none",
        )
    )
    assert 'class="dz-carousel"' in html
    assert "data-dz-carousel" in html
    assert 'data-dz-carousel-index="0"' in html
    assert 'data-dz-carousel-wrap="none"' in html
    assert "data-dz-carousel-prev" in html
    assert "data-dz-carousel-next" in html
    assert "data-dz-carousel-status" in html
    assert 'class="dz-carousel__slide dz-carousel__slide--media"' in html
    assert "data-dz-active" in html
    assert 'class="dz-carousel__dot"' in html
    assert "Slide A" in html
    assert "Slide 1 of 2" in html
    assert 'data-dz-entry-count="2"' in html


def test_carousel_empty_state() -> None:
    html = FragmentRenderer().render(Carousel(slides=(), empty_message="Nothing here"))
    assert "Nothing here" in html
    assert 'data-dz-entry-count="0"' in html


def test_build_carousel_from_static_entries() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "sample_gallery", "title": "Sample", "empty_message": None})()
    ctx: RegionContext = {
        "status_entries": [
            {
                "title": "Wide",
                "body": "https://placehold.co/640x360/png?text=W",
                "icon": "16/9",
            },
            {"title": "Tall", "caption": "https://placehold.co/300x400/png?text=T"},
        ],
        "items": [],
        "empty_message": "none",
    }
    surface = _A()._build_carousel(region, ctx)
    html = FragmentRenderer().render(surface)
    assert 'class="dz-carousel"' in html
    assert "data-dz-carousel" in html
    assert "Wide" in html
    assert "Tall" in html
    assert html.count('class="dz-carousel__slide') == 2


def test_build_carousel_from_preview_url_items() -> None:
    class _A(_BuildersMetricsMixin):
        pass

    region = type("R", (), {"name": "asset_carousel", "title": "Assets", "empty_message": None})()
    ctx: RegionContext = {
        "items": [
            {
                "name": "Primary logo",
                "preview_url": "https://placehold.co/320x200/png?text=LOGO",
                "asset_type": "logo",
            },
            {
                "name": "Hero photo",
                "preview_url": "https://placehold.co/320x200/png?text=PHOTO",
                "asset_type": "photo",
            },
        ],
        "status_entries": [],
    }
    surface = _A()._build_carousel(region, ctx)
    html = FragmentRenderer().render(surface)
    assert "Primary logo" in html
    assert "Hero photo" in html
    assert "placehold.co" in html
    assert 'data-dz-entry-count="2"' in html


def test_simple_task_declares_sample_gallery_carousel() -> None:
    text = (SIMPLE / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "sample_gallery:" in text
    assert "display: carousel" in text
    assert "Priority board sketch" in text


def test_simple_task_appspec_sample_gallery_region() -> None:
    appspec = load_project_appspec(SIMPLE)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    admin = next((w for w in workspaces if getattr(w, "name", None) == "admin_dashboard"), None)
    assert admin is not None, (
        f"admin_dashboard missing; names={[getattr(w, 'name', None) for w in workspaces]}"
    )
    regions = list(getattr(admin, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("sample_gallery")
    assert region is not None, f"sample_gallery missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "carousel"
    entries = list(getattr(region, "status_entries", None) or [])
    assert len(entries) >= 2
    assert getattr(entries[0], "title", None)
    assert getattr(entries[0], "caption", None) or getattr(entries[0], "body", None)


def test_design_studio_declares_asset_carousel() -> None:
    text = (DESIGN / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "asset_carousel:" in text
    assert "display: carousel" in text


def test_design_studio_appspec_asset_carousel_region() -> None:
    appspec = load_project_appspec(DESIGN)
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    desk = next((w for w in workspaces if getattr(w, "name", None) == "brand_desk"), None)
    assert desk is not None
    regions = list(getattr(desk, "regions", None) or [])
    by_name = {getattr(r, "name", None): r for r in regions}
    region = by_name.get("asset_carousel")
    assert region is not None, f"asset_carousel missing; regions={list(by_name)}"
    display = getattr(region, "display", None)
    display_v = getattr(display, "value", display)
    assert display_v == "carousel"


def test_dsl_shapes_carousel_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "carousel" not in planned
    assert snap["live"] >= 70
