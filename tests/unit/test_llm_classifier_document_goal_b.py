"""Post-5.8 Goal B document — llm_ticket_classifier case brief composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/llm_ticket_classifier/dsl/seeds/demo_data/TicketDocument.jsonl"


def _support_dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace support_dashboard "Support Dashboard":')
    end = text.index('workspace ticket_management "Ticket Management":', start)
    return text[start:end]


def test_ticket_document_entity_is_document_composition() -> None:
    text = APP.read_text()
    assert 'entity TicketDocument "Ticket Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert (
        "doc_kind: enum[case_brief, macro, sla_note, escalation_plan, resolution]=case_brief"
        in text
    )
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_support_dashboard_declares_composition_after_dual_attention() -> None:
    """Goal B document: composition on Support Dashboard before AI reply trail."""
    block = _support_dashboard_block()
    assert "composition:" in block
    assert "source: TicketDocument" in block
    assert "documents: count(TicketDocument)" in block
    assert "action: ticket_document_detail" in block
    # Order: dual attention → documents → conversation
    assert block.index("open_attention:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_ai_replies:")
    assert (
        "focus: classification_metrics, high_severity, open_attention, "
        "composition, live_ai_replies, triage_readiness" in block
    )


def test_ticket_document_list_dual_open_and_ticket_hub() -> None:
    text = APP.read_text()
    assert 'surface ticket_document_list "Ticket Documents"' in text
    assert "open: TicketDocument via id | Ticket via ticket" in text
    assert 'surface ticket_document_detail "Ticket Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: TicketDocument" in text


def test_ticket_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8, "Goal B document expects composition lines across tickets"
    kinds = set()
    statuses = set()
    ticket_ids = {
        "d7571f1c-d20e-5553-9314-38cc71310818",
        "b0d82143-ba17-5067-b490-9bc513574de9",
        "67cc8ea4-be9a-5bd6-8181-d3f119af53ca",
        "821e22ac-fb9b-5f31-9cc4-7d207f55da88",
        "987db84e-0932-55f8-9515-d56dd0b987e0",
        "4f19bc8c-b245-591f-863f-27738d50047d",
        "c1ade692-9144-5570-add2-1d1d18d794b4",
    }
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["ticket"]) in ticket_ids
        assert str(row["id"]).startswith("d5000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {"case_brief", "macro", "sla_note", "escalation_plan", "resolution"}
    assert statuses >= {"draft", "published"}
