"""Post-5.8 Goal B command_density — llm_ticket_classifier Support Dashboard."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"


def _support_dashboard_block() -> str:
    text = APP.read_text()
    start = text.index('workspace support_dashboard "Support Dashboard":')
    end = text.index('workspace ticket_management "Ticket Management":', start)
    return text[start:end]


def test_support_dashboard_declares_dual_attention_before_conversation() -> None:
    """Peer AI support homes put ≥2 attention panels above the reply trail."""
    block = _support_dashboard_block()
    assert "classification_metrics:" in block
    assert "high_severity:" in block
    assert "open_attention:" in block
    assert "composition:" in block
    assert "live_ai_replies:" in block
    # Order: metrics → high severity → open → documents → conversation.
    assert block.index("classification_metrics:") < block.index("high_severity:")
    assert block.index("high_severity:") < block.index("open_attention:")
    assert block.index("open_attention:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_ai_replies:")


def test_support_dashboard_caps_attention_for_fold_share() -> None:
    block = _support_dashboard_block()
    assert "limit: 4" in block
    # Goal B document (cycle 1876): readiness after dual attention + docs + replies.
    assert (
        "focus: classification_metrics, high_severity, open_attention, "
        "composition, live_ai_replies, triage_readiness" in block
    )
    assert "Multi-panel AI triage" in block or "multi-panel" in block.lower()
    # Conversation spine uses Message chrome after dual attention + documents.
    replies = block.split("live_ai_replies:", 1)[1][:400]
    assert "display: conversation" in replies
    assert "source: TicketClassification" in replies


def test_support_dashboard_metrics_count_severity_and_conversation() -> None:
    block = _support_dashboard_block()
    assert (
        "high_severity: count(TicketClassification where priority = high or priority = critical)"
        in block
    )
    assert "conversation: count(TicketClassification)" in block
    assert "documents: count(TicketDocument)" in block
    assert "filter: priority = high or priority = critical" in block
