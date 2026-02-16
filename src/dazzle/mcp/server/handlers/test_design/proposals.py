"""Persona test proposal handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..common import extract_progress, load_project_appspec, wrap_handler_errors
from ..serializers import serialize_test_design

logger = logging.getLogger("dazzle.mcp")


def _parse_test_design_action(value: str) -> Any:
    """Parse a TestDesignAction with descriptive error on invalid input."""
    from dazzle.core.ir.test_design import TestDesignAction

    try:
        return TestDesignAction(value)
    except ValueError:
        valid = ", ".join(a.value for a in TestDesignAction)
        raise ValueError(f"'{value}' is not a valid action. Valid actions: {valid}") from None


def _parse_test_design_trigger(value: str) -> Any:
    """Parse a TestDesignTrigger with descriptive error on invalid input."""
    from dazzle.core.ir.test_design import TestDesignTrigger

    try:
        return TestDesignTrigger(value)
    except ValueError:
        valid = ", ".join(t.value for t in TestDesignTrigger)
        raise ValueError(f"'{value}' is not a valid trigger. Valid triggers: {valid}") from None


@wrap_handler_errors
def propose_persona_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Generate test designs from persona goals and workflows.

    Analyzes a persona's goals from DSL and proposes tests that verify
    the persona can achieve their stated objectives.
    """
    from datetime import UTC, datetime

    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.testing.test_design_persistence import get_next_test_design_id

    progress = extract_progress(args)

    progress.log_sync("Proposing persona tests...")
    app_spec = load_project_appspec(project_root)

    persona_filter = args.get("persona")
    max_tests = args.get("max_tests", 10)

    designs: list[TestDesignSpec] = []
    design_count = 0

    # Get starting ID
    base_id = get_next_test_design_id(project_root)
    base_num = int(base_id[3:])

    def next_id() -> str:
        nonlocal design_count
        result = f"TD-{base_num + design_count:03d}"
        design_count += 1
        return result

    now = datetime.now(UTC)

    # Filter personas
    personas_to_process = app_spec.personas
    if persona_filter:
        personas_to_process = [
            p for p in personas_to_process if p.id == persona_filter or p.label == persona_filter
        ]

    if not personas_to_process:
        return json.dumps(
            {
                "status": "no_personas",
                "message": "No personas found in DSL. Add persona definitions to generate persona-centric tests.",
                "available_personas": [p.id for p in app_spec.personas],
            }
        )

    for persona in personas_to_process:
        if design_count >= max_tests:
            break

        persona_name = persona.label or persona.id

        # Generate tests for each persona goal
        for goal in persona.goals[:3]:  # Limit goals per persona
            if design_count >= max_tests:
                break

            # Create test design for this goal
            steps = [
                TestDesignStep(
                    action=TestDesignAction.LOGIN_AS,
                    target=persona.id,
                    rationale=f"Authenticate as {persona_name}",
                ),
            ]

            # Find surfaces this persona can access
            # Note: WorkspaceSpec doesn't directly link to persona; use all workspaces
            surfaces_for_persona = []
            for ws in app_spec.workspaces:
                surfaces_for_persona.extend(ws.regions)

            # If persona has access to surfaces, navigate to first one
            if surfaces_for_persona:
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.NAVIGATE_TO,
                        target=surfaces_for_persona[0].name
                        if surfaces_for_persona
                        else "dashboard",
                        rationale="Navigate to persona's primary workspace",
                    )
                )

            # Add goal-specific action (inferred from goal text)
            if "create" in goal.lower() or "add" in goal.lower():
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CREATE,
                        target="entity",
                        data={"from_goal": goal},
                        rationale=f"Perform action to achieve: {goal}",
                    )
                )
            elif "view" in goal.lower() or "see" in goal.lower():
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.ASSERT_VISIBLE,
                        target="content",
                        data={"from_goal": goal},
                        rationale=f"Verify visibility for: {goal}",
                    )
                )
            else:
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CLICK,
                        target="action",
                        data={"from_goal": goal},
                        rationale=f"Interact to achieve: {goal}",
                    )
                )

            designs.append(
                TestDesignSpec(
                    test_id=next_id(),
                    title=f"{persona_name} can {goal.lower().rstrip('.')}",
                    description=f"Test that {persona_name} persona can achieve goal: {goal}",
                    persona=persona.id,
                    trigger=TestDesignTrigger.USER_CLICK,
                    steps=steps,
                    expected_outcomes=[
                        f"Goal achieved: {goal}",
                        "No errors or permission denials",
                    ],
                    entities=[],  # Will be filled by agent
                    surfaces=[s.name for s in surfaces_for_persona[:2]],
                    tags=["persona", persona.id, "goal"],
                    status=TestDesignStatus.PROPOSED,
                    prompt_version="v1",
                    created_at=now,
                    updated_at=now,
                )
            )

        # Generate test for persona accessing a workspace
        # Note: WorkspaceSpec doesn't directly link to persona; generate test for first workspace
        if app_spec.workspaces and design_count < max_tests:
            ws = app_spec.workspaces[0]  # Use first workspace
            designs.append(
                TestDesignSpec(
                    test_id=next_id(),
                    title=f"{persona_name} can access {ws.title or ws.name} workspace",
                    description=f"Test that {persona_name} can access and use the {ws.name} workspace",
                    persona=persona.id,
                    trigger=TestDesignTrigger.PAGE_LOAD,
                    steps=[
                        TestDesignStep(
                            action=TestDesignAction.LOGIN_AS,
                            target=persona.id,
                            rationale=f"Authenticate as {persona_name}",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.NAVIGATE_TO,
                            target=ws.name,
                            rationale=f"Go to {ws.title or ws.name} workspace",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.ASSERT_VISIBLE,
                            target=f"workspace:{ws.name}",
                            rationale="Verify workspace is accessible",
                        ),
                    ],
                    expected_outcomes=[
                        f"Workspace {ws.name} loads successfully",
                        "All workspace regions are visible",
                    ],
                    entities=[],
                    surfaces=[r.name for r in ws.regions],
                    tags=["persona", persona.id, "workspace"],
                    status=TestDesignStatus.PROPOSED,
                    prompt_version="v1",
                    created_at=now,
                    updated_at=now,
                )
            )

    # Convert to JSON-serializable format
    designs_data = [serialize_test_design(d) for d in designs]

    return json.dumps(
        {
            "proposed_count": len(designs_data),
            "max_tests": max_tests,
            "personas_analyzed": [p.id for p in personas_to_process],
            "note": "These are draft test designs. Review and call save_test_designs with accepted designs.",
            "designs": designs_data,
        },
        indent=2,
    )
