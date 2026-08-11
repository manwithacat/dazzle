"""Post-5.8 Goal B media — design_studio Asset Catalog + Brand Desk pixels first."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
ASSET_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Asset.jsonl"
BRAND_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/Brand.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    needle = f'workspace {name} "'
    start = text.index(needle)
    rest = text[start + 1 :]
    next_ws = rest.find("\nworkspace ")
    return text[start : start + 1 + next_ws] if next_ws >= 0 else text[start:]


def test_asset_catalog_media_grid_before_brand_palette() -> None:
    """Peer DAM tools put creative thumbs above brand meta walls."""
    block = _workspace_block("asset_catalog")
    assert "media_grid:" in block
    assert "display: grid" in block
    assert "brand_palette:" in block
    assert block.index("media_grid:") < block.index("brand_palette:")
    assert "focus: media_grid, brand_palette, review_queue" in block
    # Cap palette so it cannot re-eat the fold after reorder
    assert "limit: 4" in block
    # brand_swatch_wall: empty copy names palette swatches for buyers
    assert "swatch" in block.lower() or "palette" in block.lower()


def test_brand_desk_declares_asset_media_shelf() -> None:
    block = _workspace_block("brand_desk")
    assert "asset_media:" in block
    assert "display: grid" in block
    assert "brand_media:" in block
    # Pixels first: asset media grid before palette swatch wall
    assert block.index("asset_media:") < block.index("brand_media:")
    assert block.index("brand_media:") < block.index("campaign_queue:")
    # Carousel after fold pair so swatches stay buyer-visible
    if "asset_carousel:" in block:
        assert block.index("brand_media:") < block.index("asset_carousel:")
    assert "focus: asset_media, brand_media, campaign_queue" in block
    # brand_swatch_wall: title / empty name palette swatches for still OCR
    assert 'title: "Palette Swatches"' in block or "palette swatch" in block.lower()
    assert "limit: 2" in block  # asset_media fold cap


def test_brand_entity_fitness_includes_palette_swatches() -> None:
    """Peer brand identity rows expose logo + Primary/Secondary/Accent for queues."""
    text = APP.read_text()
    start = text.index('entity Brand "Brand":')
    end = text.index('entity Asset "Design Asset":', start)
    block = text[start:end]
    assert "primary_color: str(7)" in block
    assert "secondary_color: str(7)" in block
    assert "accent_color: str(7)" in block
    assert "repr_fields: [name, logo_url, primary_color, secondary_color, accent_color]" in block


def test_brand_list_and_hub_expose_full_palette_swatches() -> None:
    """List + hub surfaces pin Primary/Secondary/Accent color widgets (still OCR)."""
    text = APP.read_text()
    list_start = text.index('surface brand_list "Brands":')
    list_end = text.index('surface brand_create "New Brand":', list_start)
    list_block = text[list_start:list_end]
    assert 'field primary_color "Primary" widget=color' in list_block
    assert 'field secondary_color "Secondary" widget=color' in list_block
    assert 'field accent_color "Accent" widget=color' in list_block
    assert "palette swatches" in list_block.lower()

    detail_start = text.index('surface brand_detail "Brand Detail":')
    detail_end = text.index('related assets "Assets":', detail_start)
    detail_block = text[detail_start:detail_end]
    assert 'section palette "Palette":' in detail_block
    assert 'field primary_color "Primary" widget=color' in detail_block
    assert 'field secondary_color "Secondary" widget=color' in detail_block
    assert 'field accent_color "Accent" widget=color' in detail_block

    # Creator hub related brands show full swatch columns (related supports multi-col)
    assert "columns: name, logo_url, primary_color, secondary_color, accent_color" in text


def test_brand_seeds_carry_hex_palette_tokens() -> None:
    rows = [json.loads(line) for line in BRAND_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 4
    for row in rows:
        for key in ("primary_color", "secondary_color", "accent_color"):
            val = str(row.get(key) or "")
            assert val.startswith("#") and len(val) == 7, (row.get("name"), key, val)


def test_brand_entity_fallback_columns_keep_palette_swatches() -> None:
    """Entity-fallback economy must keep logo + color types for brand_desk queues."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.runtime.workspace_columns import build_entity_columns

    spec = load_project_appspec(ROOT / "examples" / "design_studio")
    brand = spec.get_entity("Brand")
    assert brand is not None
    cols = build_entity_columns(brand)
    keys = [c["key"] for c in cols]
    types = {c["key"]: c["type"] for c in cols}
    assert "name" in keys
    assert "logo_url" in keys
    assert types.get("logo_url") == "image"
    for color_key in ("primary_color", "secondary_color", "accent_color"):
        assert color_key in keys, keys
        assert types[color_key] == "color", types


