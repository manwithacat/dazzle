"""
Consolidated tool handlers.

This module provides dispatch functions for consolidated tools.
Each handler routes the 'operation' parameter to existing handler functions.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .state import get_available_projects, get_project_root, is_dev_mode, resolve_project_path

logger = logging.getLogger(__name__)


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


def _dispatch_project_ops(
    arguments: dict[str, Any],
    ops: dict[str, Callable[..., str]],
    tool_label: str,
) -> str:
    """Common pattern: resolve project, look up operation in dict, call handler(project_path, arguments)."""
    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)
    if project_path is None:
        return _project_error()
    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return json.dumps({"error": f"Unknown {tool_label} operation: {operation}"})
    return handler(project_path, arguments)


async def _dispatch_project_ops_async(
    arguments: dict[str, Any],
    ops: dict[str, Callable[..., Any]],
    tool_label: str,
) -> str:
    """Async variant of _dispatch_project_ops. All handlers are awaited."""
    import inspect

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)
    if project_path is None:
        return _project_error()
    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return json.dumps({"error": f"Unknown {tool_label} operation: {operation}"})
    result = handler(project_path, arguments)
    if inspect.isawaitable(result):
        rv: str = await result
        return rv
    return str(result)


def _dispatch_standalone_ops(
    arguments: dict[str, Any],
    ops: dict[str, Callable[..., str]],
    tool_label: str,
) -> str:
    """Dispatch for handlers that take only arguments (no project_path)."""
    operation = arguments.get("operation")
    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return json.dumps({"error": f"Unknown {tool_label} operation: {operation}"})
    return handler(arguments)


# =============================================================================
# DSL Operations Handler
# =============================================================================


def handle_dsl(arguments: dict[str, Any]) -> str:
    """Handle consolidated DSL operations."""
    from .handlers.dsl import (
        analyze_patterns,
        get_unified_issues,
        inspect_entity,
        inspect_surface,
        lint_project,
        list_modules,
        validate_dsl,
    )
    from .handlers.stories import get_dsl_spec_handler

    def _fidelity(project_path: Path, args: dict[str, Any]) -> str:
        from .handlers.fidelity import score_fidelity_handler

        return score_fidelity_handler(project_path, args)

    def _export_frontend_spec(project_path: Path, args: dict[str, Any]) -> str:
        from .handlers.dsl import export_frontend_spec_handler

        return export_frontend_spec_handler(project_path, args)

    def _list_fragments(project_path: Path, args: dict[str, Any]) -> str:
        from dazzle_ui.runtime.fragment_registry import get_fragment_registry

        return json.dumps({"fragments": get_fragment_registry()}, indent=2)

    ops: dict[str, Callable[..., str]] = {
        "validate": validate_dsl,
        "list_modules": list_modules,
        "inspect_entity": inspect_entity,
        "inspect_surface": inspect_surface,
        "analyze": analyze_patterns,
        "lint": lint_project,
        "issues": get_unified_issues,
        "get_spec": get_dsl_spec_handler,
        "fidelity": _fidelity,
        "export_frontend_spec": _export_frontend_spec,
        "list_fragments": _list_fragments,
    }

    return _dispatch_project_ops(arguments, ops, "DSL")


# =============================================================================
# API Pack Handler
# =============================================================================


def handle_api_pack(arguments: dict[str, Any]) -> str:
    """Handle consolidated API pack operations."""
    from .handlers.api_packs import (
        generate_service_dsl_handler,
        get_api_pack_handler,
        get_env_vars_for_packs_handler,
        infrastructure_handler,
        list_api_packs_handler,
        search_api_packs_handler,
    )

    standalone_ops: dict[str, Callable[..., str]] = {
        "list": list_api_packs_handler,
        "search": search_api_packs_handler,
        "get": get_api_pack_handler,
        "generate_dsl": generate_service_dsl_handler,
        "env_vars": get_env_vars_for_packs_handler,
    }

    operation = arguments.get("operation")

    # Most ops are standalone (no project_path)
    standalone = standalone_ops.get(operation)  # type: ignore[arg-type]
    if standalone is not None:
        return standalone(arguments)

    # infrastructure needs project context
    if operation == "infrastructure":
        project_path = _resolve_project(arguments)
        if project_path is None:
            return _project_error()
        return infrastructure_handler(project_path=project_path, args=arguments)

    return json.dumps({"error": f"Unknown API pack operation: {operation}"})


# =============================================================================
# Story Handler
# =============================================================================


def handle_story(arguments: dict[str, Any]) -> str:
    """Handle consolidated story operations."""
    from .handlers.process import stories_coverage_handler
    from .handlers.stories import (
        generate_tests_from_stories_handler,
        get_stories_handler,
        propose_stories_from_dsl_handler,
        save_stories_handler,
        wall_stories_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    # Special case: "get" with wall view
    if operation == "get" and arguments.get("view") == "wall":
        return wall_stories_handler(project_path, arguments)

    ops: dict[str, Callable[..., str]] = {
        "propose": propose_stories_from_dsl_handler,
        "save": save_stories_handler,
        "get": get_stories_handler,
        "generate_tests": generate_tests_from_stories_handler,
        "coverage": stories_coverage_handler,
    }

    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return json.dumps({"error": f"Unknown story operation: {operation}"})
    return handler(project_path, arguments)


# =============================================================================
# Demo Data Handler
# =============================================================================


def handle_demo_data(arguments: dict[str, Any]) -> str:
    """Handle consolidated demo data operations."""
    from .handlers.demo_data import (
        generate_demo_data_handler,
        get_demo_blueprint_handler,
        propose_demo_blueprint_handler,
        save_demo_blueprint_handler,
    )

    ops: dict[str, Callable[..., str]] = {
        "propose": propose_demo_blueprint_handler,
        "save": save_demo_blueprint_handler,
        "get": get_demo_blueprint_handler,
        "generate": generate_demo_data_handler,
    }

    return _dispatch_project_ops(arguments, ops, "demo data")


# =============================================================================
# Test Design Handler
# =============================================================================


def handle_test_design(arguments: dict[str, Any]) -> str:
    """Handle consolidated test design operations."""
    from .handlers.test_design import (
        get_coverage_actions_handler,
        get_runtime_coverage_gaps_handler,
        get_test_designs_handler,
        get_test_gaps_handler,
        propose_persona_tests_handler,
        save_runtime_coverage_handler,
        save_test_designs_handler,
    )

    ops: dict[str, Callable[..., str]] = {
        "propose_persona": propose_persona_tests_handler,
        "gaps": get_test_gaps_handler,
        "save": save_test_designs_handler,
        "get": get_test_designs_handler,
        "coverage_actions": get_coverage_actions_handler,
        "runtime_gaps": get_runtime_coverage_gaps_handler,
        "save_runtime": save_runtime_coverage_handler,
        "auto_populate": _auto_populate_tests,
        "improve_coverage": _improve_coverage,
    }

    return _dispatch_project_ops(arguments, ops, "test design")


# =============================================================================
# SiteSpec Handler
# =============================================================================


def handle_sitespec(arguments: dict[str, Any]) -> str:
    """Handle consolidated sitespec operations."""
    from .handlers.sitespec import (
        coherence_handler,
        generate_imagery_prompts_handler,
        generate_tokens_handler,
        get_copy_handler,
        get_sitespec_handler,
        get_theme_handler,
        review_copy_handler,
        review_sitespec_handler,
        scaffold_copy_handler,
        scaffold_site_handler,
        scaffold_theme_handler,
        validate_sitespec_handler,
        validate_theme_handler,
    )

    ops: dict[str, Callable[..., str]] = {
        "get": get_sitespec_handler,
        "validate": validate_sitespec_handler,
        "scaffold": scaffold_site_handler,
        "get_copy": get_copy_handler,
        "scaffold_copy": scaffold_copy_handler,
        "review_copy": review_copy_handler,
        "coherence": coherence_handler,
        "get_theme": get_theme_handler,
        "scaffold_theme": scaffold_theme_handler,
        "validate_theme": validate_theme_handler,
        "generate_tokens": generate_tokens_handler,
        "generate_imagery_prompts": generate_imagery_prompts_handler,
        "review": review_sitespec_handler,
    }

    return _dispatch_project_ops(arguments, ops, "sitespec")


# =============================================================================
# Semantics Handler
# =============================================================================


def handle_semantics(arguments: dict[str, Any]) -> str:
    """Handle consolidated semantics operations."""
    from dazzle.mcp.event_first_tools import (
        handle_extract_guards,
        handle_extract_semantics,
        handle_infer_analytics,
        handle_infer_compliance,
        handle_infer_tenancy,
        handle_validate_events,
    )

    # These handlers take (arguments, project_path) — reversed signature
    def _wrap(fn: Callable[..., str]) -> Callable[..., str]:
        def wrapper(project_path: Path, args: dict[str, Any]) -> str:
            return fn(args, project_path)

        return wrapper

    ops: dict[str, Callable[..., str]] = {
        "extract": _wrap(handle_extract_semantics),
        "validate_events": _wrap(handle_validate_events),
        "tenancy": _wrap(handle_infer_tenancy),
        "compliance": _wrap(handle_infer_compliance),
        "analytics": _wrap(handle_infer_analytics),
        "extract_guards": _wrap(handle_extract_guards),
    }

    return _dispatch_project_ops(arguments, ops, "semantics")


# =============================================================================
# Process Handler
# =============================================================================


async def handle_process(arguments: dict[str, Any]) -> str:
    """Handle consolidated process operations."""
    from .handlers.process import (
        get_process_diagram_handler,
        get_process_run_handler,
        inspect_process_handler,
        list_process_runs_handler,
        list_processes_handler,
        propose_processes_handler,
        save_processes_handler,
        stories_coverage_handler,
    )

    ops: dict[str, Callable[..., Any]] = {
        "propose": propose_processes_handler,
        "save": save_processes_handler,
        "list": list_processes_handler,
        "inspect": inspect_process_handler,
        "list_runs": list_process_runs_handler,
        "get_run": get_process_run_handler,
        "diagram": get_process_diagram_handler,
        "coverage": stories_coverage_handler,
    }

    return await _dispatch_project_ops_async(arguments, ops, "process")


# =============================================================================
# DSL Test Handler
# =============================================================================


async def handle_dsl_test(arguments: dict[str, Any]) -> str:
    """Handle consolidated DSL test operations."""
    from .handlers.dsl_test import (
        create_sessions_handler,
        diff_personas_handler,
        generate_dsl_tests_handler,
        get_dsl_test_coverage_handler,
        list_dsl_tests_handler,
        run_all_dsl_tests_handler,
        run_dsl_tests_handler,
        verify_story_handler,
    )

    ops: dict[str, Callable[..., Any]] = {
        "generate": generate_dsl_tests_handler,
        "run": run_dsl_tests_handler,
        "run_all": run_all_dsl_tests_handler,
        "coverage": get_dsl_test_coverage_handler,
        "list": list_dsl_tests_handler,
        "create_sessions": create_sessions_handler,
        "diff_personas": diff_personas_handler,
        "verify_story": verify_story_handler,
    }

    return await _dispatch_project_ops_async(arguments, ops, "DSL test")


# =============================================================================
# E2E Test Handler
# =============================================================================


async def handle_e2e_test(arguments: dict[str, Any]) -> str:
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
    standalone_ops: dict[str, Callable[..., Any]] = {
        "check_infra": lambda: check_test_infrastructure_handler(),
        "tier_guidance": lambda: get_test_tier_guidance_handler(arguments),
    }

    standalone = standalone_ops.get(operation)  # type: ignore[arg-type]
    if standalone is not None:
        return str(standalone())

    # Other operations need project context
    project_path = _resolve_project(arguments)
    if project_path is None:
        return _project_error()

    pp = str(project_path)

    if operation == "run":
        return run_e2e_tests_handler(
            project_path=pp,
            priority=arguments.get("priority"),
            tag=arguments.get("tag"),
            headless=arguments.get("headless", True),
        )
    elif operation == "run_agent":
        rv: str = await run_agent_e2e_tests_handler(
            project_path=pp,
            test_id=arguments.get("test_id"),
            headless=arguments.get("headless", True),
            model=arguments.get("model"),
        )
        return rv
    elif operation == "coverage":
        return get_e2e_test_coverage_handler(project_path=pp)
    elif operation == "list_flows":
        return list_e2e_flows_handler(
            project_path=pp,
            priority=arguments.get("priority"),
            tag=arguments.get("tag"),
            limit=arguments.get("limit", 20),
        )
    elif operation == "run_viewport":
        from .handlers.viewport_testing import run_viewport_tests_handler

        return run_viewport_tests_handler(
            project_path=pp,
            headless=arguments.get("headless", True),
            viewports=arguments.get("viewports"),
            persona_id=arguments.get("persona_id"),
            capture_screenshots=arguments.get("capture_screenshots", False),
            update_baselines=arguments.get("update_baselines", False),
        )
    elif operation in ("list_viewport_specs", "save_viewport_specs"):
        from .handlers.viewport_testing import manage_viewport_specs_handler

        return manage_viewport_specs_handler(
            project_path=pp,
            operation=operation,
            specs=arguments.get("viewport_specs"),
            to_dsl=arguments.get("to_dsl", True),
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
        get_activity_handler,
        get_dnr_logs_handler,
        get_mcp_status_handler,
        get_telemetry_handler,
    )

    operation = arguments.get("operation")

    # All status ops are standalone (no project_path)
    standalone_ops: dict[str, Callable[..., str]] = {
        "mcp": get_mcp_status_handler,
        "logs": get_dnr_logs_handler,
        "telemetry": get_telemetry_handler,
        "activity": get_activity_handler,
    }

    standalone = standalone_ops.get(operation)  # type: ignore[arg-type]
    if standalone is not None:
        return standalone(arguments)

    # active_project uses a different arg
    if operation == "active_project":
        resolved = arguments.get("_resolved_project_path")
        return get_active_project_info(resolved_path=resolved)

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

    standalone_ops: dict[str, Callable[..., str]] = {
        "concept": lookup_concept_handler,
        "examples": find_examples_handler,
        "cli_help": get_cli_help_handler,
        "workflow": get_workflow_guide_handler,
        "inference": lookup_inference_handler,
    }

    operation = arguments.get("operation")

    standalone = standalone_ops.get(operation)  # type: ignore[arg-type]
    if standalone is not None:
        return standalone(arguments)

    # get_spec needs project context
    if operation == "get_spec":
        project_path = _resolve_project(arguments)
        if project_path is None:
            return _project_error()
        from .tool_handlers import get_product_spec_handler

        return get_product_spec_handler(project_path, arguments)

    return json.dumps({"error": f"Unknown knowledge operation: {operation}"})


# =============================================================================
# User Management Handler
# =============================================================================


async def handle_user_management(arguments: dict[str, Any]) -> str:
    """Handle consolidated user management operations (async)."""
    from .handlers.user_management import (
        create_user_handler,
        deactivate_user_handler,
        get_auth_config_handler,
        get_user_handler,
        list_sessions_handler,
        list_users_handler,
        reset_password_handler,
        revoke_session_handler,
        update_user_handler,
    )
    from .progress import ProgressContext
    from .progress import noop as _noop_progress

    progress: ProgressContext = arguments.get("_progress") or _noop_progress()
    operation = arguments.get("operation")
    progress.log_sync(f"User management: {operation}...")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    pp = str(project_path)

    if operation == "list":
        return json.dumps(
            await list_users_handler(
                role=arguments.get("role"),
                active_only=arguments.get("active_only", True),
                limit=arguments.get("limit", 50),
                offset=arguments.get("offset", 0),
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "create":
        email = arguments.get("email")
        if not email:
            return json.dumps({"error": "email is required"})
        return json.dumps(
            await create_user_handler(
                email=email,
                name=arguments.get("name"),
                roles=arguments.get("roles"),
                is_superuser=arguments.get("is_superuser", False),
                password=arguments.get("password"),
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "get":
        user_id = arguments.get("user_id")
        email = arguments.get("email")
        if not user_id and not email:
            return json.dumps({"error": "user_id or email is required"})
        return json.dumps(
            await get_user_handler(
                user_id=user_id,
                email=email,
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "update":
        user_id = arguments.get("user_id")
        if not user_id:
            return json.dumps({"error": "user_id is required"})
        return json.dumps(
            await update_user_handler(
                user_id=user_id,
                username=arguments.get("username"),
                roles=arguments.get("roles"),
                is_active=arguments.get("is_active"),
                is_superuser=arguments.get("is_superuser"),
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "reset_password":
        user_id = arguments.get("user_id")
        if not user_id:
            return json.dumps({"error": "user_id is required"})
        return json.dumps(
            await reset_password_handler(
                user_id=user_id,
                password=arguments.get("password"),
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "deactivate":
        user_id = arguments.get("user_id")
        if not user_id:
            return json.dumps({"error": "user_id is required"})
        return json.dumps(
            await deactivate_user_handler(user_id=user_id, project_path=pp),
            indent=2,
        )
    elif operation == "list_sessions":
        return json.dumps(
            await list_sessions_handler(
                user_id=arguments.get("user_id"),
                active_only=arguments.get("active_only", True),
                limit=arguments.get("limit", 50),
                project_path=pp,
            ),
            indent=2,
        )
    elif operation == "revoke_session":
        session_id = arguments.get("session_id")
        if not session_id:
            return json.dumps({"error": "session_id is required"})
        return json.dumps(
            await revoke_session_handler(session_id=session_id, project_path=pp),
            indent=2,
        )
    elif operation == "config":
        return json.dumps(
            await get_auth_config_handler(project_path=pp),
            indent=2,
        )
    else:
        return json.dumps({"error": f"Unknown user_management operation: {operation}"})


# =============================================================================
# Helper Functions for Enhanced Operations
# =============================================================================


def _load_appspec(project_path: Path) -> Any:
    """Load and return appspec from project, or raise on failure."""
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    manifest = load_manifest(project_path / "dazzle.toml")
    dsl_files = discover_dsl_files(project_path, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def _generate_entity_stories(
    appspec: Any,
    max_stories: int,
    existing_titles: set[str],
    default_actor: str,
    now: str,
    next_story_id: Callable[[], str],
) -> tuple[list[Any], int]:
    """Generate stories from entities and their state machine transitions.

    Returns (new_stories, skipped_count).
    """
    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger

    stories: list[StorySpec] = []
    skipped = 0
    count = 0

    for entity in appspec.domain.entities:
        if count >= max_stories:
            break

        # Create story (skip if title already exists)
        title = f"{default_actor} creates a new {entity.title or entity.name}"
        if title in existing_titles:
            skipped += 1
        else:
            existing_titles.add(title)
            stories.append(
                StorySpec(
                    story_id=next_story_id(),
                    title=title,
                    actor=default_actor,
                    trigger=StoryTrigger.FORM_SUBMITTED,
                    scope=[entity.name],
                    preconditions=[f"{default_actor} has permission to create {entity.name}"],
                    happy_path_outcome=[
                        f"New {entity.name} is saved to database",
                        f"{default_actor} sees confirmation message",
                    ],
                    side_effects=[],
                    constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][
                        :3
                    ],
                    variants=["Validation error on required field"],
                    status=StoryStatus.ACCEPTED,
                    created_at=now,
                    accepted_at=now,
                )
            )
            count += 1

        # State machine transitions
        if entity.state_machine:
            for transition in entity.state_machine.transitions[:3]:
                if count >= max_stories:
                    break
                sm = entity.state_machine
                title = f"{default_actor} changes {entity.name} from {transition.from_state} to {transition.to_state}"
                if title in existing_titles:
                    skipped += 1
                    continue
                existing_titles.add(title)
                stories.append(
                    StorySpec(
                        story_id=next_story_id(),
                        title=title,
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
                count += 1

    return stories, skipped


def _generate_test_designs_from_stories(stories: list[Any]) -> list[Any]:
    """Generate test design specs from a list of stories.

    Returns list of TestDesignSpec instances.
    """
    from dazzle.core.ir.stories import StoryTrigger
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )

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

    return test_designs


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

    from dazzle.core.stories_persistence import add_stories, get_next_story_id, load_stories
    from dazzle.testing.test_design_persistence import add_test_designs

    max_stories = arguments.get("max_stories", 30)
    include_test_designs = arguments.get("include_test_designs", True)

    try:
        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"})

    # Load existing stories and build a title set for dedup
    existing_stories = load_stories(project_path)
    existing_titles = {s.title for s in existing_stories}

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

    stories, skipped = _generate_entity_stories(
        appspec, max_stories, existing_titles, default_actor, now, next_story_id
    )

    # Save stories
    all_stories = add_stories(project_path, stories, overwrite=False)

    result: dict[str, Any] = {
        "stories_proposed": len(stories),
        "stories_skipped_as_duplicates": skipped,
        "stories_total": len(all_stories),
        "status": "success",
    }

    # Generate test designs from stories
    if include_test_designs and stories:
        test_designs = _generate_test_designs_from_stories(stories)
        add_test_designs(project_path, test_designs, overwrite=False, to_dsl=True)
        result["test_designs_generated"] = len(test_designs)

    result["next_steps"] = [
        "dazzle test dsl-run    # Run Tier 1 API tests",
        "dazzle test run-all    # Run all test tiers",
    ]

    return json.dumps(result, indent=2)


def _propose_persona_coverage_tests(
    appspec: Any,
    covered_personas: set[str],
    max_actions: int,
    start_id: int,
) -> tuple[list[Any], list[dict[str, Any]], int]:
    """Generate test designs for uncovered personas.

    Returns (new_designs, actions_taken, next_id).
    """
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )

    new_designs: list[TestDesignSpec] = []
    actions_taken: list[dict[str, Any]] = []
    next_id = start_id

    for persona in appspec.personas:
        if len(actions_taken) >= max_actions:
            break
        if persona.id not in covered_personas and persona.goals:
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

    return new_designs, actions_taken, next_id


def _propose_entity_coverage_tests(
    appspec: Any,
    uncovered_entities: set[str],
    max_actions: int,
    actions_so_far: int,
    start_id: int,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Generate test designs for uncovered entities.

    Returns (new_designs, actions_taken).
    """
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )

    new_designs: list[TestDesignSpec] = []
    actions_taken: list[dict[str, Any]] = []
    next_id = start_id

    for entity in appspec.domain.entities:
        if actions_so_far + len(actions_taken) >= max_actions:
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

    return new_designs, actions_taken


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
    from dazzle.testing.test_design_persistence import add_test_designs, load_test_designs

    max_actions = arguments.get("max_actions", 5)
    focus = arguments.get("focus", "all")

    try:
        appspec = _load_appspec(project_path)
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
    new_designs: list[Any] = []
    next_id = len(existing_designs) + 1

    # Priority 1: Uncovered personas
    if focus in ("all", "personas"):
        persona_designs, persona_actions, next_id = _propose_persona_coverage_tests(
            appspec, covered_personas, max_actions, next_id
        )
        new_designs.extend(persona_designs)
        actions_taken.extend(persona_actions)

    # Priority 2: Uncovered entities
    if focus in ("all", "entities"):
        entity_designs, entity_actions = _propose_entity_coverage_tests(
            appspec, uncovered_entities, max_actions, len(actions_taken), next_id
        )
        new_designs.extend(entity_designs)
        actions_taken.extend(entity_actions)

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

    ops: dict[str, Callable[..., str]] = {
        "scaffold": scaffold_pitchspec_handler,
        "generate": generate_pitch_handler,
        "validate": validate_pitchspec_handler,
        "get": get_pitchspec_handler,
        "review": review_pitchspec_handler,
        "update": update_pitchspec_handler,
        "enrich": enrich_pitchspec_handler,
        "init_assets": init_assets_handler,
    }

    return _dispatch_project_ops(arguments, ops, "pitch")


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

    ops: dict[str, Callable[..., str]] = {
        "templates": templates_handler,
        "create": create_handler,
        "validate": validate_handler,
        "examples": examples_handler,
    }

    return _dispatch_standalone_ops(arguments, ops, "contribution")


