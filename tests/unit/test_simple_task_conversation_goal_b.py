"""Post-5.8 Goal B conversation — simple_task comments on admin/team desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/simple_task/dsl/seeds/demo_data/TaskComment.jsonl"


def test_task_comment_display_field_is_content() -> None:
    text = APP.read_text()
    assert "entity TaskComment" in text
    assert "display_field: content" in text
    assert "content: text required" in text


def test_hero_desks_declare_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace admin_dashboard" in text
    assert "workspace team_overview" in text
    assert "workspace my_work" in text
    assert "live_conversation:" in text
    assert "source: TaskComment" in text
    assert "conversation: count(TaskComment)" in text
    assert "focus: live_conversation" in text


def test_task_comment_seeds_have_domain_true_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("content") or "")
        assert len(body) >= 24, body
        assert " " in body
