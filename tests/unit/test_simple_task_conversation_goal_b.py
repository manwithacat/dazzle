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
    # command_density@1835 keeps live_conversation on the focus spine (not first).
    assert "live_conversation" in text
    assert "focus:" in text and "live_conversation" in text
    # Goal B interesting_product: hero live threads use MessageScroller chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    for ws in ("admin_dashboard", "team_overview", "my_work"):
        block = text.split(f"workspace {ws}", 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: TaskComment" in region, ws
        # Focus spine still names the conversation region.
        ux = block.split("ux:", 1)[1][:800]
        assert "live_conversation" in ux, ws


def test_task_detail_discussion_uses_conversation_chrome() -> None:
    """Task hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface task_detail "Task Detail"' in text
    block = text.split('surface task_detail "Task Detail"', 1)[1]
    block = block.split("surface task_comments", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: TaskComment" in related
    assert "columns: content, author, created_at" in related
    assert "display: queue" not in related


def test_task_comment_seeds_have_domain_true_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("content") or "")
        assert len(body) >= 24, body
        assert " " in body
