"""#1605 agent closed-loop: context / binding / prove / playbook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.validation.extended import _lint_story_execution_bindings

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_agent_context_on_simple_task() -> None:
    from dazzle.mcp.server.handlers.agent_loop import agent_context_handler

    raw = agent_context_handler(SIMPLE, {})
    data = json.loads(raw)
    assert data.get("ok") is True
    assert "runtime" in data
    assert "dazzle_version" in data["runtime"]
    assert data["counts"]["stories"] >= 1
    assert "next_steps" in data
    assert data["story_bindings"]["binding_gate"] in ("pass", "fail")


def test_agent_playbook_domain_logic() -> None:
    from dazzle.mcp.server.handlers.agent_loop import agent_playbook_handler

    raw = agent_playbook_handler(SIMPLE, {"name": "domain_logic"})
    data = json.loads(raw)
    assert data["ok"] is True
    assert "map → bind" in data["body"] or "map → bind" in data["body"].replace("→", "->")


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


def test_prove_process_bound_story() -> None:
    from dazzle.mcp.server.handlers.agent_loop import agent_prove_handler

    raw = agent_prove_handler(SIMPLE, {"story_id": "ST-017"})
    data = json.loads(raw)
    assert data.get("results"), data
    r0 = data["results"][0]
    assert r0["story_id"] == "ST-017"
    assert r0["result"] == "pass", r0
    assert r0.get("executed_by", "").startswith("process.")


def test_agent_tool_registered() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    names = {t.name for t in get_consolidated_tools()}
    assert "agent" in names
