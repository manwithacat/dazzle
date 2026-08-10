"""Post-5.8 Goal B document — ops_dashboard runbook/postmortem composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/ops_dashboard/dsl/seeds/demo_data/OpsDocument.jsonl"


def _command_center_block() -> str:
    text = APP.read_text()
    start = text.index('workspace command_center "Command Center":')
    end = text.index('workspace incident_review "Incident Review":', start)
    return text[start:end]


def test_ops_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity OpsDocument "Ops Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert "doc_kind: enum[runbook, postmortem, status_page, slo_brief, playbook]=runbook" in text
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_command_center_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Command Center before notes trail."""
    block = _command_center_block()
    assert "composition:" in block
    assert "source: OpsDocument" in block
    assert "documents: count(OpsDocument)" in block
    assert "action: ops_document_detail" in block
    # Order: dual attention → documents → conversation
    assert block.index("active_alerts:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: runbook_covers, health_summary, systems_attention, active_alerts, "
        "composition, live_conversation" in block
    )
    # Media cover wall is first; composition remains after dual attention.
    assert block.index("runbook_covers:") < block.index("health_summary:")


def test_ops_document_list_dual_open_and_system_hub() -> None:
    text = APP.read_text()
    assert 'surface ops_document_list "Ops Documents"' in text
    assert "open: OpsDocument via id | System via system" in text
    assert 'surface ops_document_detail "Ops Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: OpsDocument" in text


def test_ops_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across systems"
    kinds = set()
    statuses = set()
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["system"])
        assert str(row["id"]).startswith("64000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"runbook", "postmortem", "status_page", "slo_brief", "playbook"}
    assert statuses >= {"draft", "published"}