# =============================================================================
# Bootstrap Handler
# =============================================================================


def handle_bootstrap(arguments: dict[str, Any]) -> str:
    """Handle bootstrap tool - entry point for naive app requests."""
    from .handlers.bootstrap import handle_bootstrap as _handle

    # Get project path from arguments or pre-resolved path
    project_path = arguments.get("_resolved_project_path") or arguments.get("project_path")
    if isinstance(project_path, str):
        project_path = Path(project_path)

    return _handle(arguments, project_path)


# =============================================================================
# Spec Analyze Handler
# =============================================================================


def handle_spec_analyze(arguments: dict[str, Any]) -> str:
    """Handle spec_analyze tool for cognition pass on narrative specs."""
    from .handlers.spec_analyze import handle_spec_analyze as _handle

    return _handle(arguments)


# =============================================================================
# Graph Handler
# =============================================================================


def _handle_graph_query(handlers: Any, arguments: dict[str, Any]) -> str:
    return json.dumps(
        handlers.handle_query(
            text=arguments.get("text", ""),
            entity_types=arguments.get("entity_types"),
            limit=arguments.get("limit", 20),
        ),
        indent=2,
    )


def _handle_graph_dependencies(handlers: Any, arguments: dict[str, Any]) -> str:
    return json.dumps(
        handlers.handle_get_dependencies(
            entity_id=arguments.get("entity_id", ""),
            relation_types=arguments.get("relation_types"),
            transitive=arguments.get("transitive", False),
        ),
        indent=2,
    )


