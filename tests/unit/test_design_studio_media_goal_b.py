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


def test_brand_desk_declares_asset_media_shelf() -> None:
    block = _workspace_block("brand_desk")
    assert "asset_media:" in block
    assert "display: grid" in block
    assert "brand_media:" in block
    # Pixels first: asset media grid before logo monogram queue
    assert block.index("asset_media:") < block.index("brand_media:")
    assert block.index("brand_media:") < block.index("campaign_queue:")
    assert "focus: asset_media, brand_media, campaign_queue" in block


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
