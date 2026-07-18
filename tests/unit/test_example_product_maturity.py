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
    assert row.tier in {"ok", "deepen"}  # may deepen on density, not critical


def test_fleet_scan_returns_rows(pm) -> None:
    rows = pm.scan()
    assert len(rows) >= 5
    apps = {r.app for r in rows}
    assert "support_tickets" in apps


def test_status_line(pm) -> None:
    rows = pm.scan()
    line = pm.format_status(rows)
    assert line.startswith("product_maturity ")
    assert "residual=" in line
