"""Post-5.8 Goal B command_density — fieldtest_hub Manager Ops dual attention."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/fieldtest_hub/dsl/app.dsl"


def _manager_ops_block() -> str:
    text = APP.read_text()
    start = text.index('workspace manager_ops "Manager Ops":')
    end = text.index("workspace issue_triage", start)
    return text[start:end]


def test_manager_ops_declares_dual_attention_before_conversation() -> None:
    """Peer field-ops homes put ≥2 attention panels above a conversation trail."""
    block = _manager_ops_block()
    assert "quality_strip:" in block
    assert "critical_issues:" in block
    assert "device_attention:" in block
    assert "live_conversation:" in block
    # Order: quality → critical → device → conversation (command density).
    assert block.index("quality_strip:") < block.index("critical_issues:")
    assert block.index("critical_issues:") < block.index("device_attention:")
    assert block.index("device_attention:") < block.index("live_conversation:")


def test_manager_ops_caps_attention_queues_for_fold_share() -> None:
    block = _manager_ops_block()
    # Caps keep dual panels + conversation sharing the fold (ops_dashboard pattern).
    assert "limit: 4" in block
    assert "focus: quality_strip, critical_issues, device_attention, live_conversation" in block
    assert "Multi-panel field ops" in block or "multi-panel" in block.lower()


def test_manager_ops_quality_strip_counts_critical_and_conversation() -> None:
    block = _manager_ops_block()
    assert "critical: count(IssueReport where severity = critical" in block
    assert "conversation: count(IssueNote)" in block
