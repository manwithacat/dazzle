"""Post-5.8 Goal B empty_region_honesty — fieldtest_hub secondary desks (cycle 1855)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/fieldtest_hub/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        for alt in ("\nsurface ", "\nentity ", "\naction ", "\nledger "):
            a = rest.find(alt)
            if a != -1:
                return text[start : start + 1 + a]
        return text[start:]
    return text[start : start + 1 + nxt]


def test_issue_triage_omits_critical_trail() -> None:
    """Triage: conversation + evidence + dual queues — not twin critical timeline."""
    block = _workspace_block("issue_triage")
    assert "live_conversation:" in block
    assert "field_evidence:" in block
    assert "triage_queue:" in block
    assert "critical_issues:" in block
    assert "critical_trail:" not in block
    assert "display: timeline" not in block
    assert "display: bar_chart" not in block


def test_firmware_pipeline_omits_status_bar_and_task_timeline() -> None:
    """Ship desk: metrics + release timeline + board + task queue — not status bar."""
    block = _workspace_block("firmware_pipeline")
    assert "release_metrics:" in block
    assert "firmware_releases:" in block
    assert "firmware_board:" in block
    assert "release_tasks:" in block
    assert "display: queue" in block  # open tasks are a pull queue
    assert "release_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert block.count("display: timeline") == 1


def test_device_fleet_omits_trail_and_status_bar() -> None:
    """Fleet desk: org boards + pressure queues — not trail/bar thrash."""
    block = _workspace_block("device_fleet")
    assert "fleet_metrics:" in block
    assert "by_model:" in block
    assert "by_status:" in block
    assert "unassigned_devices:" in block
    assert "active_devices:" in block
    assert "recall_queue:" in block
    assert "fleet_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    # Cycle 1938 org_structure: model/lifecycle boards before queues.
    assert "focus: fleet_metrics, by_status, by_model, unassigned_devices, active_devices" in block


def test_draft_releases_omits_twin_queue_trail_and_bar() -> None:
    """Draft pressure: one queue + metrics — not twin queue / trail / status bar."""
    block = _workspace_block("draft_releases")
    assert "draft_metrics:" in block
    assert "draft_queue:" in block
    assert "draft_grid:" not in block
    assert "draft_trail:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block


def test_tester_roster_omits_session_trail() -> None:
    """Org desk: skill + region + roster — not session timeline dump."""
    block = _workspace_block("tester_roster")
    assert "by_skill:" in block
    assert "by_location:" in block
    assert "active_testers:" in block
    assert "unassigned_devices:" in block
    assert "session_trail:" not in block
    assert "display: timeline" not in block
    assert "display: bar_chart" not in block


def test_manager_ops_omits_fleet_status_bar() -> None:
    """Ops home: multi-panel fold + under-fold boards — not fleet status bar dump."""
    block = _workspace_block("manager_ops")
    assert "quality_strip:" in block
    assert "critical_issues:" in block
    assert "device_attention:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "fleet_status_mix:" not in block
    # bar_chart dogfood lives on eng/tester homes, not under manager ops fold.
    assert "display: bar_chart" not in block


def test_engineering_dashboard_keeps_bar_and_timeline_coverage() -> None:
    """Hero prune must not leave bar_chart/timeline fleet-uncovered (gallery desk)."""
    block = _workspace_block("engineering_dashboard")
    assert "display: bar_chart" in block
    assert "display: timeline" in block
    assert "severity_mix:" in block
