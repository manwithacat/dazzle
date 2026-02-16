"""Test gap analysis handler."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..common import extract_progress, load_project_appspec, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


@wrap_handler_errors
def get_test_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze coverage and suggest what's missing.

    Returns untested entities, persona goals, state transitions, and suggested test designs.
    """
    from dazzle.core.ir.test_design import TestGap, TestGapAnalysis, TestGapCategory
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    progress = extract_progress(args)

    progress.log_sync("Analyzing test gaps...")
    app_spec = load_project_appspec(project_root)

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
    progress.log_sync("Checking entity coverage...")
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
    progress.log_sync("Checking persona coverage...")
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
                    goal.lower() in (d.title.lower() if d.title else "") for d in persona_designs
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
    progress.log_sync("Checking surface coverage...")
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
            [s for s in app_spec.scenarios if any(d.scenario == s.name for d in existing_designs)]
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
