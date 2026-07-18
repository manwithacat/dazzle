"""#1626 demo_fleet_bar probe — showcase apps stay above seed/nav floors."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "demo_fleet_bar.py"
SEEDS = REPO / "examples"


def _load():
    spec = importlib.util.spec_from_file_location("demo_fleet_bar", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_showcase_demo_fleet_bar_ok() -> None:
    mod = _load()
    residual = [r for r in (mod.score_app(a) for a in mod.SHOWCASE) if not r.ok]
    assert not residual, "demo_fleet residual: " + ", ".join(
        f"{r.app}:{','.join(r.issues)}" for r in residual
    )


def test_invoice_jsonl_submitted_per_tenant() -> None:
    """P0-9: each tenant has ≥3 submitted invoices for Approval Desk."""
    path = SEEDS / "invoice_ops" / "dsl" / "seeds" / "demo_data" / "Invoice.jsonl"
    assert path.is_file()
    by_tenant: Counter[str] = Counter()
    for row in _jsonl(path):
        if row.get("status") == "submitted":
            by_tenant[str(row.get("tenant_id"))] += 1
    assert by_tenant, "no submitted invoices"
    thin = {t: n for t, n in by_tenant.items() if n < 3}
    assert not thin, f"thin submitted tenants: {thin}"


def test_project_tracker_board_column_floors() -> None:
    """P0-5: Task.jsonl keeps kanban columns non-empty."""
    path = SEEDS / "project_tracker" / "dsl" / "seeds" / "demo_data" / "Task.jsonl"
    assert path.is_file()
    by = Counter(str(r.get("status")) for r in _jsonl(path))
    assert by["todo"] >= 3
    assert by["in_progress"] >= 3
    assert by["review"] >= 2


def test_design_studio_brand_hex_swatches() -> None:
    """P0-8: Brand.jsonl carries hex palettes for color widgets."""
    path = SEEDS / "design_studio" / "dsl" / "seeds" / "demo_data" / "Brand.jsonl"
    assert path.is_file()
    hex_ok = 0
    for row in _jsonl(path):
        pc = str(row.get("primary_color") or "")
        if pc.startswith("#") and len(pc) in (4, 7):
            hex_ok += 1
    assert hex_ok >= 3


def test_simple_task_member_has_assigned_work() -> None:
    """Re-eval #1: member My Work must have tasks assigned to stable member id."""
    from dazzle.http.runtime.test_routes import STABLE_PERSONA_USER_IDS

    member = STABLE_PERSONA_USER_IDS["member"]
    path = SEEDS / "simple_task" / "dsl" / "seeds" / "demo_data" / "Task.jsonl"
    rows = _jsonl(path)
    assigned = [r for r in rows if r.get("assigned_to") == member]
    assert len(assigned) >= 3, f"member assigned={len(assigned)}"


def test_support_agent_has_in_progress_assignments() -> None:
    """Re-eval #1: agent dashboard My Assigned needs in_progress tickets."""
    from dazzle.http.runtime.test_routes import STABLE_PERSONA_USER_IDS

    agent = STABLE_PERSONA_USER_IDS["agent"]
    path = SEEDS / "support_tickets" / "dsl" / "seeds" / "demo_data" / "Ticket.jsonl"
    rows = _jsonl(path)
    mine = [r for r in rows if r.get("assigned_to") == agent and r.get("status") == "in_progress"]
    assert len(mine) >= 2, f"agent in_progress={len(mine)}"


def test_queue_transitions_capped_to_primary_pair() -> None:
    """Re-eval #2: queue chrome must not show full state-machine walls."""
    from dazzle.http.runtime.workspace_region_computes import (
        _prefer_primary_queue_transitions,
    )

    farm = [
        {"to_state": s, "label": s}
        for s in (
            "paid",
            "partially_paid",
            "disputed",
            "approved",
            "rejected",
            "submitted",
        )
    ]
    out = _prefer_primary_queue_transitions(farm)
    assert len(out) == 2
    assert {t["to_state"] for t in out} == {"approved", "rejected"}
