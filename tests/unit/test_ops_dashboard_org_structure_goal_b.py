"""Post-5.8 Goal B org_structure — ops_dashboard Systems desk fleet hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/ops_dashboard/dsl/app.dsl"
SYSTEM_SEEDS = ROOT / "examples/ops_dashboard/dsl/seeds/demo_data/System.jsonl"


def _systems_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace systems_desk "Systems":')
    end = text.index('workspace alerts_desk "Alerts":', start)
    return text[start:end]


def test_systems_desk_declares_service_type_and_status_before_flat() -> None:
    """Peer fleet tools show service-class / health org shape before flat roster."""
    block = _systems_desk_block()
    assert "by_service_type:" in block
    assert "display: kanban" in block
    assert "group_by: service_type" in block
    assert "by_status:" in block
    assert "group_by: status" in block
    assert "systems_grid:" in block
    assert "pressure_queue:" in block
    # Order: pulse → service-type board → status board → flat roster → pressure
    assert block.index("fleet_pulse:") < block.index("by_service_type:")
    assert block.index("by_service_type:") < block.index("by_status:")
    assert block.index("by_status:") < block.index("systems_grid:")
    assert block.index("systems_grid:") < block.index("pressure_queue:")


def test_systems_desk_ux_focus_org_before_load() -> None:
    block = _systems_desk_block()
    assert "focus: fleet_pulse, by_service_type, by_status, systems_grid, pressure_queue" in block
    assert "org structure" in block.lower() or "service class" in block.lower()
    # Prefer kanban org boards over under-fold service/status bar theater
    assert "service_mix:" not in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "as ops_engineer:" in block


def test_system_seeds_span_service_types_and_statuses() -> None:
    """Buyer-true fleet org needs multiple service classes and health states."""
    rows = [json.loads(line) for line in SYSTEM_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12
    types = {str(r.get("service_type") or "") for r in rows}
    statuses = {str(r.get("status") or "") for r in rows}
    assert "api" in types
    assert "web" in types
    assert "database" in types
    assert "cache" in types
    assert "queue" in types
    assert len(types) >= 4
    assert "healthy" in statuses
    assert "degraded" in statuses
    assert "critical" in statuses
    for row in rows:
        assert row.get("name")
        assert row.get("service_type")
        assert row.get("status")
