"""UX Quality mission: drive Playwright through a component's quality gates.

Takes a parsed ux-architect component contract, a persona to run as,
and a target example app URL. Builds a Mission that:

1. Logs in via the QA mode magic link endpoint (POST /qa/magic-link)
2. Navigates to a page where the component is present
3. Drives each quality gate using a record_gate_result tool
4. Completes when all gates are recorded, on stagnation, or on budget exhaustion

The mission output lives in the `results` dict passed by the caller
(one entry per gate_id → {pass, observation}).
"""

from __future__ import annotations

from typing import Any

from ..core import AgentTool, Mission
from ..models import AgentAction, Step
from ._shared import ComponentContract


def make_record_gate_tool(results: dict) -> AgentTool:
    """Create the record_gate_result tool bound to a shared results dict."""

    def handler(args: dict) -> str:
        gate_id = args["gate_id"]
        passed = args["pass"]
        observation = args["observation"]
        results[gate_id] = {"pass": passed, "observation": observation}
        status = "PASS" if passed else "FAIL"
        return f"Recorded: {gate_id} = {status}"

    return AgentTool(
        name="record_gate_result",
        description=(
            "Record the pass/fail result for a quality gate with a brief observation. "
            "Call this once per gate after you've tested it."
        ),
        schema={
            "type": "object",
            "properties": {
                "gate_id": {
                    "type": "string",
                    "description": "The quality gate identifier (e.g. 'drag_threshold').",
                },
                "pass": {
                    "type": "boolean",
                    "description": "True if the gate passed, False if failed.",
                },
                "observation": {
                    "type": "string",
                    "description": "One sentence describing what you observed during the test.",
                },
            },
            "required": ["gate_id", "pass", "observation"],
        },
        handler=handler,
    )


def _build_system_prompt(
    contract: ComponentContract,
    persona: Any,
    example_app: str,
) -> str:
    """Assemble the system prompt for the UX quality agent."""
    persona_label = getattr(persona, "label", None) or getattr(persona, "id", "unknown")

    gate_lines: list[str] = []
    for gate in contract.quality_gates:
        gate_lines.append(f"- **{gate.id}**: {gate.description}")

    anatomy_str = (
        ", ".join(f"`{a}`" for a in contract.anatomy) if contract.anatomy else "(not specified)"
    )
    primitives_str = (
        ", ".join(f"`{p}`" for p in contract.primitives) if contract.primitives else "(none)"
    )

    gates_section = "\n".join(gate_lines)

    return f"""You are QA-testing the **{contract.component_name}** component as persona **{persona_label}** in the Dazzle example app `{example_app}`.

Your job: verify each of the component's quality gates passes against the running app. Use the `record_gate_result` tool to report pass/fail per gate with a brief observation.

## Component

- **Name:** {contract.component_name}
- **Anatomy:** {anatomy_str}
- **Primitives invoked:** {primitives_str}

## Quality Gates

You must test each of these and report the result using `record_gate_result`:

{gates_section}

## Approach

1. You are already logged in as {persona_label}. Navigate to a page where the {contract.component_name} component is present.
2. For each quality gate, perform the described test. If the described behaviour cannot be reproduced exactly, use your best judgement — the goal is to determine whether the contract is satisfied.
3. After testing each gate, call `record_gate_result` with:
   - `gate_id`: the id from the list above
   - `pass`: True or False
   - `observation`: one sentence describing what you saw
4. When all gates are recorded, emit a DONE action to complete the mission.

Be efficient. Each test should take 2-5 actions. Don't linger on pages or re-verify things you've already recorded. If a gate is ambiguous, record pass=False with an observation explaining why.
"""


def _make_stagnation_completion(window: int = 5):
    """Completion criteria: stop after `window` steps with no record_gate_result call."""

    def completion(action: AgentAction, history: list[Step]) -> bool:
        if len(history) < window:
            return False
        recent = history[-window:]
        for step in recent:
            if step.action.type.name == "TOOL" and step.action.target == "record_gate_result":
                return False
        return True

    return completion


def build_ux_quality_mission(
    contract: ComponentContract,
    persona: Any,
    example_app: str,
    base_url: str,
    results: dict,
) -> Mission:
    """Build a Mission that drives Playwright through a component's quality gates.

    Args:
        contract: Parsed ux-architect component contract
        persona: PersonaSpec (must have `id` and `label` attributes)
        example_app: Name of the example app (for logging/context only)
        base_url: Root URL of the running Dazzle app (e.g. http://localhost:3462)
        results: Dict to receive gate results (mutated by record_gate_result tool)

    Returns:
        A Mission ready to pass to DazzleAgent.run()
    """
    persona_id = getattr(persona, "id", "unknown")

    system_prompt = _build_system_prompt(contract, persona, example_app)
    record_tool = make_record_gate_tool(results)

    return Mission(
        name=f"ux_quality:{contract.component_name}:{persona_id}",
        system_prompt=system_prompt,
        tools=[record_tool],
        completion_criteria=_make_stagnation_completion(window=5),
        max_steps=30,
        token_budget=50_000,
        context={
            "component": contract.component_name,
            "persona_id": persona_id,
            "example_app": example_app,
            "base_url": base_url,
            "gate_count": len(contract.quality_gates),
        },
        start_url=base_url,
    )