def _handle_graph_dependents(handlers: Any, arguments: dict[str, Any]) -> str:
    return json.dumps(
        handlers.handle_get_dependents(
            entity_id=arguments.get("entity_id", ""),
            relation_types=arguments.get("relation_types"),
            transitive=arguments.get("transitive", False),
        ),
        indent=2,
    )


def _handle_graph_neighbourhood(handlers: Any, arguments: dict[str, Any]) -> str:
    return json.dumps(
        handlers.handle_get_neighbourhood(
            entity_id=arguments.get("entity_id", ""),
            depth=arguments.get("depth", 1),
            relation_types=arguments.get("relation_types"),
        ),
        indent=2,
    )


def _handle_graph_paths(handlers: Any, arguments: dict[str, Any]) -> str:
    return json.dumps(
        handlers.handle_find_paths(
            source_id=arguments.get("source_id", ""),
            target_id=arguments.get("target_id", ""),
            relation_types=arguments.get("relation_types"),
        ),
        indent=2,
    )


def _handle_graph_concept(graph: Any, arguments: dict[str, Any]) -> str:
    name = arguments.get("name", "")
    entity = graph.lookup_concept(name)
    if entity is None:
        return json.dumps({"error": f"Concept not found: {name}"})
    return json.dumps(
        {
            "id": entity.id,
            "type": entity.entity_type,
            "name": entity.name,
            "metadata": entity.metadata,
        },
        indent=2,
    )


