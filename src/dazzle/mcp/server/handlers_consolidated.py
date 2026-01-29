"""
Consolidated tool handlers.

This module provides dispatch functions for consolidated tools.
Each handler routes the 'operation' parameter to existing handler functions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import get_available_projects, get_project_root, is_dev_mode, resolve_project_path


def _resolve_project(arguments: dict[str, Any]) -> Path | None:
    """Resolve project path from arguments or state."""
    # Check for pre-resolved path (set by dispatch_consolidated_tool via roots)
    pre_resolved = arguments.get("_resolved_project_path")
    if isinstance(pre_resolved, Path):
        return pre_resolved

    explicit_path = arguments.get("project_path")
    try:
        return resolve_project_path(explicit_path)
    except ValueError:
        return None


def _project_error() -> str:
    """Generate project not found error message."""
    if is_dev_mode():
        return json.dumps(
            {
                "error": "No project selected. Use 'select_project' to choose one, or pass 'project_path' directly.",
                "available_projects": list(get_available_projects().keys()),
            }
        )
    else:
        return json.dumps(
            {
                "error": "No dazzle.toml found in project root",
                "project_root": str(get_project_root()),
            }
        )


# =============================================================================
# DSL Operations Handler
# =============================================================================


def handle_dsl(arguments: dict[str, Any]) -> str:
    """Handle consolidated DSL operations."""
    from .handlers.dsl import (
        analyze_patterns,
        inspect_entity,
        inspect_surface,
        lint_project,
        list_modules,
        validate_dsl,
    )
    from .handlers.stories import get_dsl_spec_handler

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "validate":
        return validate_dsl(project_path)
    elif operation == "list_modules":
        return list_modules(project_path)
    elif operation == "inspect_entity":
        return inspect_entity(project_path, arguments)
    elif operation == "inspect_surface":
        return inspect_surface(project_path, arguments)
    elif operation == "analyze":
        return analyze_patterns(project_path)
    elif operation == "lint":
        return lint_project(project_path, arguments)
    elif operation == "get_spec":
        return get_dsl_spec_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown DSL operation: {operation}"})


# =============================================================================
# API Pack Handler
# =============================================================================


def handle_api_pack(arguments: dict[str, Any]) -> str:
    """Handle consolidated API pack operations."""
    from .handlers.api_packs import (
        generate_service_dsl_handler,
        get_api_pack_handler,
        get_env_vars_for_packs_handler,
        list_api_packs_handler,
        search_api_packs_handler,
    )

    operation = arguments.get("operation")

    if operation == "list":
        return list_api_packs_handler(arguments)
    elif operation == "search":
        return search_api_packs_handler(arguments)
    elif operation == "get":
        return get_api_pack_handler(arguments)
    elif operation == "generate_dsl":
        return generate_service_dsl_handler(arguments)
    elif operation == "env_vars":
        return get_env_vars_for_packs_handler(arguments)
    else:
        return json.dumps({"error": f"Unknown API pack operation: {operation}"})


# =============================================================================
# Story Handler
# =============================================================================


def handle_story(arguments: dict[str, Any]) -> str:
    """Handle consolidated story operations."""
    from .handlers.process import stories_coverage_handler
    from .handlers.stories import (
        generate_story_stubs_handler,
        generate_tests_from_stories_handler,
        get_stories_handler,
        propose_stories_from_dsl_handler,
        save_stories_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "propose":
        return propose_stories_from_dsl_handler(project_path, arguments)
    elif operation == "save":
        return save_stories_handler(project_path, arguments)
    elif operation == "get":
        return get_stories_handler(project_path, arguments)
    elif operation == "generate_stubs":
        return generate_story_stubs_handler(project_path, arguments)
    elif operation == "generate_tests":
        return generate_tests_from_stories_handler(project_path, arguments)
    elif operation == "coverage":
        return stories_coverage_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown story operation: {operation}"})


# =============================================================================
# Demo Data Handler
# =============================================================================


def handle_demo_data(arguments: dict[str, Any]) -> str:
    """Handle consolidated demo data operations."""
    from .tool_handlers import (
        generate_demo_data_handler,
        get_demo_blueprint_handler,
        propose_demo_blueprint_handler,
        save_demo_blueprint_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "propose":
        return propose_demo_blueprint_handler(project_path, arguments)
    elif operation == "save":
        return save_demo_blueprint_handler(project_path, arguments)
    elif operation == "get":
        return get_demo_blueprint_handler(project_path, arguments)
    elif operation == "generate":
        return generate_demo_data_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown demo data operation: {operation}"})


# =============================================================================
# Test Design Handler
# =============================================================================


def handle_test_design(arguments: dict[str, Any]) -> str:
    """Handle consolidated test design operations."""
    from .tool_handlers import (
        get_coverage_actions_handler,
        get_runtime_coverage_gaps_handler,
        get_test_designs_handler,
        get_test_gaps_handler,
        propose_persona_tests_handler,
        save_runtime_coverage_handler,
        save_test_designs_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "propose_persona":
        return propose_persona_tests_handler(project_path, arguments)
    elif operation == "gaps":
        return get_test_gaps_handler(project_path, arguments)
    elif operation == "save":
        return save_test_designs_handler(project_path, arguments)
    elif operation == "get":
        return get_test_designs_handler(project_path, arguments)
    elif operation == "coverage_actions":
        return get_coverage_actions_handler(project_path, arguments)
    elif operation == "runtime_gaps":
        return get_runtime_coverage_gaps_handler(project_path, arguments)
    elif operation == "save_runtime":
        return save_runtime_coverage_handler(project_path, arguments)
    elif operation == "auto_populate":
        return _auto_populate_tests(project_path, arguments)
    elif operation == "improve_coverage":
        return _improve_coverage(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown test design operation: {operation}"})


# =============================================================================
# SiteSpec Handler
# =============================================================================


def handle_sitespec(arguments: dict[str, Any]) -> str:
    """Handle consolidated sitespec operations."""
    from .tool_handlers import (
        get_sitespec_handler,
        scaffold_site_handler,
        validate_sitespec_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "get":
        return get_sitespec_handler(project_path, arguments)
    elif operation == "validate":
        return validate_sitespec_handler(project_path, arguments)
    elif operation == "scaffold":
        return scaffold_site_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown sitespec operation: {operation}"})


# =============================================================================
# Semantics Handler
# =============================================================================


def handle_semantics(arguments: dict[str, Any]) -> str:
    """Handle consolidated semantics operations."""
    from dazzle.mcp.event_first_tools import (
        handle_extract_semantics,
        handle_infer_analytics,
        handle_infer_compliance,
        handle_infer_tenancy,
        handle_validate_events,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "extract":
        return handle_extract_semantics(arguments, project_path)
    elif operation == "validate_events":
        return handle_validate_events(arguments, project_path)
    elif operation == "tenancy":
        return handle_infer_tenancy(arguments, project_path)
    elif operation == "compliance":
        return handle_infer_compliance(arguments, project_path)
    elif operation == "analytics":
        return handle_infer_analytics(arguments, project_path)
    else:
        return json.dumps({"error": f"Unknown semantics operation: {operation}"})


# =============================================================================
# Feedback Handler
# =============================================================================


def handle_feedback(arguments: dict[str, Any]) -> str:
    """Handle consolidated feedback operations."""
    from dazzle.mcp.event_first_tools import (
        handle_add_feedback,
        handle_list_feedback,
    )

    operation = arguments.get("operation")
    project_root = get_project_root()

    if operation == "add":
        return handle_add_feedback(arguments, project_root)
    elif operation == "list":
        return handle_list_feedback(arguments, project_root)
    else:
        return json.dumps({"error": f"Unknown feedback operation: {operation}"})


# =============================================================================
# Process Handler
# =============================================================================


def handle_process(arguments: dict[str, Any]) -> str:
    """Handle consolidated process operations."""
    from .handlers.process import (
        get_process_diagram_handler,
        get_process_run_handler,
        inspect_process_handler,
        list_process_runs_handler,
        list_processes_handler,
        propose_processes_handler,
        stories_coverage_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "propose":
        return propose_processes_handler(project_path, arguments)
    elif operation == "list":
        return list_processes_handler(project_path, arguments)
    elif operation == "inspect":
        return inspect_process_handler(project_path, arguments)
    elif operation == "list_runs":
        return list_process_runs_handler(project_path, arguments)
    elif operation == "get_run":
        return get_process_run_handler(project_path, arguments)
    elif operation == "diagram":
        return get_process_diagram_handler(project_path, arguments)
    elif operation == "coverage":
        return stories_coverage_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown process operation: {operation}"})


# =============================================================================
# DSL Test Handler
# =============================================================================


def handle_dsl_test(arguments: dict[str, Any]) -> str:
    """Handle consolidated DSL test operations."""
    from .tool_handlers import (
        generate_dsl_tests_handler,
        get_dsl_test_coverage_handler,
        list_dsl_tests_handler,
        run_dsl_tests_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "generate":
        return generate_dsl_tests_handler(project_path, arguments)
    elif operation == "run":
        return run_dsl_tests_handler(project_path, arguments)
    elif operation == "coverage":
        return get_dsl_test_coverage_handler(project_path, arguments)
    elif operation == "list":
        return list_dsl_tests_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown DSL test operation: {operation}"})


# =============================================================================
# E2E Test Handler
# =============================================================================


def handle_e2e_test(arguments: dict[str, Any]) -> str:
    """Handle consolidated E2E test operations."""
    from .handlers.testing import (
        check_test_infrastructure_handler,
        get_e2e_test_coverage_handler,
        get_test_tier_guidance_handler,
        list_e2e_flows_handler,
        run_agent_e2e_tests_handler,
        run_e2e_tests_handler,
    )

    operation = arguments.get("operation")

    # check_infra and tier_guidance don't need project context
    if operation == "check_infra":
        return check_test_infrastructure_handler()
    elif operation == "tier_guidance":
        return get_test_tier_guidance_handler(arguments)

    # Other operations need project context
    project_path = _resolve_project(arguments)
    if project_path is None:
        return _project_error()

    if operation == "run":
        return run_e2e_tests_handler(
            project_path=str(project_path),
            priority=arguments.get("priority"),
            tag=arguments.get("tag"),
            headless=arguments.get("headless", True),
        )
    elif operation == "run_agent":
        return run_agent_e2e_tests_handler(
            project_path=str(project_path),
            test_id=arguments.get("test_id"),
            headless=arguments.get("headless", True),
            model=arguments.get("model"),
        )
    elif operation == "coverage":
        return get_e2e_test_coverage_handler(project_path=str(project_path))
    elif operation == "list_flows":
        return list_e2e_flows_handler(
            project_path=str(project_path),
            priority=arguments.get("priority"),
            tag=arguments.get("tag"),
            limit=arguments.get("limit", 20),
        )
    else:
        return json.dumps({"error": f"Unknown E2E test operation: {operation}"})


# =============================================================================
# Status Handler
# =============================================================================


def handle_status(arguments: dict[str, Any]) -> str:
    """Handle consolidated status operations."""
    from .handlers.project import get_active_project_info
    from .handlers.status import (
        get_dnr_logs_handler,
        get_mcp_status_handler,
    )

    operation = arguments.get("operation")

    if operation == "mcp":
        return get_mcp_status_handler(arguments)
    elif operation == "logs":
        return get_dnr_logs_handler(arguments)
    elif operation == "active_project":
        resolved = arguments.get("_resolved_project_path")
        return get_active_project_info(resolved_path=resolved)
    else:
        return json.dumps({"error": f"Unknown status operation: {operation}"})


# =============================================================================
# Knowledge Handler
# =============================================================================


def handle_knowledge(arguments: dict[str, Any]) -> str:
    """Handle consolidated knowledge operations."""
    from .handlers.knowledge import (
        get_cli_help_handler,
        get_workflow_guide_handler,
        lookup_concept_handler,
        lookup_inference_handler,
    )
    from .tool_handlers import find_examples_handler

    operation = arguments.get("operation")

    if operation == "concept":
        return lookup_concept_handler(arguments)
    elif operation == "examples":
        return find_examples_handler(arguments)
    elif operation == "cli_help":
        return get_cli_help_handler(arguments)
    elif operation == "workflow":
        return get_workflow_guide_handler(arguments)
    elif operation == "inference":
        return lookup_inference_handler(arguments)
    elif operation == "get_spec":
        project_path = _resolve_project(arguments)
        if project_path is None:
            return _project_error()
        from .tool_handlers import get_product_spec_handler

        return get_product_spec_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown knowledge operation: {operation}"})


# =============================================================================
# User Feedback Handler (Dazzle Bar)
# =============================================================================


async def handle_user_feedback(arguments: dict[str, Any]) -> str:
    """Handle consolidated user feedback operations (async)."""
    from .handlers.feedback import (
        get_feedback_handler,
        get_feedback_summary_handler,
        list_feedback_handler,
        update_feedback_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    pp = str(project_path)

    if operation == "list":
        return json.dumps(
            await list_feedback_handler(
                status=arguments.get("status"),
                category=arguments.get("category"),
                limit=arguments.get("limit", 20),
                project_path=pp,
            )
        )
    elif operation == "get":
        feedback_id = arguments.get("feedback_id")
        if not feedback_id:
            return json.dumps({"error": "feedback_id is required"})
        return json.dumps(await get_feedback_handler(feedback_id=feedback_id, project_path=pp))
    elif operation == "update":
        feedback_id = arguments.get("feedback_id")
        status = arguments.get("status")
        if not feedback_id or not status:
            return json.dumps({"error": "feedback_id and status are required"})
        return json.dumps(
            await update_feedback_handler(
                feedback_id=feedback_id,
                status=status,
                notes=arguments.get("notes"),
                project_path=pp,
            )
        )
    elif operation == "summary":
        return json.dumps(await get_feedback_summary_handler(project_path=pp))
    else:
        return json.dumps({"error": f"Unknown user feedback operation: {operation}"})


# =============================================================================
# Helper Functions for Enhanced Operations
# =============================================================================


def _auto_populate_tests(project_path: Path, arguments: dict[str, Any]) -> str:
    """
    Auto-populate stories and test designs from DSL.

    This operation runs the full autonomous workflow:
    1. Propose stories from DSL entities
    2. Auto-accept all proposed stories
    3. Generate test designs from accepted stories
    4. Save everything to dsl/stories/ and dsl/tests/

    Args:
        project_path: Path to the project directory
        arguments: dict with optional keys:
            - max_stories: Maximum stories to propose (default: 30)
            - include_test_designs: Whether to generate test designs (default: True)

    Returns:
        JSON string with summary of what was created
    """
    from datetime import UTC, datetime

    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules
    from dazzle.core.stories_persistence import add_stories, get_next_story_id
    from dazzle.testing.test_design_persistence import add_test_designs

    max_stories = arguments.get("max_stories", 30)
    include_test_designs = arguments.get("include_test_designs", True)

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"})

    # Get starting story ID
    base_id = get_next_story_id(project_path)
    base_num = int(base_id[3:])
    story_count = 0

    def next_story_id() -> str:
        nonlocal story_count
        result = f"ST-{base_num + story_count:03d}"
        story_count += 1
        return result

    now = datetime.now(UTC).isoformat()
    default_actor = "User"
    if appspec.personas:
        default_actor = appspec.personas[0].label or appspec.personas[0].id

    stories: list[StorySpec] = []

    # Generate stories from entities
    for entity in appspec.domain.entities:
        if story_count >= max_stories:
            break

        # Create story
        stories.append(
            StorySpec(
                story_id=next_story_id(),
                title=f"{default_actor} creates a new {entity.title or entity.name}",
                actor=default_actor,
                trigger=StoryTrigger.FORM_SUBMITTED,
                scope=[entity.name],
                preconditions=[f"{default_actor} has permission to create {entity.name}"],
                happy_path_outcome=[
                    f"New {entity.name} is saved to database",
                    f"{default_actor} sees confirmation message",
                ],
                side_effects=[],
                constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][:3],
                variants=["Validation error on required field"],
                status=StoryStatus.ACCEPTED,
                created_at=now,
                accepted_at=now,
            )
        )

        # State machine transitions
        if entity.state_machine:
            for transition in entity.state_machine.transitions[:3]:
                if story_count >= max_stories:
                    break
                sm = entity.state_machine
                stories.append(
                    StorySpec(
                        story_id=next_story_id(),
                        title=f"{default_actor} changes {entity.name} from {transition.from_state} to {transition.to_state}",
                        actor=default_actor,
                        trigger=StoryTrigger.STATUS_CHANGED,
                        scope=[entity.name],
                        preconditions=[
                            f"{entity.name}.{sm.status_field} is '{transition.from_state}'"
                        ],
                        happy_path_outcome=[
                            f"{entity.name}.{sm.status_field} becomes '{transition.to_state}'",
                        ],
                        side_effects=[],
                        constraints=[],
                        variants=[],
                        status=StoryStatus.ACCEPTED,
                        created_at=now,
                        accepted_at=now,
                    )
                )

    # Save stories
    all_stories = add_stories(project_path, stories, overwrite=False)

    result: dict[str, Any] = {
        "stories_proposed": len(stories),
        "stories_total": len(all_stories),
        "status": "success",
    }

    # Generate test designs from stories
    if include_test_designs and stories:
        trigger_map = {
            StoryTrigger.FORM_SUBMITTED: TestDesignTrigger.FORM_SUBMITTED,
            StoryTrigger.STATUS_CHANGED: TestDesignTrigger.STATUS_CHANGED,
            StoryTrigger.USER_CLICK: TestDesignTrigger.USER_CLICK,
        }

        test_designs: list[TestDesignSpec] = []

        for story in stories:
            test_id = story.story_id.replace("ST-", "TD-")

            steps: list[TestDesignStep] = [
                TestDesignStep(
                    action=TestDesignAction.LOGIN_AS,
                    target=story.actor,
                    rationale=f"Test from {story.actor}'s perspective",
                )
            ]

            if story.trigger == StoryTrigger.FORM_SUBMITTED:
                scope_entity = story.scope[0] if story.scope else "form"
                steps.extend(
                    [
                        TestDesignStep(
                            action=TestDesignAction.NAVIGATE_TO,
                            target=f"{scope_entity}_create",
                            rationale="Navigate to creation form",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.FILL,
                            target="form",
                            data={"fields": "required_fields"},
                            rationale="Fill form with test data",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.CLICK,
                            target="submit_button",
                            rationale="Submit the form",
                        ),
                    ]
                )
            elif story.trigger == StoryTrigger.STATUS_CHANGED:
                scope_entity = story.scope[0] if story.scope else "entity"
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.TRIGGER_TRANSITION,
                        target=scope_entity,
                        rationale="Trigger status change",
                    )
                )

            test_designs.append(
                TestDesignSpec(
                    test_id=test_id,
                    title=f"Verify: {story.title}",
                    description=f"Test generated from story {story.story_id}",
                    persona=story.actor,
                    trigger=trigger_map.get(story.trigger, TestDesignTrigger.USER_CLICK),
                    steps=steps,
                    expected_outcomes=story.happy_path_outcome.copy(),
                    entities=story.scope.copy(),
                    tags=[f"story:{story.story_id}", "auto-populated"],
                    status=TestDesignStatus.PROPOSED,
                )
            )

        add_test_designs(project_path, test_designs, overwrite=False, to_dsl=True)
        result["test_designs_generated"] = len(test_designs)

    result["next_steps"] = [
        "dazzle test dsl-run    # Run Tier 1 API tests",
        "dazzle test run-all    # Run all test tiers",
    ]

    return json.dumps(result, indent=2)


def _improve_coverage(project_path: Path, arguments: dict[str, Any]) -> str:
    """
    Execute top coverage improvement actions automatically.

    This operation:
    1. Gets prioritized coverage actions
    2. Executes the top N actions automatically
    3. Returns a summary of what was done

    Args:
        project_path: Path to the project directory
        arguments: dict with optional keys:
            - max_actions: Maximum actions to execute (default: 5)
            - focus: Focus area - "all", "personas", "entities", "scenarios" (default: "all")

    Returns:
        JSON string with summary of actions taken
    """
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules
    from dazzle.testing.test_design_persistence import add_test_designs, load_test_designs

    max_actions = arguments.get("max_actions", 5)
    focus = arguments.get("focus", "all")

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"})

    # Load existing test designs
    existing_designs = load_test_designs(project_path)

    # Track what's covered
    covered_personas: set[str] = set()
    covered_entities: set[str] = set()

    for design in existing_designs:
        if design.persona:
            covered_personas.add(design.persona)
        covered_entities.update(design.entities)

    # Find gaps
    all_entities = {e.name for e in appspec.domain.entities}
    all_personas = {p.id for p in appspec.personas}

    uncovered_entities = all_entities - covered_entities
    uncovered_personas = all_personas - covered_personas

    actions_taken: list[dict[str, Any]] = []
    new_designs: list[TestDesignSpec] = []
    next_id = len(existing_designs) + 1

    # Priority 1: Uncovered personas
    if focus in ("all", "personas"):
        for persona in appspec.personas:
            if len(actions_taken) >= max_actions:
                break
            if persona.id not in covered_personas and persona.goals:
                # Create a test design for this persona
                new_designs.append(
                    TestDesignSpec(
                        test_id=f"TD-{next_id:03d}",
                        title=f"Verify {persona.label or persona.id} can achieve their goals",
                        description=f"Auto-generated to cover persona {persona.id}",
                        persona=persona.id,
                        trigger=TestDesignTrigger.USER_CLICK,
                        steps=[
                            TestDesignStep(
                                action=TestDesignAction.LOGIN_AS,
                                target=persona.id,
                                rationale=f"Test as {persona.id}",
                            ),
                            TestDesignStep(
                                action=TestDesignAction.NAVIGATE_TO,
                                target="dashboard",
                                rationale="Navigate to main view",
                            ),
                        ],
                        expected_outcomes=[f"{persona.id} can access their workspace"],
                        entities=[],
                        tags=["auto-coverage", f"persona:{persona.id}"],
                        status=TestDesignStatus.PROPOSED,
                    )
                )
                next_id += 1
                actions_taken.append(
                    {
                        "action": "propose_persona_test",
                        "persona": persona.id,
                        "test_id": new_designs[-1].test_id,
                    }
                )

    # Priority 2: Uncovered entities
    if focus in ("all", "entities"):
        for entity in appspec.domain.entities:
            if len(actions_taken) >= max_actions:
                break
            if entity.name in uncovered_entities:
                new_designs.append(
                    TestDesignSpec(
                        test_id=f"TD-{next_id:03d}",
                        title=f"CRUD operations for {entity.title or entity.name}",
                        description=f"Auto-generated to cover entity {entity.name}",
                        persona="User",
                        trigger=TestDesignTrigger.FORM_SUBMITTED,
                        steps=[
                            TestDesignStep(
                                action=TestDesignAction.NAVIGATE_TO,
                                target=f"{entity.name}_create",
                                rationale="Navigate to creation form",
                            ),
                            TestDesignStep(
                                action=TestDesignAction.FILL,
                                target="form",
                                data={"fields": "required"},
                                rationale="Fill required fields",
                            ),
                            TestDesignStep(
                                action=TestDesignAction.CLICK,
                                target="submit",
                                rationale="Submit form",
                            ),
                        ],
                        expected_outcomes=[f"{entity.name} is created successfully"],
                        entities=[entity.name],
                        tags=["auto-coverage", f"entity:{entity.name}", "crud"],
                        status=TestDesignStatus.PROPOSED,
                    )
                )
                next_id += 1
                actions_taken.append(
                    {
                        "action": "propose_entity_test",
                        "entity": entity.name,
                        "test_id": new_designs[-1].test_id,
                    }
                )

    # Save new test designs
    if new_designs:
        add_test_designs(project_path, new_designs, overwrite=False, to_dsl=True)

    # Calculate new coverage
    new_entity_coverage = (
        (
            len(covered_entities)
            + len([a for a in actions_taken if a["action"] == "propose_entity_test"])
        )
        / len(all_entities)
        * 100
        if all_entities
        else 100
    )
    new_persona_coverage = (
        (
            len(covered_personas)
            + len([a for a in actions_taken if a["action"] == "propose_persona_test"])
        )
        / len(all_personas)
        * 100
        if all_personas
        else 100
    )

    return json.dumps(
        {
            "actions_taken": len(actions_taken),
            "actions": actions_taken,
            "test_designs_created": len(new_designs),
            "coverage": {
                "entities": f"{new_entity_coverage:.1f}%",
                "personas": f"{new_persona_coverage:.1f}%",
            },
            "gaps_remaining": {
                "entities": len(uncovered_entities)
                - len([a for a in actions_taken if a["action"] == "propose_entity_test"]),
                "personas": len(uncovered_personas)
                - len([a for a in actions_taken if a["action"] == "propose_persona_test"]),
            },
        },
        indent=2,
    )


# =============================================================================
# Pitch Handler
# =============================================================================


def handle_pitch(arguments: dict[str, Any]) -> str:
    """Handle consolidated pitch operations."""
    from .handlers.pitch import (
        enrich_pitchspec_handler,
        generate_pitch_handler,
        get_pitchspec_handler,
        init_assets_handler,
        review_pitchspec_handler,
        scaffold_pitchspec_handler,
        update_pitchspec_handler,
        validate_pitchspec_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    if operation == "scaffold":
        return scaffold_pitchspec_handler(project_path, arguments)
    elif operation == "generate":
        return generate_pitch_handler(project_path, arguments)
    elif operation == "validate":
        return validate_pitchspec_handler(project_path, arguments)
    elif operation == "get":
        return get_pitchspec_handler(project_path, arguments)
    elif operation == "review":
        return review_pitchspec_handler(project_path, arguments)
    elif operation == "update":
        return update_pitchspec_handler(project_path, arguments)
    elif operation == "enrich":
        return enrich_pitchspec_handler(project_path, arguments)
    elif operation == "init_assets":
        return init_assets_handler(project_path, arguments)
    else:
        return json.dumps({"error": f"Unknown pitch operation: {operation}"})


# =============================================================================
# Mailpit Handler (async)
# =============================================================================


async def handle_mailpit(arguments: dict[str, Any]) -> str:
    """Handle consolidated Mailpit operations (async)."""
    from .handlers.mailpit import handle_mailpit as _handle_mailpit

    return await _handle_mailpit(arguments)


# =============================================================================
# Contribution Handler
# =============================================================================


def handle_contribution(arguments: dict[str, Any]) -> str:
    """Handle consolidated contribution packaging operations."""
    from .handlers.contribution import (
        create_handler,
        examples_handler,
        templates_handler,
        validate_handler,
    )

    operation = arguments.get("operation")

    if operation == "templates":
        return templates_handler(arguments)
    elif operation == "create":
        return create_handler(arguments)
    elif operation == "validate":
        return validate_handler(arguments)
    elif operation == "examples":
        return examples_handler(arguments)
    else:
        return json.dumps({"error": f"Unknown contribution operation: {operation}"})


# =============================================================================
# Main Dispatcher
# =============================================================================

# Map of consolidated tool names to their handlers
CONSOLIDATED_TOOL_HANDLERS = {
    "dsl": handle_dsl,
    "api_pack": handle_api_pack,
    "story": handle_story,
    "demo_data": handle_demo_data,
    "test_design": handle_test_design,
    "sitespec": handle_sitespec,
    "semantics": handle_semantics,
    "feedback": handle_feedback,
    "process": handle_process,
    "dsl_test": handle_dsl_test,
    "e2e_test": handle_e2e_test,
    "status": handle_status,
    "knowledge": handle_knowledge,
    "pitch": handle_pitch,
    "mailpit": handle_mailpit,
    "contribution": handle_contribution,
    "user_feedback": handle_user_feedback,
}


async def dispatch_consolidated_tool(
    name: str,
    arguments: dict[str, Any],
    session: Any = None,
) -> str | None:
    """
    Dispatch a consolidated tool call.

    Returns the result string if the tool is a consolidated tool,
    or None if it's not (to allow fallback to original tools).

    Supports both sync and async handlers.

    Args:
        name: Tool name.
        arguments: Tool arguments.
        session: Optional MCP ServerSession for roots-based project resolution.
    """
    import inspect

    handler = CONSOLIDATED_TOOL_HANDLERS.get(name)
    if handler:
        # Pre-resolve project path from MCP roots if session available
        if session is not None and "_resolved_project_path" not in arguments:
            try:
                from .state import resolve_project_path_from_roots

                resolved = await resolve_project_path_from_roots(
                    session, arguments.get("project_path")
                )
                arguments = {**arguments, "_resolved_project_path": resolved}
            except Exception:
                pass  # Fall through to sync resolution

        if inspect.iscoroutinefunction(handler):
            result = await handler(arguments)
        else:
            result = handler(arguments)
        return str(result) if result is not None else None
    return None
