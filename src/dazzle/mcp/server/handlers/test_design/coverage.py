"""Coverage action and runtime coverage gap handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.paths import project_test_results_dir

from ..common import error_response, extract_progress, load_project_appspec, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _generate_crud_steps(entity_name: str, operation: str) -> list[dict[str, Any]]:
    """Generate steps for a CRUD operation test."""
    entity_lower = entity_name.lower()
    route = f"/{entity_lower}s" if not entity_lower.endswith("s") else f"/{entity_lower}"

    if operation == "create":
        return [
            {"action": "navigate_to", "target": f"{route}/new", "rationale": "Go to create form"},
            {"action": "fill", "target": "form", "data": {}, "rationale": "Fill required fields"},
            {"action": "submit", "target": "form", "rationale": "Submit form"},
            {
                "action": "assert_visible",
                "target": f"entity:{entity_name}",
                "rationale": "Verify created",
            },
        ]
    elif operation == "read":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "first-item", "rationale": "Click first item"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify detail view"},
        ]
    elif operation == "update":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "edit-button", "rationale": "Click edit"},
            {"action": "fill", "target": "form", "data": {}, "rationale": "Modify fields"},
            {"action": "submit", "target": "form", "rationale": "Save changes"},
        ]
    elif operation == "delete":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "delete-button", "rationale": "Click delete"},
            {"action": "click", "target": "confirm-delete", "rationale": "Confirm deletion"},
        ]
    elif operation == "list":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list view"},
            {
                "action": "assert_visible",
                "target": f"entity:{entity_name}",
                "rationale": "Verify list renders",
            },
        ]
    return []


def _generate_view_steps(entity_name: str, view: str) -> list[dict[str, Any]]:
    """Generate steps for a UI view test."""
    entity_lower = entity_name.lower()
    route = f"/{entity_lower}s" if not entity_lower.endswith("s") else f"/{entity_lower}"

    if view == "list":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list view"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify list renders"},
        ]
    elif view == "detail":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list first"},
            {"action": "click", "target": "first-item", "rationale": "Click to view detail"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify detail view"},
        ]
    elif view == "create":
        return [
            {"action": "navigate_to", "target": f"{route}/new", "rationale": "Go to create form"},
            {"action": "assert_visible", "target": "form", "rationale": "Verify form renders"},
        ]
    elif view == "edit":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list first"},
            {"action": "click", "target": "edit-button", "rationale": "Click edit"},
            {"action": "assert_visible", "target": "form", "rationale": "Verify edit form"},
        ]
    return []


# ---------------------------------------------------------------------------
# Impl functions (no MCP types, explicit params, return plain dicts)
# ---------------------------------------------------------------------------


def test_design_coverage_actions_impl(
    project_root: Path,
    *,
    max_actions: int = 5,
    focus: str = "all",
) -> dict[str, Any]:
    """Get prioritized actions to increase test coverage."""
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    app_spec = load_project_appspec(project_root)

    existing_designs = load_test_designs(project_root)
    testspec = generate_e2e_testspec(app_spec)

    covered_personas: set[str] = set()
    covered_entities: set[str] = set()
    covered_scenarios: set[str] = set()

    for design in existing_designs:
        if design.persona:
            covered_personas.add(design.persona)
        covered_entities.update(design.entities)
        if design.scenario:
            covered_scenarios.add(design.scenario)

    all_entities = {e.name for e in app_spec.domain.entities}
    all_personas = {p.id for p in app_spec.personas}
    all_scenarios = {s.name for s in app_spec.scenarios}

    actions: list[dict[str, Any]] = []

    if focus in ("all", "personas"):
        for persona in app_spec.personas:
            if persona.id not in covered_personas and persona.goals:
                actions.append(
                    {
                        "priority": 1,
                        "category": "persona_tests",
                        "target": persona.id,
                        "title": f"Generate tests for {persona.label or persona.id}",
                        "impact": f"Covers {len(persona.goals)} persona goals",
                        "prompt": f"""Generate test designs for the "{persona.label or persona.id}" persona.

This persona has {len(persona.goals)} goals that need test coverage:
{chr(10).join(f"- {goal}" for goal in persona.goals)}

