"""Post-5.8 Goal B command_density — acme_billing multi-panel billing desk."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"


def _billing_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace billing "Acme Billing":')
    end = text.index('workspace my_work "My Work":', start)
    return text[start:end]


def test_billing_declares_dual_attention_before_conversation() -> None:
    """Peer billing homes put ≥2 attention panels above the note trail."""
    block = _billing_block()
    assert "portfolio_metrics:" in block
    assert "open_invoices:" in block
    assert "sensitive_flags:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → open → sensitive → composition → conversation.
    assert block.index("portfolio_metrics:") < block.index("open_invoices:")
    assert block.index("open_invoices:") < block.index("sensitive_flags:")
    assert block.index("sensitive_flags:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")


def test_billing_caps_attention_for_fold_share() -> None:
    block = _billing_block()
    assert "limit: 4" in block
    # Goal B media invoice_packets leads; dual attention + composition trail follow.
    assert (
        "focus: invoice_packets, portfolio_metrics, open_invoices, "
        "sensitive_flags, composition, live_conversation"
    ) in block
    assert "Multi-panel" in block or "multi-panel" in block.lower()


def test_billing_metrics_count_open_sensitive_and_conversation() -> None:
    block = _billing_block()
    assert "open_books: count(Invoice where sensitive != true)" in block
    assert "sensitive: count(Invoice where sensitive = true)" in block
    assert "conversation: count(InvoiceNote)" in block
    assert "filter: sensitive != true" in block
    assert "filter: sensitive = true" in block