def _handle_graph_inference(graph: Any, arguments: dict[str, Any]) -> str:
    query_text = arguments.get("text", "")
    limit = arguments.get("limit", 20)
    matches = graph.lookup_inference_matches(query_text, limit=limit)
    return json.dumps(
        {
            "query": query_text,
            "matches": [
                {
                    "id": e.id,
                    "name": e.name,
                    "category": e.metadata.get("category", ""),
                    "triggers": e.metadata.get("triggers", []),
                }
                for e in matches
            ],
            "count": len(matches),
        },
        indent=2,
    )


def _handle_graph_related(graph: Any, arguments: dict[str, Any]) -> str:
    entity_id = arguments.get("entity_id", "")
    relations = graph.get_relations(
        entity_id=entity_id,
        relation_type="related_concept",
        direction="outgoing",
    )
    related_ids = [r.target_id for r in relations]
    related_entities = [e for eid in related_ids if (e := graph.get_entity(eid)) is not None]
    return json.dumps(
        {
            "entity_id": entity_id,
            "related": [
                {"id": e.id, "name": e.name, "type": e.entity_type} for e in related_entities
            ],
            "count": len(related_entities),
        },
        indent=2,
    )


def _handle_graph_import(graph: Any, arguments: dict[str, Any]) -> str:
    import_data = arguments.get("data")
    file_path = arguments.get("file_path")
    if import_data is None and file_path:
        try:
            with open(file_path) as f:
                import_data = json.load(f)
        except Exception as e:
            return json.dumps({"error": f"Failed to read file: {e}"})
    if import_data is None:
        return json.dumps({"error": "Either 'data' or 'file_path' is required"})
    mode = arguments.get("mode", "merge")
    try:
        stats = graph.import_project_data(import_data, mode=mode)
        return json.dumps({"status": "success", "mode": mode, **stats}, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e)})


