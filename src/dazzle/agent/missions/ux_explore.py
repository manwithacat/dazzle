"""UX Explore mission: bottom-up discovery of missing contracts and edge cases.

Two strategies:
- MISSING_CONTRACTS: agent explores the canonical example looking for
  interactions that have no ux-architect contract yet. Produces
  "propose_component" findings → PROP-NNN rows in the backlog.
- EDGE_CASES: agent re-tests shipped components with adversarial inputs
  (empty state, max content, keyboard-only, rapid interactions) to find
  failures outside the defined quality gates. Produces "record_edge_case"
  findings → EX-NNN rows in the backlog.

The calling loop (`/ux-cycle`) alternates strategies and aggregates the
results into the backlog.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..core import AgentTool, Mission
from ._shared import make_stagnation_completion


class Strategy(Enum):
    MISSING_CONTRACTS = "missing_contracts"
    EDGE_CASES = "edge_cases"


def make_propose_component_tool(proposals: list[dict[str, Any]]) -> AgentTool:
    """Create the propose_component tool that records new component proposals."""

    def handler(args: dict[str, Any]) -> str:
        proposals.append(
            {
                "component_name": args["component_name"],
                "description": args["description"],
                "example_app": args["example_app"],
            }
        )
        return f"Proposed: {args['component_name']}"

    return AgentTool(
        name="propose_component",
        description=(
            "Propose a new UX component that should have a ux-architect contract "
            "but doesn't yet. Use when you observe an interaction pattern (drag, drop, "
            "inline edit, popover, etc.) that isn't covered by an existing contract."
        ),
        schema={
            "type": "object",
            "properties": {
                "component_name": {
                    "type": "string",
                    "description": "Kebab-case name for the proposed component (e.g. 'tree-view').",
                },
                "description": {
                    "type": "string",
                    "description": "One-paragraph description of what this component does and why it needs a contract.",
                },
                "example_app": {
                    "type": "string",
                    "description": "The example app where you observed this pattern.",
                },
            },
            "required": ["component_name", "description", "example_app"],
        },
        handler=handler,
    )


def make_record_edge_case_tool(findings: list[dict[str, Any]]) -> AgentTool:
    """Create the record_edge_case tool that records edge case failures."""

    def handler(args: dict[str, Any]) -> str:
        findings.append(
            {
                "component_name": args["component_name"],
                "description": args["description"],
                "example_app": args["example_app"],
                "severity": args.get("severity", "minor"),
            }
        )
        return f"Recorded edge case: {args['component_name']} — {args['severity']}"

    return AgentTool(
        name="record_edge_case",
        description=(
            "Record an edge case failure on a shipped component (one that has "
            "a ux-architect contract and passed its quality gates). Use when you "
            "find a failure outside the defined gates — e.g. empty state, max "
            "content, keyboard-only flow, rapid interaction."
        ),
        schema={
            "type": "object",
            "properties": {
                "component_name": {
                    "type": "string",
                    "description": "The component where the edge case occurs.",
                },
                "description": {
                    "type": "string",
                    "description": "One-sentence description of the edge case and how to reproduce it.",
                },
                "example_app": {
                    "type": "string",
                    "description": "The example app where you reproduced the issue.",
                },
                "severity": {
                    "type": "string",
                    "enum": ["blocker", "major", "minor", "polish"],
                    "description": "Severity of the issue.",
                },
            },
            "required": ["component_name", "description", "example_app"],
        },
        handler=handler,
    )


def _build_missing_contracts_prompt(persona: Any, example_app: str) -> str:
    persona_label = getattr(persona, "label", None) or getattr(persona, "id", "unknown")
    return f"""You are exploring the Dazzle example app `{example_app}` as persona **{persona_label}**, looking for UX components that should have a ux-architect contract but don't yet.

## What counts as a component

A UX component is a recurring interaction pattern with its own internal state and behaviour. Examples of components that ALREADY have contracts:
- dashboard-grid, card, data-table

Examples of components that might NOT have contracts yet:
- form (with multi-step wizards, field dependencies, validation)
- modal / dialog
- popover / tooltip
- tree view
- kanban board (different from dashboard grid)
- rich text editor
- date picker
- command palette
- slide-over drawer

## Your approach

1. Navigate the app and notice the interactions you encounter.
2. For each distinct pattern, ask: "Does this already have a contract?" (You can assume dashboard-grid, card, data-table DO have contracts — everything else is fair game.)
3. If you find a pattern without a contract, call `propose_component` with the name, a one-paragraph description, and the app where you saw it.
4. Aim for 3-5 proposals per run. Don't propose trivial things like "button" or "link".

When you've proposed 3-5 components OR have explored the main areas of the app, emit DONE.
"""


def _build_edge_cases_prompt(persona: Any, example_app: str) -> str:
    persona_label = getattr(persona, "label", None) or getattr(persona, "id", "unknown")
    return f"""You are stress-testing shipped components in the Dazzle example app `{example_app}` as persona **{persona_label}**, looking for edge-case failures.

## What to test

Focus on components that HAVE a ux-architect contract and passed their quality gates. For each, try adversarial inputs:

- **Empty state:** What happens when the list/grid has 0 items? Can you still interact with the chrome?
- **Max content:** Very long text in a field. A column with 1000 characters. A card title that wraps to 5 lines.
- **Keyboard-only:** Can you do everything without the mouse? Are focus rings visible? Do all buttons have keyboard access?
- **Rapid interactions:** Double-click buttons. Press Enter twice. Hold down arrow keys. Does the app stay responsive?
- **Mid-action state:** Start dragging, press Esc. Start editing a cell, click away without saving.

## Your approach

1. For each shipped component you encounter (dashboard, data table, card), pick 2-3 adversarial tests from the list above.
2. When you find a failure (console error, visual glitch, broken state), call `record_edge_case` with the component name, a reproduction description, the app, and a severity (blocker/major/minor/polish).
3. Aim for 3-5 recorded findings per run.

When you've recorded 3-5 findings OR exhausted your adversarial approaches, emit DONE.
"""


def build_ux_explore_mission(
    strategy: Strategy,
    persona: Any,
    example_app: str,
    base_url: str,
    proposals: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> Mission:
    """Build a ux-explore Mission for one of the two strategies.

    Args:
        strategy: MISSING_CONTRACTS or EDGE_CASES
        persona: PersonaSpec for the run (must have id and label attrs)
        example_app: Name of the example app being explored
        base_url: Root URL of the running Dazzle app
        proposals: Mutable list for propose_component tool output
        findings: Mutable list for record_edge_case tool output

    Returns:
        A Mission ready to pass to DazzleAgent.run()
    """
    persona_id = getattr(persona, "id", "unknown")

    if strategy == Strategy.MISSING_CONTRACTS:
        prompt = _build_missing_contracts_prompt(persona, example_app)
        tools = [make_propose_component_tool(proposals)]
    elif strategy == Strategy.EDGE_CASES:
        prompt = _build_edge_cases_prompt(persona, example_app)
        tools = [make_record_edge_case_tool(findings)]
    else:
        raise ValueError(f"Unknown explore strategy: {strategy}")

    return Mission(
        name=f"ux_explore:{strategy.value}:{persona_id}",
        system_prompt=prompt,
        tools=tools,
        completion_criteria=make_stagnation_completion(window=8, label="explore"),
        max_steps=40,
        token_budget=60_000,
        context={
            "strategy": strategy.value,
            "persona_id": persona_id,
            "example_app": example_app,
            "base_url": base_url,
        },
        start_url=base_url,
    )
