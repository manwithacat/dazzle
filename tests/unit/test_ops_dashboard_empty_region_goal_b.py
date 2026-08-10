"""Post-5.8 Goal B empty_region_honesty — ops_dashboard secondary desks (cycle 1852)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        # surfaces may follow
        for alt in ("\nsurface ", "\nentity ", "\naction "):
            a = rest.find(alt)
            if a != -1:
                return text[start : start + 1 + a]
        return text[start:]
    return text[start : start + 1 + nxt]


def test_systems_desk_omits_check_trail_and_status_bar() -> None:
    """Fleet desk: pulse + dual queues — not check timeline / status chart voids."""
    block = _workspace_block("systems_desk")
    assert "fleet_pulse:" in block
    assert "systems_grid:" in block
    assert "pressure_queue:" in block
    assert "check_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_alerts_desk_omits_trail_and_severity_bar() -> None:
    """On-call desk: pulse + active queue + pressure systems — not trail/bar thrash."""
    block = _workspace_block("alerts_desk")
    assert "alert_pulse:" in block
    assert "active_queue:" in block
    assert "systems_grid:" in block
    assert "alert_trail:" not in block
    assert "severity_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_integrations_desk_omits_enable_trail_and_status_bar() -> None:
    """Integrations: pending + live queues only."""
    block = _workspace_block("integrations_desk")
    assert "integration_pulse:" in block
    assert "pending_queue:" in block
    assert "live_grid:" in block
    assert "enable_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_active_alerts_omits_twin_queue_trail_and_bar() -> None:
    """Active pressure: one queue + metrics — not twin queue / trail / severity bar."""
    block = _workspace_block("active_alerts")
    assert "alert_pulse:" in block
    assert "active_queue:" in block
    assert "active_grid:" not in block
    assert "alert_trail:" not in block
    assert "severity_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_resolved_alerts_keeps_one_history_omits_twin_trail_and_bar() -> None:
    """Close-out: queue + one timeline — not twin trail + severity bar."""
    block = _workspace_block("resolved_alerts")
    assert "resolved_pulse:" in block
    assert "resolved_queue:" in block
    assert "resolved_grid:" in block
    assert "display: timeline" in block
    assert "resolve_trail:" not in block
    assert "severity_mix:" not in block
    assert "display: bar_chart" not in block
    assert block.count("display: timeline") == 1


def test_command_center_keeps_bar_and_timeline_coverage() -> None:
    """Hero prune must not leave bar_chart/timeline fleet-uncovered (gallery desk)."""
    block = _workspace_block("command_center")
    assert "display: bar_chart" in block
    assert "display: timeline" in block
    assert "alert_timeline:" in block
    assert "alert_severity_breakdown:" in block