Use the `propose_persona_tests` MCP tool with persona="{persona.id}" to generate test designs, then review and save the accepted designs with `save_test_designs`.""",
                        "mcp_tool": "propose_persona_tests",
                        "mcp_args": {"persona": persona.id},
                    }
                )

    if focus in ("all", "state_machines", "entities"):
        for entity in app_spec.domain.entities:
            if entity.state_machine and entity.name not in covered_entities:
                sm = entity.state_machine
                transitions = [f"{t.from_state} \u2192 {t.to_state}" for t in sm.transitions]
                actions.append(
                    {
                        "priority": 2,
                        "category": "state_machine_tests",
                        "target": entity.name,
                        "title": f"Add state machine tests for {entity.name}",
                        "impact": f"Covers {len(sm.transitions)} state transitions",
                        "prompt": f"""Create test designs for the {entity.name} entity's state machine.

The state machine has these transitions:
{chr(10).join(f"- {t}" for t in transitions)}

Create a test design that:
1. Creates a {entity.name} in each initial state
2. Triggers each valid transition
3. Verifies the state changes correctly
4. Tests that invalid transitions are rejected

Save the test design with `save_test_designs` using test_id="SM_{entity.name.upper()}_001".""",
                        "code_template": _generate_state_machine_test_template(entity.name, sm),
                    }
                )

    if focus in ("all", "scenarios"):
        for scenario in app_spec.scenarios:
            if scenario.name not in covered_scenarios:
                actions.append(
                    {
                        "priority": 3,
                        "category": "scenario_tests",
                        "target": scenario.name,
                        "title": f"Add tests for scenario: {scenario.name}",
                        "impact": "Covers defined user workflow",
                        "prompt": f"""Create a test design for the "{scenario.name}" scenario.

Description: {scenario.description or "No description"}

This scenario defines a user workflow that should be tested end-to-end. Create a test design that:
1. Sets up the required preconditions
2. Executes the scenario steps
3. Verifies the expected outcomes

Save with `save_test_designs` using test_id="SCENARIO_{scenario.name.upper()}_001".""",
                    }
                )

    if focus in ("all", "entities"):
        for entity in app_spec.domain.entities:
            if entity.access and entity.name not in covered_entities:
                actions.append(
                    {
                        "priority": 4,
                        "category": "access_control_tests",
                        "target": entity.name,
                        "title": f"Add access control tests for {entity.name}",
                        "impact": "Verifies permission rules",
                        "prompt": f"""Create test designs for {entity.name} access control.

The entity has access rules that need testing:
- Verify authorized personas can access the entity
- Verify unauthorized personas are denied
- Test each permission (view, create, edit, delete) if applicable

Save with `save_test_designs` using test_id="ACL_{entity.name.upper()}_001".""",
                    }
                )

    if focus in ("all", "entities"):
        for entity in app_spec.domain.entities:
            if (
                entity.name not in covered_entities
                and not entity.state_machine
                and not entity.access
            ):
                actions.append(
                    {
                        "priority": 5,
                        "category": "entity_tests",
                        "target": entity.name,
                        "title": f"Add CRUD tests for {entity.name}",
                        "impact": "Basic entity coverage",
                        "prompt": f"""Create test designs for basic {entity.name} CRUD operations.

Note: Deterministic CRUD tests are auto-generated, but you can add persona-specific tests that:
1. Test CRUD from a specific persona's perspective
2. Verify business rules and validation
3. Test edge cases specific to this entity

