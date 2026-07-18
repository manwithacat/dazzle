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
