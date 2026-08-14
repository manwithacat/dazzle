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


def test_user_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1925 agency_lead: Team Overview cards must not dump Photo Url/Email/Is Active."""
    text = APP.read_text()
    start = text.index('entity User "Team Member"')
    # Entity fitness block only (before Task entity).
    block = text[start : text.index('entity Task "Task"')]
    assert "repr_fields: [name, role, department]" in block
    # Raw admin schema must stay off card repr (still available on list/detail).
    assert "photo_url" not in block.split("repr_fields:")[1].split("\n")[0]
    assert "email" not in block.split("repr_fields:")[1].split("\n")[0]
    assert "is_active" not in block.split("repr_fields:")[1].split("\n")[0]


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
    assert "focus: media_shelf, metrics, open_blockers, open_questions" in block


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
    # Cycle 2058: conversation density focus (≤4); media shelf still first.
    assert "focus: media_shelf, metrics, open_blockers, open_questions" in block
    assert "composition:" in block
    assert "team_roster:" in block


def test_user_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 8, "Goal B media expects headshots across the task team"
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url