def handle_graph(arguments: dict[str, Any]) -> str:
    """Handle knowledge graph operations."""
    from .state import get_knowledge_graph, refresh_knowledge_graph

    graph = get_knowledge_graph()
    if graph is None:
        return json.dumps({"error": "Knowledge graph not initialized"})

    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(graph)
    operation = arguments.get("operation")

    # Operations that use the KnowledgeGraphHandlers wrapper
    handler_ops: dict[str, Callable[..., str]] = {
        "query": lambda args: _handle_graph_query(handlers, args),
        "dependencies": lambda args: _handle_graph_dependencies(handlers, args),
        "dependents": lambda args: _handle_graph_dependents(handlers, args),
        "neighbourhood": lambda args: _handle_graph_neighbourhood(handlers, args),
        "paths": lambda args: _handle_graph_paths(handlers, args),
        "stats": lambda args: json.dumps(handlers.handle_get_stats(), indent=2),
        "populate": lambda args: json.dumps(
            refresh_knowledge_graph(args.get("root_path")), indent=2
        ),
        # Operations that use the graph directly
        "concept": lambda args: _handle_graph_concept(graph, args),
        "inference": lambda args: _handle_graph_inference(graph, args),
        "related": lambda args: _handle_graph_related(graph, args),
        "export": lambda args: json.dumps(graph.export_project_data(), indent=2),
        "import": lambda args: _handle_graph_import(graph, args),
    }

    handler_fn = handler_ops.get(operation)  # type: ignore[arg-type]
    if handler_fn is None:
        return json.dumps({"error": f"Unknown graph operation: {operation}"})
    return handler_fn(arguments)