Save with `save_test_designs` using test_id="CRUD_{entity.name.upper()}_001".""",
                    }
                )

    actions.sort(key=lambda x: x["priority"])
    actions = actions[:max_actions]

    total_items = len(all_entities) + len(all_personas) + len(all_scenarios)
    covered_items = len(covered_entities) + len(covered_personas) + len(covered_scenarios)
    coverage_score = (covered_items / total_items * 100) if total_items > 0 else 100.0

    summary = {
        "coverage_score": round(coverage_score, 1),
        "coverage_breakdown": {
            "entities": f"{len(covered_entities)}/{len(all_entities)}",
            "personas": f"{len(covered_personas)}/{len(all_personas)}",
            "scenarios": f"{len(covered_scenarios)}/{len(all_scenarios)}",
        },
        "deterministic_flows": len(testspec.flows),
        "custom_test_designs": len(existing_designs),
    }

    return {
        "summary": summary,
        "action_count": len(actions),
        "focus": focus,
        "guidance": (
            "Execute these actions in order to increase coverage. "
            "Each action includes a prompt you can follow directly. "
            "After completing an action, call get_coverage_actions again to get the next set."
        ),
        "actions": [
            {
                "priority": a["priority"],
                "category": a["category"],
                "target": a["target"],
                "title": a["title"],
                "impact": a["impact"],
                "prompt": a["prompt"],
                "mcp_tool": a.get("mcp_tool"),
                "mcp_args": a.get("mcp_args"),
                "code_template": a.get("code_template"),
            }
            for a in actions
        ],
        "next_steps": (
            "1. Read the first action's prompt\n"
            "2. Execute the suggested MCP tool or follow the instructions\n"
            "3. Save successful test designs with save_test_designs\n"
            "4. Call get_coverage_actions again to see updated coverage and next actions"
        ),
    }


def test_design_runtime_gaps_impl(
    project_root: Path,
    *,
    max_actions: int = 5,
    coverage_path: str | None = None,
) -> dict[str, Any]:
    """Analyze runtime UX coverage report to find gaps and generate tests."""
    if coverage_path:
        report_path = Path(coverage_path)
    else:
        candidates = [
            project_root / "dsl" / "tests" / "runtime_coverage.json",
            project_test_results_dir(project_root) / "ux_coverage.json",
        ]
        report_path = None
        for candidate in candidates:
            if candidate.exists():
                report_path = candidate
                break

    if not report_path or not report_path.exists():
        return {
            "error": "No runtime coverage report found",
            "hint": (
                "Run the E2E tests to generate a coverage report, then save it with "
                "save_runtime_coverage or provide a path with coverage_report_path"
            ),
            "searched_paths": [str(c) for c in candidates]
            if not coverage_path
            else [str(coverage_path)],
        }

    with open(report_path) as f:
        coverage = json.load(f)

    actions: list[dict[str, Any]] = []

    for entity_name, entity_data in coverage.get("entities", {}).items():
        missing_ops = entity_data.get("operations_missing", [])
        if missing_ops:
            for op in missing_ops:
                actions.append(
                    {
                        "priority": 1,
                        "category": "crud_gap",
                        "target": f"{entity_name}:{op}",
                        "title": f"Add {op} test for {entity_name}",
                        "impact": "Will increase entity CRUD coverage",
                        "test_design": {
                            "test_id": f"RUNTIME_{entity_name.upper()}_{op.upper()}_001",
                            "title": f"Test {op} operation for {entity_name}",
                            "description": f"Fill runtime coverage gap: {op} operation for {entity_name}",
                            "trigger": "user_click",
                            "steps": _generate_crud_steps(entity_name, op),
                            "expected_outcomes": [
                                f"{op.capitalize()} operation completes successfully"
                            ],
                            "entities": [entity_name],
                            "tags": ["crud", "runtime_gap", "automated"],
                            "status": "accepted",
                        },
                    }
                )

        missing_views = entity_data.get("ui_views_missing", [])
        if missing_views:
            for view in missing_views:
                actions.append(
                    {
                        "priority": 2,
                        "category": "ui_view_gap",
                        "target": f"{entity_name}:{view}",
                        "title": f"Add {view} view test for {entity_name}",
                        "impact": "Will increase entity UI coverage",
                        "test_design": {
                            "test_id": f"RUNTIME_{entity_name.upper()}_VIEW_{view.upper()}_001",
                            "title": f"Test {view} view for {entity_name}",
                            "description": f"Fill runtime coverage gap: {view} view for {entity_name}",
                            "trigger": "user_click",
                            "steps": _generate_view_steps(entity_name, view),
                            "expected_outcomes": [f"{view.capitalize()} view renders correctly"],
                            "entities": [entity_name],
                            "tags": ["ui_view", "runtime_gap", "automated"],
                            "status": "accepted",
                        },
                    }
                )

    routes_data = coverage.get("routes", {})
    if isinstance(routes_data, dict):
        total_routes = routes_data.get("total", 0)
        visited_routes = routes_data.get("visited", 0)
        if total_routes > visited_routes:
            actions.append(
                {
                    "priority": 3,
                    "category": "route_gap",
                    "target": "routes",
                    "title": f"Add navigation tests ({visited_routes}/{total_routes} routes covered)",
                    "impact": f"Will improve route coverage from {round(visited_routes / total_routes * 100 if total_routes else 0)}%",
                    "prompt": (
                        f"There are {total_routes - visited_routes} unvisited routes. "
                        "Create test designs that navigate to each surface/page in the application. "
                        "Check the DSL for surface definitions to identify routes."
                    ),
                }
            )

    actions.sort(key=lambda x: x["priority"])
    actions = actions[:max_actions]

    overall = coverage.get("overall_coverage", 0)
    summary = {
        "runtime_coverage": round(overall, 1),
        "route_coverage": coverage.get("route_coverage", 0),
        "crud_coverage": coverage.get("entity_crud_coverage", 0),
        "ui_coverage": coverage.get("entity_ui_coverage", 0),
        "gaps_found": len(actions),
        "report_path": str(report_path),
    }

    test_designs = [a["test_design"] for a in actions if "test_design" in a]

    return {
        "summary": summary,
        "gap_count": len(actions),
        "guidance": (
            "These test designs will fill gaps in runtime UX coverage. "
            "Save them with save_test_designs to have them execute in future test runs."
        ),
        "actions": actions,
        "ready_to_save": test_designs,
        "next_steps": (
            "1. Review the generated test designs\n"
            "2. Save with: save_test_designs(designs=<ready_to_save>)\n"
            "3. Run E2E tests to verify coverage improvement\n"
            "4. Save updated coverage with save_runtime_coverage"
        ),
    }


def test_design_save_runtime_impl(
    project_root: Path,
    *,
    coverage_data: dict[str, Any],
) -> dict[str, Any]:
    """Save runtime coverage report to dsl/tests/ for future analysis."""
    tests_dir = project_root / "dsl" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    output_path = tests_dir / "runtime_coverage.json"
    with open(output_path, "w") as f:
        json.dump(coverage_data, f, indent=2)

    return {
        "success": True,
        "path": str(output_path),
        "message": "Runtime coverage saved. Use get_runtime_coverage_gaps to analyze gaps.",
    }


def test_design_improve_coverage_impl(
    project_root: Path,
    *,
    max_actions: int = 5,
    focus: str = "all",
    coverage_path: str | None = None,
) -> dict[str, Any]:
    """Combined coverage improvement: static DSL gaps + runtime gaps."""
    static = test_design_coverage_actions_impl(project_root, max_actions=max_actions, focus=focus)
    runtime = test_design_runtime_gaps_impl(
        project_root, max_actions=max_actions, coverage_path=coverage_path
    )
    return {
        "static_coverage": static,
        "runtime_coverage": runtime,
    }


@wrap_handler_errors
def get_coverage_actions_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Get prioritized actions to increase test coverage.

    Returns actionable prompts an LLM can execute directly.
    """
    progress = extract_progress(args)
    progress.log_sync("Building coverage action list...")
    result = test_design_coverage_actions_impl(
        project_root,
        max_actions=args.get("max_actions", 5),
        focus=args.get("focus", "all"),
    )
    return json.dumps(result, indent=2)


