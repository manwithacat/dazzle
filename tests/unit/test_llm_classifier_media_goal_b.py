"""Post-5.8 Goal B media — llm_ticket_classifier case brief cover wall (novel vs headshot)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"
DOC_SEEDS = ROOT / "examples/llm_ticket_classifier/dsl/seeds/demo_data/TicketDocument.jsonl"


def _workspace_block(name: str, end_marker: str) -> str:
    text = APP.read_text()
    start = text.index(f'workspace {name} "')
    end = text.index(end_marker, start + 1)
    return text[start:end]


def test_ticket_document_declares_preview_url() -> None:
    text = APP.read_text()
    block = text.split('entity TicketDocument "Ticket Document"')[1].split("entity ")[0]
    assert "preview_url: url" in block
    assert "photo_url" not in block
    assert "preview_url" in block.split("fitness:")[1]


def test_support_dashboard_case_brief_covers_first() -> None:
    """Novel media: case brief document thumbs win fold — not staff headshots."""
    block = _workspace_block(
        "support_dashboard",
        'workspace ticket_management "Ticket Management":',
    )
    assert "case_brief_covers:" in block
    assert "source: TicketDocument" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert "photo_url" not in block
    assert block.index("case_brief_covers:") < block.index("classification_metrics:")
    assert (
        "focus: case_brief_covers, classification_metrics, high_severity, "
        "open_attention, composition, live_ai_replies, triage_readiness" in block
    )


def test_ticket_management_case_brief_covers_first() -> None:
    block = _workspace_block(
        "ticket_management",
        'workspace classification_desk "Classifications":',
    )
    assert "case_brief_covers:" in block
    assert "display: grid" in block
    assert "preview_url != null" in block
    assert "media_shelf:" not in block
    assert block.index("case_brief_covers:") < block.index("agent_pulse:")
    assert (
        "focus: case_brief_covers, agent_pulse, live_ai_replies, ticket_queue, "
        "classification_trail, desk_readiness" in block
    )


def test_ticket_document_seeds_have_preview_urls() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    with_preview = [r for r in rows if r.get("preview_url")]
    assert len(with_preview) >= 8, "Goal B media expects cover previews on case briefs"
    assert all("placehold.co" in r["preview_url"] for r in with_preview)
