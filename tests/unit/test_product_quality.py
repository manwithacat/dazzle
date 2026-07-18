"""Unit tests for dazzle.product_quality (#1626 felt demo bar)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.product_quality.bar import score_project, score_status_lines
from dazzle.product_quality.persona_homes import (
    STABLE_PERSONA_USER_IDS,
    score_persona_homes,
)
from dazzle.product_quality.stills import score_stills

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"


def test_stable_persona_ids_include_showcase_roles() -> None:
    for role in (
        "member",
        "manager",
        "agent",
        "approver",
        "finance",
        "admin",
        "tester",
        "engineer",
        "ops_engineer",
    ):
        assert role in STABLE_PERSONA_USER_IDS
        uid = STABLE_PERSONA_USER_IDS[role]
        assert uid.startswith("a1000000-")


def test_platform_admin_landing_is_residual() -> None:
    """Product admin must not land on framework _platform_admin (#1626)."""
    from dazzle.product_quality.persona_homes import _score_one_persona

    home = _score_one_persona("admin", "_platform_admin", {}, seed=None, min_hits=1)
    assert home.residual
    assert any("platform_admin_landing" in r.reason for r in home.regions)


def test_fieldtest_tester_home_seeded() -> None:
    app = EXAMPLES / "fieldtest_hub"
    if not app.is_dir():
        pytest.skip("fieldtest_hub missing")
    homes = {h.persona: h for h in score_persona_homes(app)}
    assert "tester" in homes
    assert not homes["tester"].residual
    assert any(r.seed_hits >= 1 for r in homes["tester"].regions)


def test_persona_homes_simple_task_has_member_desk() -> None:
    app = EXAMPLES / "simple_task"
    if not app.is_dir():
        pytest.skip("simple_task missing")
    homes = score_persona_homes(app)
    by_persona = {h.persona: h for h in homes}
    assert "member" in by_persona or "manager" in by_persona
    # At least one product persona should have current_user regions scored
    scored = [h for h in homes if h.regions]
    assert scored, "expected assignment-aware regions on simple_task"


def test_score_project_single_app() -> None:
    app = EXAMPLES / "simple_task"
    if not (app / "dazzle.toml").is_file():
        pytest.skip("simple_task missing")
    report = score_project(app)
    assert report.project.endswith("simple_task")
    assert report.probes
    names = {p.name for p in report.probes}
    assert "product_maturity" in names
    assert "demo_fleet" in names
    lines = score_status_lines(report)
    assert any("product_quality residual_total=" in ln for ln in lines)
    payload = report.to_dict()
    assert "residual_total" in payload
    assert "recommended" in payload


def test_score_project_fleet_scope() -> None:
    if not EXAMPLES.is_dir():
        pytest.skip("examples/ missing")
    report = score_project(EXAMPLES, app="support_tickets")
    assert report.app == "support_tickets"
    assert isinstance(report.persona_homes, list)
    assert isinstance(report.stills, list)
    assert report.probes


def test_stills_absent_dir_returns_empty(tmp_path: Path) -> None:
    assert score_stills(tmp_path, "simple_task") == []


def test_stills_empty_hero_residual(tmp_path: Path) -> None:
    shots = tmp_path / ".dazzle" / "qa" / "screenshots"
    shots.mkdir(parents=True)
    tiny = shots / "task_board_manager_desktop_light.png"
    tiny.write_bytes(b"\x89PNG" + b"\x00" * 100)
    scores = score_stills(tmp_path, "simple_task")
    assert scores
    hero = next(s for s in scores if s.name == tiny.name)
    assert hero.residual
    assert "empty_hero" in hero.reason


def test_mcp_handler_score() -> None:
    from dazzle.mcp.server.handlers.product_quality import (
        product_quality_score_handler,
    )

    app = EXAMPLES / "simple_task"
    if not (app / "dazzle.toml").is_file():
        pytest.skip("simple_task missing")
    raw = product_quality_score_handler(app, {"project_root": str(app)})
    data = json.loads(raw)
    assert "error" not in data
    assert "residual_total" in data
    assert "status_lines" in data
    assert data["status_lines"]


def test_mcp_tool_registered() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    tools = {t.name: t for t in get_consolidated_tools()}
    assert "product_quality" in tools
    schema = tools["product_quality"].inputSchema
    ops = schema["properties"]["operation"]["enum"]
    assert ops == ["score"]


def test_mcp_dispatch_handler() -> None:
    from dazzle.mcp.server.handlers_consolidated import CONSOLIDATED_TOOL_HANDLERS

    assert "product_quality" in CONSOLIDATED_TOOL_HANDLERS


def test_persona_payload_regions_on_report() -> None:
    """Regression: _persona_payload must attach h.regions (not dead branch)."""
    app = EXAMPLES / "invoice_ops"
    if not (app / "dazzle.toml").is_file():
        pytest.skip("invoice_ops missing")
    report = score_project(app)
    for home in report.persona_homes:
        assert "regions" in home
        assert isinstance(home["regions"], list)
