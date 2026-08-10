"""Post-5.8 Goal B media — simple_task teammate headshot shelf (cycle 1884)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/simple_task/dsl/seeds/demo_data/User.jsonl"


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


def test_admin_dashboard_media_shelf_first() -> None:
    """Goal B media: teammate headshots win the Admin Dashboard fold before metrics."""
    block = _workspace_block("admin_dashboard")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: is_active = true and photo_url != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("metrics:")
    assert block.index("media_shelf:") < block.index("urgent_tasks:")
    assert (
        "focus: media_shelf, metrics, urgent_tasks, overdue_tasks, "
        "composition, live_conversation" in block
    )


def test_team_overview_media_shelf_first() -> None:
    """Goal B media: headshot grid declared before metrics/queues on Team Overview."""
    block = _workspace_block("team_overview")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: is_active = true and photo_url != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("metrics:")
    assert block.index("media_shelf:") < block.index("needs_review:")
    assert (
        "focus: media_shelf, metrics, needs_review, plate_by_person, "
        "composition, live_conversation, team_roster" in block
    )


def test_user_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 8, "Goal B media expects headshots across the task team"
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url
