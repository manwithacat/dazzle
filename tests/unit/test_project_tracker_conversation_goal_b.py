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


def test_dashboard_declares_document_composition_spine() -> None:
    """Goal B document: Home surfaces Attachment filenames (not only Files desk)."""
    text = APP.read_text()
    assert "entity Attachment" in text
    assert "display_field: filename" in text
    # Dashboard metrics + composition queue (hero still proof)
    dash = text.split("workspace dashboard", 1)[1].split("workspace project_board", 1)[0]
    assert "documents: count(Attachment)" in dash
    assert "composition:" in dash
    assert "source: Attachment" in dash
    assert "action: attachment_view" in dash


def test_comment_seeds_have_domain_true_discussion_copy() -> None:
    rows = [json.loads(line) for line in COMMENT_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
