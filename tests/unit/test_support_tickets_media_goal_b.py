"""Post-5.8 Goal B media — support_tickets agent headshot shelf (cycle 1883)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/User.jsonl"


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
    assert 'entity User "User"' in text
    assert "photo_url: url" in text


def test_ticket_queue_media_shelf_first() -> None:
    """Goal B media: agent headshots win the Ticket Queue fold before metrics."""
    block = _workspace_block("ticket_queue")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: is_active = true and department != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("queue_metrics:")
    assert block.index("media_shelf:") < block.index("live_conversation:")


def test_manager_ops_media_shelf_first() -> None:
    """Goal B media: headshot grid declared before metrics/queues on Manager Ops."""
    block = _workspace_block("manager_ops")
    assert "media_shelf:" in block
    assert "source: User" in block
    assert "display: grid" in block
    assert "filter: is_active = true and department != null" in block
    assert "sort: created_at desc" in block
    assert block.index("media_shelf:") < block.index("team_metrics:")
    assert block.index("media_shelf:") < block.index("critical_queue:")
    # Fold pin tracks product intent (cycle 2001: raised_needs_reply over
    # critical_needs_reply on the manager focus strip). media_shelf stays first.
    assert (
        "focus: media_shelf, team_metrics, breach_risk, critical_queue, "
        "unassigned_queue, needs_reply, frustrated_awaiting_customer, urgent_awaiting_customer, urgent_needs_reply, raised_needs_reply, live_conversation"
        in block
    )


def test_user_seeds_have_https_photo_urls() -> None:
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 6
    with_photo = [r for r in rows if r.get("photo_url")]
    assert len(with_photo) >= 6, "Goal B media expects headshots across the support team"
    for r in with_photo:
        url = str(r["photo_url"])
        assert url.startswith("https://"), url
        assert "placehold.co" in url


def test_user_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1933: agent media/people cards skip Photo Url/Email/Is Active."""
    text = APP.read_text()
    start = text.index('entity User "User"')
    block = text[start : text.index("entity Ticket")]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "name" in line and "role" in line and "department" in line
    assert "photo_url" not in line
    assert "email" not in line
    assert "is_active" not in line
