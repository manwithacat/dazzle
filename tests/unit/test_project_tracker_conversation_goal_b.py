"""Post-5.8 Goal B conversation — project_tracker discussion trail on work desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/project_tracker/dsl/app.dsl"
COMMENT_SEEDS = ROOT / "examples/project_tracker/dsl/seeds/demo_data/Comment.jsonl"


def test_comment_display_field_is_body() -> None:
    text = APP.read_text()
    assert "entity Comment" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_dashboard_declares_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace dashboard" in text
    assert "live_conversation:" in text
    assert "source: Comment" in text
    assert "conversation: count(Comment)" in text
    # Discussion desk + member my_tasks also carry the trail
    assert "workspace discussion_desk" in text
    assert "workspace my_tasks" in text
    # Goal B interesting_product: hero live threads use MessageScroller chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    for ws in ("dashboard", "my_tasks", "discussion_desk"):
        block = text.split(f"workspace {ws}", 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: Comment" in region, ws


def test_dashboard_declares_document_composition_spine() -> None:
    """Goal B document: Home surfaces named ProjectDocument headlines (not only Files desk)."""
    text = APP.read_text()
    assert "entity ProjectDocument" in text
    assert "display_field: headline" in text
    # Dashboard metrics + composition queue (hero still proof)
    dash = text.split("workspace dashboard", 1)[1].split("workspace project_board", 1)[0]
    assert "documents: count(ProjectDocument)" in dash
    assert "composition:" in dash
    assert "source: ProjectDocument" in dash
    assert "action: project_document_detail" in dash


def test_task_detail_discussion_uses_conversation_chrome() -> None:
    """Task hub Discussion is Message/Bubble trail (not queue meta) — cycle 1897."""
    text = APP.read_text()
    # Isolate task_detail surface block (before task_edit).
    assert 'surface task_detail "Task Detail"' in text
    block = text.split('surface task_detail "Task Detail"', 1)[1]
    block = block.split("surface task_edit", 1)[0]
    assert 'related comments "Discussion"' in block
    related = block.split('related comments "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: Comment" in related
    assert "columns: body, author, created_at" in related
    assert "display: queue" not in related


def test_comment_seeds_have_domain_true_discussion_copy() -> None:
    rows = [json.loads(line) for line in COMMENT_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
