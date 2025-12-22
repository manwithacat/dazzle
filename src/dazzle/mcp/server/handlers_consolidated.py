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
    from .handlers.status import (
        get_dnr_logs_handler,
        get_mcp_status_handler,
    )

    operation = arguments.get("operation")

    if operation == "mcp":
        return get_mcp_status_handler(arguments)
    elif operation == "logs":
        return get_dnr_logs_handler(arguments)
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
    else:
        return json.dumps({"error": f"Unknown knowledge operation: {operation}"})


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
}


def dispatch_consolidated_tool(name: str, arguments: dict[str, Any]) -> str | None:
    """
    Dispatch a consolidated tool call.

    Returns the result string if the tool is a consolidated tool,
    or None if it's not (to allow fallback to original tools).
    """
    handler = CONSOLIDATED_TOOL_HANDLERS.get(name)
    if handler:
        return handler(arguments)
    return None
