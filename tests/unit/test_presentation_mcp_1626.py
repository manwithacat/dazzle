"""#1626 MCP presentation tool — discoverability for improve + consumers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"
SUPPORT = EXAMPLES / "support_tickets"


def test_presentation_tool_in_registry() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    tools = {t.name: t for t in get_consolidated_tools()}
    assert "presentation" in tools
    ops = tools["presentation"].inputSchema["properties"]["operation"]["enum"]
    assert set(ops) == {"cognition", "opportunities", "residual"}
    # product_quality description mentions presentation residual
    assert "presentation" in tools["product_quality"].description.lower()
    assert "ref_as_repr" in tools["product_quality"].description or (
        "presentation residual" in tools["product_quality"].description.lower()
    )


def test_presentation_cognition_handler() -> None:
    from dazzle.mcp.server.handlers.presentation import presentation_cognition_handler

    data = json.loads(presentation_cognition_handler(Path("."), {}))
    assert data["ok"] is True
    assert "cognition" in data
    assert "hosts_audited_by_scanner" in data["cognition"]
    assert data["force"] == "framework-ux hyperpart_presentation"
    assert "presentation" in data["mcp"]["presentation_opportunities"]


def test_presentation_opportunities_support_tickets() -> None:
    from dazzle.mcp.server.handlers.presentation import presentation_opportunities_handler

    if not (SUPPORT / "dazzle.toml").is_file():
        pytest.skip("support_tickets missing")
    data = json.loads(presentation_opportunities_handler(SUPPORT, {}))
    assert data["ok"] is True
    assert data["app"] == "support_tickets"
    assert "presentation_cognition" in data
    assert data["schema_version"] == 2


def test_presentation_residual_missing_app_errors() -> None:
    from dazzle.mcp.server.handlers.presentation import handle_presentation

    raw = handle_presentation({"operation": "residual"})
    data = json.loads(raw)
    assert data.get("ok") is False or "error" in data or "required" in raw.lower()


def test_agents_md_lists_presentation_ops() -> None:
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "`presentation`" in text
    assert "cognition, opportunities, residual" in text


def test_counter_prior_ref_as_repr_loads() -> None:
    from dazzle.mcp.semantics_kb.counter_priors import load_all_counter_priors

    priors = {p.id: p for p in load_all_counter_priors()}
    assert "ref_as_repr" in priors
    assert priors["ref_as_repr"].status == "active"
    assert any("UUID" in t for t in priors["ref_as_repr"].triggers_text)
