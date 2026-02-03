"""Test design tool handlers.

Handles persona test proposal, gap analysis, coverage actions,
runtime coverage, and test design persistence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

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

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

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
                p
                for p in personas_to_process
                if p.id == persona_filter or p.label == persona_filter
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
        designs_data = [
            {
                "test_id": d.test_id,
                "title": d.title,
                "description": d.description,
                "persona": d.persona,
                "trigger": d.trigger.value,
                "steps": [
                    {
                        "action": s.action.value,
                        "target": s.target,
                        "data": s.data,
                        "rationale": s.rationale,
                    }
                    for s in d.steps
                ],
                "expected_outcomes": d.expected_outcomes,
                "entities": d.entities,
                "surfaces": d.surfaces,
                "tags": d.tags,
                "status": d.status.value,
            }
            for d in designs
        ]

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
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_test_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze coverage and suggest what's missing.

    Returns untested entities, persona goals, state transitions, and suggested test designs.
    """
    from dazzle.core.ir.test_design import TestGap, TestGapAnalysis, TestGapCategory
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Load existing test designs
        existing_designs = load_test_designs(project_root)
        existing_entities: set[str] = set()
        existing_personas: set[str] = set()

        for design in existing_designs:
            existing_entities.update(design.entities)
            if design.persona:
                existing_personas.add(design.persona)

        # Generate deterministic tests to see what we already cover
        testspec = generate_e2e_testspec(app_spec)

        gaps: list[TestGap] = []

        # Check for untested entities (no custom test designs)
        all_entities = {e.name for e in app_spec.domain.entities}
        untested_entities = all_entities - existing_entities

        for entity_name in untested_entities:
            entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
            if entity:
                # High severity if it has state machine or access control
                severity: str = "medium"
                if entity.state_machine:
                    severity = "high"
                if entity.access:
                    severity = "high"

                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_ENTITY,
                        target=entity_name,
                        severity=severity,  # type: ignore[arg-type]
                        suggestion=f"Add persona-centric test designs for {entity_name}",
                    )
                )

        # Check for untested persona goals
        for persona in app_spec.personas:
            if persona.id not in existing_personas:
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_PERSONA_GOAL,
                        target=persona.id,
                        severity="high",
                        suggestion=f"Use propose_persona_tests to generate tests for {persona.label or persona.id}",
                    )
                )
            else:
                # Check if all goals are covered
                persona_designs = [d for d in existing_designs if d.persona == persona.id]
                covered_goals = 0
                for goal in persona.goals:
                    if any(
                        goal.lower() in (d.title.lower() if d.title else "")
                        for d in persona_designs
                    ):
                        covered_goals += 1

                if covered_goals < len(persona.goals):
                    gaps.append(
                        TestGap(
                            category=TestGapCategory.UNTESTED_PERSONA_GOAL,
                            target=f"{persona.id} (partial)",
                            severity="medium",
                            suggestion=f"Only {covered_goals}/{len(persona.goals)} goals covered for {persona.id}",
                        )
                    )

        # Check for untested state transitions
        for entity in app_spec.domain.entities:
            if entity.state_machine:
                sm = entity.state_machine
                for transition in sm.transitions:
                    # Check if deterministic tests cover this
                    flow_id = (
                        f"{entity.name}_transition_{transition.from_state}_to_{transition.to_state}"
                    )
                    if not any(f.id == flow_id for f in testspec.flows):
                        gaps.append(
                            TestGap(
                                category=TestGapCategory.UNTESTED_STATE_TRANSITION,
                                target=f"{entity.name}: {transition.from_state} -> {transition.to_state}",
                                severity="medium",
                                suggestion=f"State transition test missing for {entity.name}",
                                related_entities=[entity.name],
                            )
                        )

        # Check for untested surfaces
        tested_surfaces: set[str] = set()
        for design in existing_designs:
            tested_surfaces.update(design.surfaces)
        for flow in testspec.flows:
            # Extract surfaces from flow targets
            for step in flow.steps:
                if step.target and step.target.startswith("view:"):
                    tested_surfaces.add(step.target.split(":", 1)[1])

        for surface in app_spec.surfaces:
            if surface.name not in tested_surfaces:
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_SURFACE,
                        target=surface.name,
                        severity="low",
                        suggestion=f"Add navigation test for {surface.title or surface.name}",
                    )
                )

        # Check for untested scenarios
        for scenario in app_spec.scenarios:
            # Check if any test design references this scenario
            if not any(d.scenario == scenario.name for d in existing_designs):
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_SCENARIO,
                        target=scenario.name,
                        severity="medium",
                        suggestion=f"DSL scenario '{scenario.name}' has no corresponding test design",
                    )
                )

        # Calculate coverage score
        total_items = (
            len(all_entities)
            + len(app_spec.personas)
            + len(app_spec.surfaces)
            + len(app_spec.scenarios)
        )
        covered_items = (
            len(all_entities - untested_entities)
            + len(existing_personas)
            + len(tested_surfaces)
            + len(
                [
                    s
                    for s in app_spec.scenarios
                    if any(d.scenario == s.name for d in existing_designs)
                ]
            )
        )

        coverage_score = (covered_items / total_items * 100) if total_items > 0 else 100.0

        analysis = TestGapAnalysis(
            project_name=app_spec.name,
            total_entities=len(all_entities),
            total_surfaces=len(app_spec.surfaces),
            total_personas=len(app_spec.personas),
            total_scenarios=len(app_spec.scenarios),
            gaps=gaps,
            coverage_score=round(coverage_score, 1),
        )

        return json.dumps(
            {
                "project": analysis.project_name,
                "coverage_score": analysis.coverage_score,
                "totals": {
                    "entities": analysis.total_entities,
                    "surfaces": analysis.total_surfaces,
                    "personas": analysis.total_personas,
                    "scenarios": analysis.total_scenarios,
                },
                "gap_count": len(gaps),
                "gaps_by_severity": {
                    "high": len([g for g in gaps if g.severity == "high"]),
                    "medium": len([g for g in gaps if g.severity == "medium"]),
                    "low": len([g for g in gaps if g.severity == "low"]),
                },
                "gaps_by_category": analysis.gap_count_by_category,
                "gaps": [
                    {
                        "category": g.category.value,
                        "target": g.target,
                        "severity": g.severity,
                        "suggestion": g.suggestion,
                    }
                    for g in gaps
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save test designs to dsl/tests/designs.json."""
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.testing.test_design_persistence import add_test_designs, get_dsl_tests_dir

    designs_data = args.get("designs", [])
    overwrite = args.get("overwrite", False)

    if not designs_data:
        return json.dumps({"error": "No designs provided"})

    try:
        # Convert dict data to TestDesignSpec objects
        designs: list[TestDesignSpec] = []
        for d in designs_data:
            steps = []
            for s in d.get("steps", []):
                steps.append(
                    TestDesignStep(
                        action=_parse_test_design_action(s["action"])
                        if s.get("action")
                        else TestDesignAction.CLICK,
                        target=s.get("target", ""),
                        data=s.get("data"),
                        rationale=s.get("rationale"),
                    )
                )

            designs.append(
                TestDesignSpec(
                    test_id=d["test_id"],
                    title=d["title"],
                    description=d.get("description"),
                    persona=d.get("persona"),
                    scenario=d.get("scenario"),
                    trigger=_parse_test_design_trigger(d["trigger"])
                    if d.get("trigger")
                    else TestDesignTrigger.USER_CLICK,
                    steps=steps,
                    expected_outcomes=d.get("expected_outcomes", []),
                    entities=d.get("entities", []),
                    surfaces=d.get("surfaces", []),
                    tags=d.get("tags", []),
                    status=TestDesignStatus(d.get("status", "proposed")),
                    notes=d.get("notes"),
                )
            )

        # Save designs
        result = add_test_designs(project_root, designs, overwrite=overwrite, to_dsl=True)
        designs_file = get_dsl_tests_dir(project_root) / "designs.json"

        response: dict[str, Any] = {
            "status": "saved",
            "saved_count": result.added_count,
            "total_count": len(result.all_designs),
            "file": str(designs_file),
            "overwrite": overwrite,
        }

        if result.remapped_ids:
            response["remapped_ids"] = result.remapped_ids
            response["warning"] = (
                f"{len(result.remapped_ids)} design(s) had colliding IDs and were "
                "auto-assigned new unique IDs. See remapped_ids for details."
            )

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve test designs from storage.

    Returns compact summaries by default. When ``test_ids`` is provided,
    returns full content for those specific designs only.
    """
    from dazzle.core.ir.test_design import TestDesignStatus
    from dazzle.testing.test_design_persistence import (
        get_dsl_tests_dir,
        get_test_designs_by_status,
    )

    status_filter = args.get("status_filter")
    test_ids = args.get("test_ids")

    try:
        status = (
            TestDesignStatus(status_filter) if status_filter and status_filter != "all" else None
        )
        designs = get_test_designs_by_status(project_root, status)
        designs_file = get_dsl_tests_dir(project_root) / "designs.json"

        if test_ids:
            # Return full content for requested designs only
            filtered = [d for d in designs if d.test_id in test_ids]
            return json.dumps(
                {
                    "count": len(filtered),
                    "filter": status_filter or "all",
                    "file": str(designs_file) if designs_file.exists() else None,
                    "designs": [
                        {
                            "test_id": d.test_id,
                            "title": d.title,
                            "description": d.description,
                            "persona": d.persona,
                            "scenario": d.scenario,
                            "trigger": d.trigger.value,
                            "steps": [
                                {
                                    "action": s.action.value,
                                    "target": s.target,
                                    "data": s.data,
                                    "rationale": s.rationale,
                                }
                                for s in d.steps
                            ],
                            "expected_outcomes": d.expected_outcomes,
                            "entities": d.entities,
                            "surfaces": d.surfaces,
                            "tags": d.tags,
                            "status": d.status.value,
                            "implementation_path": d.implementation_path,
                            "notes": d.notes,
                        }
                        for d in filtered
                    ],
                },
                indent=2,
            )

        # Default: return compact summaries
        return json.dumps(
            {
                "count": len(designs),
                "filter": status_filter or "all",
                "file": str(designs_file) if designs_file.exists() else None,
                "designs": [
                    {
                        "test_id": d.test_id,
                        "title": d.title,
                        "persona": d.persona,
                        "status": d.status.value,
                    }
                    for d in designs
                ],
                "guidance": "Use test_design(operation='get', test_ids=['TD-001']) to fetch full details.",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_coverage_actions_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Get prioritized actions to increase test coverage.

    Returns actionable prompts an LLM can execute directly.
    """
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    max_actions = args.get("max_actions", 5)
    focus = args.get("focus", "all")

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Load existing test designs and testspec
        existing_designs = load_test_designs(project_root)
        testspec = generate_e2e_testspec(app_spec)

        # Track what's covered
        covered_personas: set[str] = set()
        covered_entities: set[str] = set()
        covered_scenarios: set[str] = set()

        for design in existing_designs:
            if design.persona:
                covered_personas.add(design.persona)
            covered_entities.update(design.entities)
            if design.scenario:
                covered_scenarios.add(design.scenario)

        # Calculate coverage
        all_entities = {e.name for e in app_spec.domain.entities}
        all_personas = {p.id for p in app_spec.personas}
        all_scenarios = {s.name for s in app_spec.scenarios}

        # Build prioritized actions
        actions: list[dict[str, Any]] = []

        # Priority 1: Untested personas with goals (highest impact)
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

        # Priority 2: Entities with state machines (complex behavior)
        if focus in ("all", "state_machines", "entities"):
            for entity in app_spec.domain.entities:
                if entity.state_machine and entity.name not in covered_entities:
                    sm = entity.state_machine
                    transitions = [f"{t.from_state} → {t.to_state}" for t in sm.transitions]
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

        # Priority 3: Untested scenarios (user workflows)
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

        # Priority 4: Entities with access control (security)
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

        # Priority 5: Basic entity coverage
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

        # Sort by priority and limit
        actions.sort(key=lambda x: x["priority"])
        actions = actions[:max_actions]

        # Calculate coverage score
        total_items = len(all_entities) + len(all_personas) + len(all_scenarios)
        covered_items = len(covered_entities) + len(covered_personas) + len(covered_scenarios)
        coverage_score = (covered_items / total_items * 100) if total_items > 0 else 100.0

        # Build summary
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

        # Build response with guidance
        return json.dumps(
            {
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
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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


def get_runtime_coverage_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze runtime UX coverage report to find gaps and generate tests.

    This reads the actual runtime coverage from test execution and identifies
    specific gaps that need test coverage.
    """
    max_actions = args.get("max_actions", 5)
    coverage_path = args.get("coverage_report_path")

    # Find coverage report
    if coverage_path:
        report_path = Path(coverage_path)
    else:
        # Default locations
        candidates = [
            project_root / "dsl" / "tests" / "runtime_coverage.json",
            project_root / ".dazzle" / "test_results" / "ux_coverage.json",
        ]
        report_path = None
        for candidate in candidates:
            if candidate.exists():
                report_path = candidate
                break

    if not report_path or not report_path.exists():
        return json.dumps(
            {
                "error": "No runtime coverage report found",
                "hint": (
                    "Run the E2E tests to generate a coverage report, then save it with "
                    "save_runtime_coverage or provide a path with coverage_report_path"
                ),
                "searched_paths": [str(c) for c in candidates]
                if not coverage_path
                else [str(coverage_path)],
            },
            indent=2,
        )

    try:
        # Load coverage report
        with open(report_path) as f:
            coverage = json.load(f)

        # Extract gaps
        actions: list[dict[str, Any]] = []

        # Gap 1: Missing CRUD operations per entity
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

            # Missing UI views
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
                                "expected_outcomes": [
                                    f"{view.capitalize()} view renders correctly"
                                ],
                                "entities": [entity_name],
                                "tags": ["ui_view", "runtime_gap", "automated"],
                                "status": "accepted",
                            },
                        }
                    )

        # Gap 2: Missing routes
        routes_data = coverage.get("routes", {})
        if isinstance(routes_data, dict):
            total_routes = routes_data.get("total", 0)
            visited_routes = routes_data.get("visited", 0)
            if total_routes > visited_routes:
                # We don't have specific route names, suggest general navigation test
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

        # Sort by priority and limit
        actions.sort(key=lambda x: x["priority"])
        actions = actions[:max_actions]

        # Build summary
        overall = coverage.get("overall_coverage", 0)
        summary = {
            "runtime_coverage": round(overall, 1),
            "route_coverage": coverage.get("route_coverage", 0),
            "crud_coverage": coverage.get("entity_crud_coverage", 0),
            "ui_coverage": coverage.get("entity_ui_coverage", 0),
            "gaps_found": len(actions),
            "report_path": str(report_path),
        }

        # Extract test designs for direct saving
        test_designs = [a["test_design"] for a in actions if "test_design" in a]

        return json.dumps(
            {
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
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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


def save_runtime_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save runtime coverage report to dsl/tests/ for future analysis."""
    coverage_data = args.get("coverage_data")

    if not coverage_data:
        return json.dumps({"error": "coverage_data is required"}, indent=2)

    # Save to dsl/tests/runtime_coverage.json
    tests_dir = project_root / "dsl" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    output_path = tests_dir / "runtime_coverage.json"
    with open(output_path, "w") as f:
        json.dump(coverage_data, f, indent=2)

    return json.dumps(
        {
            "success": True,
            "path": str(output_path),
            "message": "Runtime coverage saved. Use get_runtime_coverage_gaps to analyze gaps.",
        },
        indent=2,
    )
