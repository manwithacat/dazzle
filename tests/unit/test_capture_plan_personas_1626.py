"""#1626 — capture plans use product personas, not field archetypes."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_support_tickets_plan_uses_product_personas() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.qa.capture import build_capture_plan

    app = REPO / "examples" / "support_tickets"
    if not app.is_dir():
        pytest.skip("support_tickets missing")
    appspec = load_project_appspec(app)
    targets = build_capture_plan(appspec)
    assert targets, "expected workspace capture targets"
    personas = {t.persona for t in targets}
    assert "Timestamped" not in personas
    assert "Auditable" not in personas
    assert personas & {"agent", "manager", "customer"}
    workspaces = {t.workspace for t in targets}
    assert not any(w.startswith("surface:System") for w in workspaces)
    assert "manager_ops" in workspaces or "ticket_queue" in workspaces
