"""Unit tests for scripts/example_product_maturity.py (anti-warehouse gate)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "example_product_maturity.py"


def _load():
    spec = importlib.util.spec_from_file_location("example_product_maturity", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def pm():
    return _load()


def test_support_tickets_is_structurally_ok(pm) -> None:
    """Flagship has product landings + workspaces — not critical residual."""
    app = REPO / "examples" / "support_tickets"
    if not app.is_dir():
        pytest.skip("support_tickets missing")
    row = pm.score_app(app)
    assert row.product_personas >= 3
    assert row.landing_ok >= 3
    assert row.tier == "ok"
    assert row.warehouse_density <= 0.70
    assert row.nav_list_share <= 0.70


def test_invoice_ops_job_desks(pm) -> None:
    """Role desks (not one shared mega-workspace) keep density/nav in band."""
    app = REPO / "examples" / "invoice_ops"
    if not app.is_dir():
        pytest.skip("invoice_ops missing")
    row = pm.score_app(app)
    assert row.tier == "ok"
    assert row.product_workspaces >= 4
    assert row.landing_ok == row.product_personas
    assert row.warehouse_density <= 0.70


def test_fleet_has_no_product_maturity_residual(pm) -> None:
    """Example fleet stays product-shaped — gate for minor/major example lifts."""
    rows = pm.scan()
    residual = [r for r in rows if r.is_residual]
    assert not residual, "product_maturity residual: " + ", ".join(
        f"{r.app}({r.tier}:{','.join(r.reasons)})" for r in residual
    )


def test_fleet_scan_returns_rows(pm) -> None:
    rows = pm.scan()
    assert len(rows) >= 5
    apps = {r.app for r in rows}
    assert "support_tickets" in apps
    assert "invoice_ops" in apps


def test_status_line(pm) -> None:
    rows = pm.scan()
    line = pm.format_status(rows)
    assert line.startswith("product_maturity ")
    assert "residual=" in line
    assert "residual=0" in line
    assert "critical=0" in line
