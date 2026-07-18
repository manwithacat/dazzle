"""#1626 P0-4 — product personas must not see platform admin chrome in nav."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def support_appspec():
    from dazzle.core.appspec_loader import load_project_appspec

    app = REPO / "examples" / "support_tickets"
    if not app.is_dir():
        pytest.skip("support_tickets missing")
    return load_project_appspec(app)


def test_agent_nav_has_no_platform_ops(support_appspec) -> None:
    from dazzle.page.converters.nav_builder import build_persona_nav
    from dazzle.rbac.matrix import generate_access_matrix

    matrix = generate_access_matrix(support_appspec)
    agent = next(p for p in support_appspec.personas if p.id == "agent")
    nav = build_persona_nav(support_appspec, agent, matrix)
    labels = [link.label for g in nav.groups for link in g.links]
    routes = [link.route or "" for g in nav.groups for link in g.links]
    blob = " ".join(labels + routes).lower()
    for banned in (
        "system health",
        "deploy history",
        "feedback report",
        "_platform_admin",
        "_admin_health",
        "systemhealth",
        "deployhistory",
    ):
        assert banned not in blob, f"agent nav leaked {banned!r}: {labels}"


def test_agent_nav_includes_job_workspace(support_appspec) -> None:
    from dazzle.page.converters.nav_builder import build_persona_nav
    from dazzle.rbac.matrix import generate_access_matrix

    matrix = generate_access_matrix(support_appspec)
    agent = next(p for p in support_appspec.personas if p.id == "agent")
    nav = build_persona_nav(support_appspec, agent, matrix)
    labels = [link.label for g in nav.groups for link in g.links]
    assert any("queue" in lab.lower() or "dashboard" in lab.lower() for lab in labels), labels