# =============================================================================
# Discovery Handler
# =============================================================================


async def handle_discovery(arguments: dict[str, Any]) -> str:
    """Handle capability discovery operations."""
    from .handlers.discovery import (
        app_coherence_handler,
        compile_discovery_handler,
        discovery_status_handler,
        emit_discovery_handler,
        get_discovery_report_handler,
        run_discovery_handler,
        verify_all_stories_handler,
    )

    ops: dict[str, Callable[..., Any]] = {
        "run": run_discovery_handler,
        "report": get_discovery_report_handler,
        "compile": compile_discovery_handler,
        "emit": emit_discovery_handler,
        "status": discovery_status_handler,
        "verify_all_stories": verify_all_stories_handler,
        "coherence": app_coherence_handler,
    }

    return await _dispatch_project_ops_async(arguments, ops, "discovery")


# =============================================================================
# User Profile Handler
# =============================================================================


def handle_user_profile(arguments: dict[str, Any]) -> str:
    """Handle user profile operations."""
    from .handlers.user_profile import handle_user_profile as _handle

    return _handle(arguments)


# =============================================================================
# Policy Handler
# =============================================================================


def handle_policy(arguments: dict[str, Any]) -> str:
    """Handle policy analysis operations."""
    from .handlers.policy import handle_policy as _handle

    project_path = _resolve_project(arguments)
    if project_path is None:
        return _project_error()

    return _handle(project_path, arguments)


