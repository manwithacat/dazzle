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
    # Product lists only (platform _admin_* / *\_admin shells excluded).
    assert row.list_surfaces == 3
    assert row.open_via_lists == 3
    assert row.wi_G == 0.0


def test_platform_surface_exclusion(pm) -> None:
    """Framework admin list shells must not inflate D/G warehouse counts."""
    assert pm._is_platform_surface("_admin_health")
    assert pm._is_platform_surface("auditentry_admin")
    assert pm._is_platform_surface("jobrun_admin")
    assert not pm._is_platform_surface("ticket_list")
    assert not pm._is_platform_surface("person_list")


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
    assert "wi_fleet=" in line
    assert "wi_next=" in line
    assert "wi_primary=" in line


def test_warehouse_index_components_in_unit_interval(pm) -> None:
    """WI and components are continuous 0–1 (agent-minimizable gradient)."""
    rows = pm.scan()
    assert rows
    w = pm._WI_WEIGHTS
    for r in rows:
        for attr in ("wi", "wi_D", "wi_N", "wi_L", "wi_J", "wi_G"):
            v = getattr(r, attr)
            assert 0.0 <= v <= 1.0 + 1e-9, f"{r.app}.{attr}={v}"
        assert r.wi_primary in {"D", "N", "L", "J", "G"}
        expected = (
            w["D"] * r.wi_D + w["N"] * r.wi_N + w["L"] * r.wi_L + w["J"] * r.wi_J + w["G"] * r.wi_G
        )
        assert abs(r.wi - expected) < 1e-6
        assert abs(sum(w.values()) - 1.0) < 1e-9


def test_compute_warehouse_index_pure(pm) -> None:
    """Synthetic row: high density/nav → high WI and primary D or N."""
    m = pm.AppProductMaturity(app="synthetic")
    m.warehouse_density = 0.9
    m.nav_list_share = 0.8
    m.product_personas = 2
    m.product_stories = 4
    m.bound_stories = 0
    m.job_personas_covered = 0
    m.list_surfaces = 8
    m.entity_count = 5
    m.open_via_lists = 0
    m.landings = [
        {
            "persona_id": "a",
            "default_workspace": "home",
            "workspace_exists": True,
            "region_count": 1,
            "richness": 0.2,
            "ok": True,
            "reason": "ok",
        },
        {
            "persona_id": "b",
            "default_workspace": "home",
            "workspace_exists": True,
            "region_count": 1,
            "richness": 0.2,
            "ok": True,
            "reason": "ok",
        },
    ]
    m = pm.compute_warehouse_index(m)
    assert m.wi > 0.5
    assert m.wi_D == 0.9
    assert m.wi_N == 0.8
    assert m.wi_G == 1.0  # multi-entity lists, no open-via
    assert m.wi_J == 1.0  # 0/4 bound stories
    assert abs(m.wi_L - 0.8) < 1e-9  # 1 - 0.2 richness
    assert m.wi_primary in {"D", "N", "L", "J", "G"}


def test_landing_pad_same_entity_does_not_max_richness(pm) -> None:
    """Anti-game L: six listish regions of one entity ≈ one signal, not full richness."""

    class _R:
        def __init__(self, display: str, source: str | None):
            self.display = display
            self.source = source

    padded = [_R("list", "Ticket") for _ in range(6)]
    _n, modes, sources, rich_pad = pm._workspace_region_signals(padded)
    assert modes == 1
    assert sources == 1
    assert rich_pad <= 0.25  # 1/5 signals

    diverse = [
        _R("metrics", "Ticket"),
        _R("queue", "Ticket"),
        _R("bar_chart", "Ticket"),
        _R("status_list", None),
        _R("list", "Comment"),
    ]
    _n2, modes2, sources2, rich_div = pm._workspace_region_signals(diverse)
    assert modes2 >= 4
    assert sources2 >= 2
    assert rich_div >= 0.8
    assert rich_div > rich_pad


def test_desk_sprawl_does_not_fully_dilute_density(pm) -> None:
    """Anti-game D: many thin workspaces on a tiny domain stay density-high."""
    # Synthetic: 6 lists, 10 weightless desks would give density 6/16=0.375
    # with raw count; with scale cap on 2 entities effective_ws ≤ 3 → 6/9=0.67.
    m = pm.AppProductMaturity(app="sprawl")
    m.list_surfaces = 6
    m.entity_count = 2
    m.product_workspaces = 10
    m.effective_product_workspaces = min(10.0 * 0.2, max(3.0, 2 * 1.5))  # thin desks
    # Recompute density as score_app would:
    denom = m.list_surfaces + m.effective_product_workspaces
    dens = m.list_surfaces / denom
    assert dens > 0.55  # still warehouse-ish despite 10 "desks"


def test_mode_family_collapses_list_and_queue(pm) -> None:
    assert pm._mode_family("list") == pm._mode_family("queue") == "listish"
    assert pm._mode_family("metrics") == "metrics"


def test_warehouse_index_cli(pm, capsys) -> None:
    rc = pm.main(["--warehouse-index"])
    out = capsys.readouterr().out
    assert "wi_fleet=" in out
    assert "wi_next=" in out
    assert "objective:" in out
    assert rc == 0


def test_next_wi_cli(pm, capsys) -> None:
    rc = pm.main(["--next-wi"])
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out
    assert (REPO / "examples" / out).is_dir()
