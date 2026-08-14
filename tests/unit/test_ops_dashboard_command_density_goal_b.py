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
    # Caps keep dual panels + documents + conversation sharing the fold.
    assert "limit: 4" in block
    assert "focus: runbook_covers, health_summary, unacked_pages, acked_bridge" in block
    assert (
        "multi-panel" in block.lower() or "runbook cover" in block.lower() or "ack" in block.lower()
    )


def test_command_center_metrics_count_critical_and_conversation() -> None:
    block = _command_center_block()
    assert "critical_count: count(System where status = critical)" in block
    assert "documents: count(OpsDocument)" in block
    assert "conversation: count(IncidentNote)" in block
    assert "source: IncidentNote" in block
    assert "unacked_pages: count(Alert where status = active" in block
    assert "acked_pages: count(Alert where status = acknowledged" in block


def test_command_center_critical_bridge_density() -> None:
    """Cycle 2049 critical systems strip retained; cycle 2064 ack stage density."""
    block = _command_center_block()
    assert "\n  critical_systems:\n" in block
    assert "\n  unacked_pages:\n" in block
    assert "\n  acked_bridge:\n" in block
    crit = block.split("\n  critical_systems:\n", 1)[1].split("\n  unacked_pages:", 1)[0]
    assert "source: System" in crit
    assert "status = critical" in crit
    assert "status = offline" in crit
    assert "display: queue" in crit
    unacked = block.split("\n  unacked_pages:\n", 1)[1].split("\n  acked_bridge:", 1)[0]
    assert "source: Alert" in unacked
    assert "status = active" in unacked
    assert "severity = critical" in unacked
    assert "severity = high" in unacked
    acked = block.split("\n  acked_bridge:\n", 1)[1].split("\n  page_alerts:", 1)[0]
    assert "source: Alert" in acked
    assert "status = acknowledged" in acked
    assert "severity = critical" in acked
    assert "offline_count: count(System where status = offline)" in block
    # Order: health → critical systems → unacked → acked → dual attention
    assert block.index("\n  health_summary:\n") < block.index("\n  critical_systems:\n")
    assert block.index("\n  critical_systems:\n") < block.index("\n  unacked_pages:\n")
    assert block.index("\n  unacked_pages:\n") < block.index("\n  acked_bridge:\n")
    assert block.index("\n  acked_bridge:\n") < block.index("\n  systems_attention:\n")
    assert "focus: runbook_covers, health_summary, unacked_pages, acked_bridge" in block
    assert "ack_stage_density" in block.lower() or "unacked vs acked" in block.lower()