def _generate_state_machine_test_template(entity_name: str, state_machine: Any) -> str:
    """Generate a test design template for state machine testing."""
    transitions = state_machine.transitions
    status_field = state_machine.status_field

    template_steps = []
    for t in transitions[:3]:  # Limit to first 3 transitions
        template_steps.append(
            {
                "action": "create",
                "target": f"entity:{entity_name}",
                "data": {status_field: t.from_state},
                "rationale": f"Create {entity_name} in '{t.from_state}' state",
            }
        )
        template_steps.append(
            {
                "action": "trigger_transition",
                "target": f"entity:{entity_name}",
                "data": {
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                },
                "rationale": f"Transition from '{t.from_state}' to '{t.to_state}'",
            }
        )

    return json.dumps(
        {
            "test_id": f"SM_{entity_name.upper()}_001",
            "title": f"State machine transitions for {entity_name}",
            "description": f"Verify all valid state transitions for {entity_name}",
            "trigger": "user_click",
            "steps": template_steps,
            "expected_outcomes": [
                "All valid transitions complete successfully",
                "Final state matches expected state",
            ],
            "entities": [entity_name],
            "tags": ["state_machine", "automated"],
        },
        indent=2,
    )


@wrap_handler_errors
def get_runtime_coverage_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze runtime UX coverage report to find gaps and generate tests.

    This reads the actual runtime coverage from test execution and identifies
    specific gaps that need test coverage.
    """
    progress = extract_progress(args)
    progress.log_sync("Analyzing runtime coverage gaps...")
    result = test_design_runtime_gaps_impl(
        project_root,
        max_actions=args.get("max_actions", 5),
        coverage_path=args.get("coverage_report_path"),
    )
    return json.dumps(result, indent=2)


@wrap_handler_errors
def save_runtime_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save runtime coverage report to dsl/tests/ for future analysis."""
    progress = extract_progress(args)

    coverage_data = args.get("coverage_data")
    if not coverage_data:
        return error_response("coverage_data is required")

    progress.log_sync("Saving runtime coverage report...")
    result = test_design_save_runtime_impl(project_root, coverage_data=coverage_data)
    return json.dumps(result, indent=2)
