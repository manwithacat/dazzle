"""#1605 agent closed-loop: context / binding / prove / playbook.

Pure path must work without importing dazzle.mcp (CyFuture P0).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from dazzle.agent_loop import binding_wall, build_context, build_playbook, prove_stories
from dazzle.core import ir
from dazzle.core.validation.extended import _lint_story_execution_bindings

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_agent_loop_import_without_mcp_package() -> None:
    """agent_loop must not pull dazzle.mcp (signing-only dual-lock pins)."""
    mod = importlib.import_module("dazzle.agent_loop.core")
    assert "dazzle.mcp" not in mod.__name__
    # Source-level guard: no import statements of dazzle.mcp
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("from dazzle.mcp", "import dazzle.mcp")):
            raise AssertionError(f"agent_loop.core must not import mcp: {stripped}")


def test_agent_context_on_simple_task() -> None:
    data = build_context(SIMPLE)
    assert data.get("ok") is True
    assert "runtime" in data
    assert "dazzle_version" in data["runtime"]
    assert data["counts"]["stories"] >= 1
    assert "next_steps" in data
    assert data["story_bindings"]["binding_gate"] in ("pass", "fail")
    assert "narrative_only_ratio" in data["story_bindings"]
    # CLI-first next steps
    assert any(s.get("kind") == "cli" for s in data["next_steps"])
    # #1605 pilot F — binding wall on context
    wall = data.get("story_wall") or {}
    assert wall.get("view") == "binding_wall"
    assert "buckets" in wall
    assert "executed_pass_static" in wall["buckets"]
    assert "narrative_only" in wall["buckets"]
    assert "markdown" in wall
    # service contract_diff light
    assert "contract_diff" in (data.get("services") or {})


def test_binding_wall_buckets_and_prove_pass() -> None:
    wall = binding_wall(SIMPLE)
    assert wall["view"] == "binding_wall"
    counts = wall["counts"]
    # ST-017 is process-bound and should land in pass_static
    pass_ids = {r["story_id"] for r in wall["buckets"]["executed_pass_static"]}
    assert "ST-017" in pass_ids
    assert "pass_static" in wall["markdown"] or "Executed + pass_static" in wall["markdown"]
    assert counts["executed_pass_static"] >= 1
    # Host auto_assign_task is present — ST-017 (and journey stories) pass_journey
    assert "executed_pass_journey" in wall["buckets"]
    assert "executed_fail_journey" in wall["buckets"]
    pass_j = {r["story_id"] for r in wall["buckets"]["executed_pass_journey"]}
    assert "ST-017" in pass_j
    assert counts["executed_pass_journey"] >= 1
    assert "pass_journey" in wall["markdown"] or "fail_journey" in wall["markdown"]


def test_agent_playbook_domain_logic() -> None:
    data = build_playbook("domain_logic")
    assert data["ok"] is True
    body = data["body"]
    assert "map → bind" in body or "map" in body
    assert "dazzle agent context" in body
    assert "dazzle agent wall" in body


def _minimal_appspec(stories: list[ir.StorySpec]) -> ir.AppSpec:
    return ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[]),
        stories=stories,
    )


def test_story_binding_lint_accepted_unbound_errors() -> None:
    story = ir.StorySpec(
        story_id="ST-999",
        title="x",
        persona="admin",
        trigger=ir.StoryTrigger.USER_CLICK,
        status=ir.StoryStatus.ACCEPTED,
    )
    errors, _ = _lint_story_execution_bindings(_minimal_appspec([story]))
    assert any("ST-999" in e and "executed_by" in e for e in errors)


def test_story_binding_lint_narrative_only_ok() -> None:
    story = ir.StorySpec(
        story_id="ST-998",
        title="x",
        persona="admin",
        trigger=ir.StoryTrigger.USER_CLICK,
        status=ir.StoryStatus.ACCEPTED,
        narrative_only=True,
    )
    errors, _ = _lint_story_execution_bindings(_minimal_appspec([story]))
    assert errors == []


def test_prove_process_bound_story_static_naming() -> None:
    data = prove_stories(SIMPLE, story_id="ST-017")
    assert data.get("results"), data
    r0 = data["results"][0]
    assert r0["story_id"] == "ST-017"
    assert r0["result"] == "pass_static", r0
    assert r0.get("evidence_kind") == "static"
    assert r0.get("executed_by", "").startswith("process.")
    assert data.get("evidence_kind") == "static"


def test_prove_runtime_process_service_host_ready() -> None:
    """ST-017 process + services/auto_assign_task.py → pass_runtime (dogfood closed loop)."""
    data = prove_stories(SIMPLE, story_id="ST-017", mode="runtime")
    assert data.get("evidence_kind") == "runtime"
    r0 = data["results"][0]
    assert r0["story_id"] == "ST-017"
    assert r0.get("static", {}).get("result") == "pass_static"
    assert r0["result"] == "pass_runtime", r0
    assert "service_ready:auto_assign_task" in (r0.get("evidence") or [])
    assert "service_contract_diff" in data


def test_inspect_host_service_ready_on_real_impl() -> None:
    from dazzle.agent_loop.runtime_prove import inspect_host_service

    insp = inspect_host_service(SIMPLE, "calculate_overdue_penalty", expected_inputs=["task_id"])
    assert insp["ok"] is True
    assert insp["exists"] is True


def test_agent_tool_registered() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    names = {t.name for t in get_consolidated_tools()}
    assert "agent" in names