# =============================================================================
# Pipeline Handler
# =============================================================================


def handle_pipeline(arguments: dict[str, Any]) -> str:
    """Handle pipeline operations."""
    from .handlers.pipeline import run_pipeline_handler

    ops: dict[str, Callable[..., str]] = {
        "run": run_pipeline_handler,
    }

    return _dispatch_project_ops(arguments, ops, "pipeline")


# =============================================================================
# Nightly Handler
# =============================================================================


def handle_nightly(arguments: dict[str, Any]) -> str:
    """Handle nightly parallel quality operations."""
    from .handlers.nightly import run_nightly_handler

    ops: dict[str, Callable[..., str]] = {
        "run": run_nightly_handler,
    }

    return _dispatch_project_ops(arguments, ops, "nightly")


# =============================================================================
# Pulse (founder-ready health report)
# =============================================================================


def handle_pulse(arguments: dict[str, Any]) -> str:
    """Handle pulse (founder-ready health report) operations."""
    from .handlers.pulse import (
        decisions_pulse_handler,
        persona_pulse_handler,
        radar_pulse_handler,
        run_pulse_handler,
        timeline_pulse_handler,
    )

    ops: dict[str, Callable[..., str]] = {
        "run": run_pulse_handler,
        "radar": radar_pulse_handler,
        "persona": persona_pulse_handler,
        "timeline": timeline_pulse_handler,
        "decisions": decisions_pulse_handler,
    }

    return _dispatch_project_ops(arguments, ops, "pulse")


