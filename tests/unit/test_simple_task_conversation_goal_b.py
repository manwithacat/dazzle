"""Post-5.8 Goal B conversation — simple_task comments on admin/team desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/simple_task/dsl/seeds/demo_data/TaskComment.jsonl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_task_comment_display_field_is_content() -> None:
    text = APP.read_text()
    assert "entity TaskComment" in text
    assert "display_field: content" in text
    assert "content: text required" in text
    # Cycle 2058 peer-pack: note_kind (kind is reserved) for Linear/Asana density
    assert "note_kind: enum[note,blocker,question,decision]=note" in text
    assert "repr_fields: [task, author, content, note_kind]" in text


def test_hero_desks_declare_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace admin_dashboard" in text
    assert "workspace team_overview" in text
    assert "workspace my_work" in text
    assert "live_conversation:" in text
    assert "source: TaskComment" in text
    assert "conversation: count(TaskComment)" in text
    for ws in ("admin_dashboard", "team_overview", "my_work"):
        block = text.split(f"workspace {ws}", 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: TaskComment" in region, ws
        if ws != "team_overview":
            ux = block.split("ux:", 1)[1][:800]
            # admin focus is conversation density (2058); my_work keeps trail
            if ws == "my_work":
                assert "live_conversation" in ux, ws


def test_admin_declares_blocker_question_density() -> None:
    """Cycle 2058 blockers+questions; cycle 2074 decision_question_density."""
    block = _workspace_block("admin_dashboard")
    assert "open_blockers:" in block
    assert "open_questions:" in block
    assert "open_decisions:" in block
    assert "note_kind = blocker" in block
    assert "note_kind = question" in block
    assert "note_kind = decision" in block
    assert "blockers: count(TaskComment where note_kind = blocker)" in block
    assert "questions: count(TaskComment where note_kind = question)" in block
    assert "decisions: count(TaskComment where note_kind = decision)" in block
    assert block.index("open_questions:") < block.index("open_decisions:")
    assert block.index("open_decisions:") < block.index("media_shelf:")
    assert block.index("media_shelf:") < block.index("metrics:")
    assert block.index("open_decisions:") < block.index("composition:")
    assert block.index("composition:") < block.index("open_blockers:")
    assert block.index("open_blockers:") < block.index("live_conversation:")
    assert "focus: open_questions, open_decisions, media_shelf, metrics" in block
    assert (
        "decision_question_density" in block.lower()
        or "question vs decision" in block.lower()
        or "blocker_question_density" in block.lower()
    )


def test_open_decisions_filters_exclusive_decision_kind() -> None:
    """Cycle 2074 recipe decision_question_density — exclusive decision trail."""
    block = _workspace_block("admin_dashboard")
    dec = block.split("\n  open_decisions:\n", 1)[1].split("\n  media_shelf:", 1)[0]
    assert "source: TaskComment" in dec
    assert "note_kind = decision" in dec
    assert "display: conversation" in dec
    assert "limit: 4" in dec
    assert "note_kind = question" not in dec
    assert "note_kind = blocker" not in dec


def test_task_detail_discussion_uses_conversation_chrome() -> None:
    """Task hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    assert 'surface task_detail "Task Detail"' in text
    block = text.split('surface task_detail "Task Detail"', 1)[1]
    block = block.split("surface task_comments", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:280]
    assert "display: conversation" in related
    assert "show: TaskComment" in related
    assert "note_kind" in related
    assert "display: queue" not in related


def test_task_comment_seeds_have_domain_true_copy_and_kinds() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    kinds = {str(r.get("note_kind") or "") for r in rows}
    assert "blocker" in kinds
    assert "question" in kinds
    assert "decision" in kinds
    assert "note" in kinds
    assert sum(1 for r in rows if r.get("note_kind") == "blocker") >= 2
    assert sum(1 for r in rows if r.get("note_kind") == "question") >= 2
    assert sum(1 for r in rows if r.get("note_kind") == "decision") >= 2
    for row in rows:
        body = str(row.get("content") or "")
        assert len(body) >= 24, body
        assert " " in body
        assert row.get("note_kind") in ("note", "blocker", "question", "decision")
