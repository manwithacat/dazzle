"""Post-5.8 Goal B media — project_tracker portfolio headshot shelf (cycle 1884)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/project_tracker/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/project_tracker/dsl/seeds/demo_data/User.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_user_entity_declares_photo_url() -> None:
    text = APP.read_text()
    assert 'entity User "Team Member"' in text
    assert "photo_url: url" in text


def test_dashboard_media_shelf_first() -> None:
    """Goal B media: teammate headshots win the Dashboard fold before metrics."""
    block = _workspace_block("dashboard")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: is_active = true and department != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("portfolio_metrics:")
    assert block.index("media_shelf:") < block.index("open_task_queue:")
    assert (
        "focus: media_shelf, portfolio_metrics, open_task_queue, composition, "
        "live_conversation, project_overview, task_flow" in block
    )


def test_user_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 6
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 6
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url
