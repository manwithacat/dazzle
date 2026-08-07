"""Post-5.8 Goal B command_density — ops_dashboard Command Center dual attention."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"


def _command_center_block() -> str:
    text = APP.read_text()
    start = text.index('workspace command_center "Command Center":')
    end = text.index('workspace incident_review "Incident Review":', start)
    return text[start:end]


def test_command_center_declares_dual_attention_before_conversation() -> None:
    """Peer ops homes put ≥2 attention panels above a conversation trail."""
    block = _command_center_block()
    assert "health_summary:" in block
    assert "systems_attention:" in block
    assert "active_alerts:" in block
    assert "live_conversation:" in block
    # Order: health pulse → systems → alerts → conversation (command density).
    assert block.index("health_summary:") < block.index("systems_attention:")
    assert block.index("systems_attention:") < block.index("active_alerts:")
    assert block.index("active_alerts:") < block.index("live_conversation:")


def test_command_center_caps_attention_queues_for_fold_share() -> None:
    block = _command_center_block()
    # Caps keep dual panels + conversation sharing the fold (fieldtest pattern).
    assert "limit: 4" in block
    assert "focus: health_summary, systems_attention, active_alerts, live_conversation" in block
    assert "Multi-panel ops" in block or "multi-panel" in block.lower()


def test_command_center_metrics_count_critical_and_conversation() -> None:
    block = _command_center_block()
    assert "critical_count: count(System where status = critical)" in block
    assert "conversation: count(IncidentNote)" in block
    assert "source: IncidentNote" in block
