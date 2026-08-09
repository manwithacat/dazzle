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
    # Order: media shelf → metrics → dual attention → conversation.
    assert block.index("media_shelf:") < block.index("portfolio:")
    assert block.index("portfolio:") < block.index("live_conversation:")
    assert block.index("media_shelf:") < block.index("live_conversation:")
    assert block.index("media_shelf:") < block.index("review_pressure:")
    assert block.index("media_shelf:") < block.index("draft_pressure:")


def test_studio_dashboard_media_home_purpose_and_focus() -> None:
    block = _studio_dashboard_block()
    # Media shelf still wins the fold; dual attention sits after metrics (cycle 1836).
    assert "media home" in block.lower() or "Multi-panel" in block or "multi-panel" in block.lower()
    assert (
        "focus: media_shelf, portfolio, review_pressure, draft_pressure, live_conversation" in block
    )
    assert "limit: 2" in block or "limit: 3" in block
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
