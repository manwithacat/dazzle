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
    assert (
        "focus: runbook_covers, health_summary, critical_systems, page_alerts, systems_attention, active_alerts, "
        "composition, live_conversation" in block
    )
    assert "multi-panel" in block.lower() or "runbook cover" in block.lower()


def test_command_center_metrics_count_critical_and_conversation() -> None:
    block = _command_center_block()
    assert "critical_count: count(System where status = critical)" in block
    assert "documents: count(OpsDocument)" in block
    assert "conversation: count(IncidentNote)" in block
    assert "source: IncidentNote" in block


def test_command_center_critical_bridge_density() -> None:
    """Cycle 2049: PagerDuty/Opsgenie critical bridge density above dual attention.

    Recipe critical_bridge_density — offline|critical systems + high|critical
    active pages — not systems_attention|active_alerts dual_attention re-stack alone.
    """
    block = _command_center_block()
    assert "\n  critical_systems:\n" in block
    assert "\n  page_alerts:\n" in block
    crit = block.split("\n  critical_systems:\n", 1)[1].split("\n  page_alerts:", 1)[0]
    assert "source: System" in crit
    assert "status = critical" in crit
    assert "status = offline" in crit
    assert "display: queue" in crit
    assert "limit: 3" in crit
    pages = block.split("\n  page_alerts:\n", 1)[1].split("\n  systems_attention:", 1)[0]
    assert "source: Alert" in pages
    assert "severity = critical" in pages
    assert "severity = high" in pages
    assert "status = active" in pages
    assert "display: queue" in pages
    assert "offline_count: count(System where status = offline)" in block
    assert (
        "page_alerts: count(Alert where status = active and (severity = critical or severity = high))"
        in block
    )
    # Order: health → critical bridge → broad dual attention
    assert block.index("\n  health_summary:\n") < block.index("\n  critical_systems:\n")
    assert block.index("\n  critical_systems:\n") < block.index("\n  page_alerts:\n")
    assert block.index("\n  page_alerts:\n") < block.index("\n  systems_attention:\n")
    assert block.index("\n  systems_attention:\n") < block.index("\n  active_alerts:\n")
    assert (
        "focus: runbook_covers, health_summary, critical_systems, page_alerts, systems_attention, active_alerts, "
        "composition, live_conversation" in block
    )
