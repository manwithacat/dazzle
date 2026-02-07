"""
Testing mission: drives E2E tests via the DazzleAgent.

This replaces the hardcoded test loop in agent_e2e.py with a
Mission object that plugs into the generic agent framework.
"""

from __future__ import annotations

from typing import Any

from ..core import Mission
from ..models import ActionType, AgentAction, Step


def build_test_mission(
    test_spec: dict[str, Any],
    base_url: str = "http://localhost:3000",
) -> Mission:
    """
    Build a Mission for E2E testing.

    Args:
        test_spec: Test specification with goals and expected outcomes
        base_url: Base URL of the application

    Returns:
        Mission configured for E2E testing
    """
    description = test_spec.get("description", test_spec.get("title", ""))
    expected_outcomes = test_spec.get("expected_outcomes", [])
    test_id = test_spec.get("test_id", "unknown")

    outcomes_text = "\n".join(f"  - {o}" for o in expected_outcomes)

    system_prompt = f"""You are an E2E test agent. Your goal is to test a web application by navigating and interacting with it.

## Test Goal
{description}

## Expected Outcomes
{outcomes_text}

## Rules
1. Analyze the current page state carefully
2. Take one action at a time toward the goal
3. Use the most reliable selectors (IDs, data-testid, unique text)
4. Call "done" when the test goal is achieved or you determine it cannot be achieved
5. Keep reasoning concise but informative"""

    return Mission(
        name=f"e2e_test:{test_id}",
        system_prompt=system_prompt,
        max_steps=15,
        token_budget=50_000,
        start_url=base_url,
        context={"test_spec": test_spec},
    )


def test_completion(action: AgentAction, history: list[Step]) -> bool:
    """E2E test completion: stop on DONE action."""
    return action.type == ActionType.DONE
