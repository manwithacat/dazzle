"""Post-5.8 Goal B document — simple_task brief composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"
BRIEF_SEEDS = ROOT / "examples/simple_task/dsl/seeds/demo_data/TaskBrief.jsonl"


def test_task_brief_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity TaskBrief "Task Brief"' in text
    assert "display_field: headline" in text
    assert "doc_kind: enum[brief, acceptance, runbook, checklist]=brief" in text


def test_hero_workspaces_declare_composition_queue() -> None:
    text = APP.read_text()
    assert "workspace admin_dashboard" in text
    assert "workspace team_overview" in text
    assert "workspace my_work" in text
    assert "source: TaskBrief" in text
    assert "composition:" in text
    assert 'related briefs "Briefs"' in text
    assert "show: TaskBrief" in text
    assert "documents: count(TaskBrief)" in text


def test_brief_list_dual_open() -> None:
    text = APP.read_text()
    assert "open: TaskBrief via id | Task via task" in text
    assert 'surface brief_list "Briefs"' in text
    assert 'surface brief_detail "Brief Detail"' in text


def test_task_brief_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in BRIEF_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across tasks"
    kinds = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        kinds.add(row["doc_kind"])
        assert str(row["task"]).startswith("b2000000-")
        assert str(row["id"]).startswith("d5000000-")
    assert kinds >= {"brief", "acceptance", "runbook", "checklist"}