async def handle_composition(arguments: dict[str, Any]) -> str:
    """Handle composition analysis operations."""
    from .handlers.composition import (
        analyze_composition_handler,
        audit_composition_handler,
        bootstrap_composition_handler,
        capture_composition_handler,
        inspect_styles_handler,
        report_composition_handler,
    )

    ops: dict[str, Callable[..., Any]] = {
        "audit": audit_composition_handler,
        "capture": capture_composition_handler,
        "analyze": analyze_composition_handler,
        "report": report_composition_handler,
        "bootstrap": bootstrap_composition_handler,
        "inspect_styles": inspect_styles_handler,
    }

    return await _dispatch_project_ops_async(arguments, ops, "composition")


# =============================================================================
# Sentinel Handler
# =============================================================================


def handle_sentinel(arguments: dict[str, Any]) -> str:
    """Handle sentinel operations."""
    from .handlers.sentinel import (
        findings_handler,
        history_handler,
        scan_handler,
        status_handler,
        suppress_handler,
    )

    ops: dict[str, Callable[..., str]] = {
        "scan": scan_handler,
        "findings": findings_handler,
        "suppress": suppress_handler,
        "status": status_handler,
        "history": history_handler,
    }

    return _dispatch_project_ops(arguments, ops, "sentinel")


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
    "process": handle_process,
    "dsl_test": handle_dsl_test,
    "e2e_test": handle_e2e_test,
    "status": handle_status,
    "knowledge": handle_knowledge,
    "pitch": handle_pitch,
    "contribution": handle_contribution,
    "user_management": handle_user_management,
    "bootstrap": handle_bootstrap,
    "spec_analyze": handle_spec_analyze,
    "graph": handle_graph,
    "discovery": handle_discovery,
    "nightly": handle_nightly,
    "pipeline": handle_pipeline,
    "user_profile": handle_user_profile,
    "policy": handle_policy,
    "pulse": handle_pulse,
    "composition": handle_composition,
    "sentinel": handle_sentinel,
}


async def dispatch_consolidated_tool(
    name: str,
    arguments: dict[str, Any],
    session: Any = None,
    progress_token: str | int | None = None,
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
        progress_token: Optional MCP progress token for sending progress updates.
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

        from .state import get_activity_store

        resolved_path = arguments.get("_resolved_project_path")
        activity_store = get_activity_store()

        # Lazy init: if KG is available but store was never created (e.g. init
        # ordering edge case), try to create it now so SQLite logging works.
        if activity_store is None:
            from .state import get_project_root, init_activity_store

            root = resolved_path if isinstance(resolved_path, Path) else get_project_root()
            if root is not None:
                init_activity_store(root)
                activity_store = get_activity_store()

        operation = arguments.get("operation")

        # Build progress context with activity store attached
        from .progress import ProgressContext

        progress = ProgressContext(
            session=session,
            progress_token=progress_token,
            activity_store=activity_store,
            tool_name=name,
            operation=operation,
        )
        arguments = {**arguments, "_progress": progress}

        # Write tool_start entry to SQLite
        if activity_store is not None:
            try:
                activity_store.log_event("tool_start", name, operation)
            except Exception:
                logger.debug("Failed to log tool_start event", exc_info=True)

        t0 = time.monotonic()
        call_ok = True
        call_error: str | None = None
        result: str | None = None
        try:
            if inspect.iscoroutinefunction(handler):
                raw = await handler(arguments)
            else:
                raw = handler(arguments)
            result = str(raw) if raw is not None else None
        except Exception:
            call_ok = False
            import traceback

            call_error = traceback.format_exc()[-500:]
            raise
        finally:
            duration_ms = (time.monotonic() - t0) * 1000

            # Write tool_end entry to SQLite activity store
            if activity_store is not None:
                try:
                    activity_store.log_event(
                        "tool_end",
                        name,
                        operation,
                        success=call_ok,
                        duration_ms=duration_ms,
                        error=call_error,
                    )
                except Exception:
                    logger.debug("Failed to log tool_end event", exc_info=True)

            # Write to tool_invocations (compact summary table)
            try:
                from .state import get_knowledge_graph

                graph = get_knowledge_graph()
                if graph is not None:
                    arg_keys = [k for k in arguments if not k.startswith("_")]
                    proj = arguments.get("_resolved_project_path")
                    proj_str = str(proj) if proj is not None else None
                    graph.log_tool_invocation(
                        tool_name=name,
                        operation=arguments.get("operation"),
                        argument_keys=arg_keys or None,
                        project_path=proj_str,
                        success=call_ok,
                        error_message=call_error,
                        result_size=len(result) if result else None,
                        duration_ms=duration_ms,
                    )
            except Exception:
                pass  # Never fail the tool call due to telemetry
        return result
    return None
