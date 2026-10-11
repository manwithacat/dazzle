"""Carousel empty must not dump generic 'No slides.' (oral #229)."""

from __future__ import annotations

from dazzle.render.breadcrumbs import (
    clerk_empty_carousel_title,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_metrics import _BuildersMetricsMixin


class _A(_BuildersMetricsMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "asset_carousel",
        "title": "Asset carousel",
        "empty_message": None,
        "source": "Asset",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_carousel(region: object, ctx: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {"items": [], "status_entries": []}
    payload.update(ctx or {})
    return FragmentRenderer().render(_A()._build_carousel(region, payload))


def test_clerk_empty_carousel_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_carousel_title(junk) == "No slides."


def test_carousel_empty_is_assets_not_no_slides() -> None:
    html = _render_carousel(_region())
    assert "dz-empty-dense" in html
    assert "No assets in this gallery." in html
    assert "No slides." not in html
    assert "No assetss" not in html


def test_carousel_empty_ctx_source_entity_still_splits() -> None:
    html = _render_carousel(_region(source=""), {"source_entity": "Asset"})
    assert "No assets in this gallery." in html
    assert "No slides." not in html


def test_carousel_empty_missing_entity_stays_no_slides() -> None:
    html = _render_carousel(_region(source=""))
    assert "No slides." in html
    assert "No assets" not in html


def test_carousel_empty_leftover_invents_no_collection() -> None:
    html = _render_carousel(_region(source="zzz"))
    assert "No slides." in html
    assert "No zzz" not in html


def test_carousel_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_carousel(_region(source="Asset"), {"entity_name": "Item"})
    assert "No assets in this gallery." in html
    assert "No slides." not in html


def test_carousel_authored_empty_still_wins() -> None:
    html = _render_carousel(_region(empty_message="No media slides yet"))
    assert "No media slides yet" in html
    assert "No slides." not in html
    assert "No assets in this gallery." not in html


def test_carousel_populated_still_renders_slides() -> None:
    html = _render_carousel(
        _region(),
        {
            "items": [
                {
                    "id": "a1",
                    "name": "Wordmark",
                    "preview_url": "https://placehold.co/640x360/png?text=Wordmark",
                }
            ],
        },
    )
    assert "Wordmark" in html
    assert "No slides." not in html
    assert "No assets in this gallery." not in html