def test_asset_seeds_carry_https_preview_thumbs() -> None:
    rows = [json.loads(line) for line in ASSET_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    previews = [str(r.get("preview_url") or "") for r in rows]
    https = [p for p in previews if p.startswith("https://placehold.co/")]
    assert len(https) >= 8, "Goal B media expects placehold preview thumbs on assets"


def test_brand_seeds_carry_logo_urls() -> None:
    rows = [json.loads(line) for line in BRAND_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 4
    for row in rows:
        logo = str(row.get("logo_url") or "")
        assert logo.startswith("https://placehold.co/"), row.get("name")


def test_asset_entity_declares_version_and_approval_stamp() -> None:
    """Peer DAM tools (Figma / Frame.io / Bynder) put revision + approval on creatives."""
    text = APP.read_text()
    start = text.index('entity Asset "Design Asset":')
    end = text.index('entity Campaign "Campaign":', start)
    block = text[start:end]
    assert "version: int=1" in block
    assert "approved_at: datetime optional" in block
    assert "repr_fields: [name, version, status, asset_type, brand]" in block


def test_asset_surfaces_expose_version_and_approval_stamp() -> None:
    text = APP.read_text()
    list_start = text.index('surface asset_list "Assets":')
    list_end = text.index('surface asset_create "New Asset":', list_start)
    list_block = text[list_start:list_end]
    assert 'field version "Version"' in list_block
    assert 'field approved_at "Approved"' in list_block

    detail_start = text.index('surface asset_detail "Asset Detail":')
    detail_end = text.index('surface asset_edit "Edit Asset":', detail_start)
    detail_block = text[detail_start:detail_end]
    assert 'field version "Version"' in detail_block
    assert 'field approved_at "Approved At"' in detail_block
    # Production strip carries revision before status theater
    prod = detail_block.split('section production "Production":', 1)[1][:400]
    assert prod.index("version") < prod.index("status")


def test_brand_and_campaign_hubs_surface_version_on_assets() -> None:
    text = APP.read_text()
    brand = text[
        text.index('surface brand_detail "Brand Detail":') : text.index(
            'surface brand_edit "Edit Brand":'
        )
        if 'surface brand_edit "Edit Brand":' in text
        else text.index('surface asset_list "Assets":')
    ]
    # brand hub assets related group
    assert "columns: name, version, status, asset_type, quality_score" in brand
    assert "columns: preview_url, name, version, status, asset_type" in text


def test_asset_seeds_carry_version_mix_and_approval_stamps() -> None:
    rows = [json.loads(line) for line in ASSET_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    versions = {int(r.get("version") or 0) for r in rows}
    assert max(versions) >= 3, "Goal B media expects multi-revision seed mix"
    assert 1 in versions
    stamped = [r for r in rows if r.get("approved_at")]
    assert len(stamped) >= 3
    for r in stamped:
        assert r.get("status") in ("approved", "published"), r.get("name")
    # Still-visible revision markers on preview thumbs
    with_v = [r for r in rows if f"v{r.get('version')}" in str(r.get("preview_url") or "").lower()]
    assert len(with_v) >= 6, "preview thumbs should OCR-mark revision for still proof"
