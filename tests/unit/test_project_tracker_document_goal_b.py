"""Post-5.8 Goal B document — project_tracker brief/spec composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/project_tracker/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/project_tracker/dsl/seeds/demo_data/ProjectDocument.jsonl"


def _dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace dashboard "Dashboard":')
    end = text.index('workspace project_board "Project Board":', start)
    return text[start:end]


def test_project_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity ProjectDocument "Project Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert "doc_kind: enum[brief, spec, proposal, status_report, decision]=brief" in text


def test_dashboard_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Dashboard before notes trail."""
    block = _dashboard_block()
    assert "composition:" in block
    assert "source: ProjectDocument" in block
    assert "documents: count(ProjectDocument)" in block
    assert "action: project_document_detail" in block
    # Order: open work → documents → conversation
    assert block.index("open_task_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: portfolio_metrics, open_task_queue, composition, live_conversation, "
        "project_overview, task_flow" in block
    )


def test_project_document_list_dual_open_and_project_hub() -> None:
    text = APP.read_text()
    assert 'surface project_document_list "Project Documents"' in text
    assert "open: ProjectDocument via id | Project via project" in text
    assert 'surface project_document_detail "Project Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: ProjectDocument" in text


def test_project_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across projects"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["project"]).startswith("6a000000-")
        assert str(row["id"]).startswith("6f000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"brief", "spec", "proposal", "status_report", "decision"}
    assert statuses >= {"draft", "published"}
