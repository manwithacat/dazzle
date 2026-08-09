"""Post-5.8 Goal B media — design_studio Studio Dashboard media home."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"


def _studio_dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace studio_dashboard "Studio Dashboard":')
    end = text.index('workspace asset_catalog "Asset Catalog":', start)
    return text[start:end]


def test_studio_dashboard_media_shelf_wins_fold() -> None:
    """Peer creative homes put pixel previews above metrics / critique meta."""
    block = _studio_dashboard_block()
    assert "media_shelf:" in block
    assert "display: grid" in block
    assert "portfolio:" in block
    assert "live_conversation:" in block
    # Order: media shelf → metrics → conversation (media home, not reply desk first).
    assert block.index("media_shelf:") < block.index("portfolio:")
    assert block.index("portfolio:") < block.index("live_conversation:")
    assert block.index("media_shelf:") < block.index("live_conversation:")


def test_studio_dashboard_media_home_purpose_and_focus() -> None:
    block = _studio_dashboard_block()
    assert "media home" in block.lower() or "Media home" in block
    assert "focus: media_shelf, portfolio, live_conversation, review_pressure" in block
    assert "limit: 8" in block
    # Fold share: drop redundant timeline/chart wall on the home desk.
    assert "recent_assets:" not in block
    assert "asset_trail:" not in block
    assert "asset_status_mix:" not in block


def test_studio_dashboard_media_shelf_opens_asset_detail() -> None:
    block = _studio_dashboard_block()
    shelf = block.split("media_shelf:", 1)[1][:350]
    assert "source: Asset" in shelf
    assert "action: asset_detail" in shelf
    assert "display: grid" in shelf
