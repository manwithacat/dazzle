"""Tests for the MCP guide tool (v0.71.7).

The handlers consume the AppSpec-loader pipeline. Tests run against
``examples/simple_task`` which committed a real ``workspace_setup``
guide in v0.71.0.
"""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.mcp.server.handlers.guide import (
    guide_concordance_handler,
    guide_get_handler,
    guide_list_handler,
    guide_narrate_handler,
)

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "simple_task"


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


def test_mcp_list_returns_summary_of_every_guide() -> None:
    # simple_task ships one guide per interactive persona (admin /
    # manager / member) since the example-guides Phase 2 authoring pass.
    payload = json.loads(guide_list_handler(EXAMPLE_ROOT, {}))
    assert payload["total"] == 3
    by_name = {g["name"]: g for g in payload["guides"]}
    assert set(by_name) == {"workspace_setup", "manager_onboarding", "member_onboarding"}
    assert by_name["workspace_setup"]["audience"] == "persona = admin"
    assert by_name["manager_onboarding"]["audience"] == "persona = manager"
    assert by_name["member_onboarding"]["audience"] == "persona = member"
    workspace_setup = by_name["workspace_setup"]
    assert workspace_setup["step_count"] == 3
    assert workspace_setup["step_order"] == ["welcome_empty", "fill_title", "invite_team"]
    assert workspace_setup["has_on_complete"] is True


def test_mcp_get_returns_full_ir_for_named_guide() -> None:
    payload = json.loads(guide_get_handler(EXAMPLE_ROOT, {"name": "workspace_setup"}))
    assert payload["name"] == "workspace_setup"
    # All 3 steps materialised.
    assert len(payload["steps"]) == 3
    # On-complete block survived round-trip.
    assert payload["on_complete"]["redirect"] == "surface.task_list"


def test_mcp_get_rejects_missing_name() -> None:
    payload = json.loads(guide_get_handler(EXAMPLE_ROOT, {}))
    assert "error" in payload
    assert "'name'" in payload["error"]


def test_mcp_get_rejects_unknown_guide() -> None:
    payload = json.loads(guide_get_handler(EXAMPLE_ROOT, {"name": "no_such_guide"}))
    assert "error" in payload
    assert "no_such_guide" in payload["error"]


def test_mcp_concordance_returns_ok_for_clean_simple_task() -> None:
    """The committed simple_task guide passes concordance; the handler
    surfaces the same green result."""
    payload = json.loads(guide_concordance_handler(EXAMPLE_ROOT, {}))
    assert payload["ok"] is True
    assert payload["errors"] == []


def test_mcp_narrate_orders_steps_by_step_order() -> None:
    payload = json.loads(guide_narrate_handler(EXAMPLE_ROOT, {"name": "workspace_setup"}))
    names = [row["name"] for row in payload["steps_in_order"]]
    assert names == ["welcome_empty", "fill_title", "invite_team"]
    # Kinds preserved as IR strings.
    kinds = [row["kind"] for row in payload["steps_in_order"]]
    assert kinds == ["empty_state", "popover", "inline_card"]
    # complete_on payload flattened.
    welcome = payload["steps_in_order"][0]
    assert welcome["complete_on"]["kind"] == "event"
    assert welcome["complete_on"]["event_ref"] == "entity.Task.created"


def test_mcp_narrate_returns_no_orphans_for_clean_guide() -> None:
    payload = json.loads(guide_narrate_handler(EXAMPLE_ROOT, {"name": "workspace_setup"}))
    assert payload["orphan_steps"] == []
