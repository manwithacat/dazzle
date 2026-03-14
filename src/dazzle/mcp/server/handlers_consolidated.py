"""
Consolidated tool handlers.

This module provides dispatch functions for consolidated tools.
Each handler routes the 'operation' parameter to existing handler functions.
"""

from __future__ import annotations

import importlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .state import get_available_projects, get_project_root, is_dev_mode, resolve_project_path

logger = logging.getLogger(__name__)


def error_response(msg: str) -> str:
    """Return a JSON error response string."""
    return json.dumps({"error": msg})


def unknown_op_response(operation: str | None, tool: str) -> str:
    """Return a JSON error for an unknown operation."""
    return json.dumps({"error": f"Unknown {tool} operation: {operation}"})


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
        return unknown_op_response(operation, tool_label)
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
        return unknown_op_response(operation, tool_label)
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
        return unknown_op_response(operation, tool_label)
    return handler(arguments)


# ---------------------------------------------------------------------------
# Handler factory — eliminates repeated import/dispatch boilerplate
# ---------------------------------------------------------------------------


def _lazy_import(ref: str) -> Callable[..., Any]:
    """Import *module_path:attr_name* on first call, then cache the callable."""
    module_path, attr_name = ref.rsplit(":", 1)
    fn: Callable[..., Any] | None = None

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal fn
        if fn is None:
            mod = importlib.import_module(module_path)
            fn = getattr(mod, attr_name)
        return fn(*args, **kwargs)

    return wrapper


def _resolve_ops(
    raw: dict[str, str | Callable[..., Any]],
) -> dict[str, Callable[..., Any]]:
    """Turn a mixed dict of *"module:attr"* strings and callables into a pure callable dict."""
    resolved: dict[str, Callable[..., Any]] = {}
    for op, ref in raw.items():
        if isinstance(ref, str):
            resolved[op] = _lazy_import(ref)
        else:
            resolved[op] = ref
    return resolved


def _make_project_handler(
    tool_label: str,
    operations: dict[str, str | Callable[..., Any]],
) -> Callable[[dict[str, Any]], str]:
    """Create a sync handler that resolves project path and dispatches by operation."""
    ops = _resolve_ops(operations)

    def handler(arguments: dict[str, Any]) -> str:
        return _dispatch_project_ops(arguments, ops, tool_label)

    return handler


def _make_project_handler_async(
    tool_label: str,
    operations: dict[str, str | Callable[..., Any]],
) -> Callable[[dict[str, Any]], Any]:
    """Create an async handler that resolves project path and dispatches by operation."""
    ops = _resolve_ops(operations)

    async def handler(arguments: dict[str, Any]) -> str:
        return await _dispatch_project_ops_async(arguments, ops, tool_label)

    return handler


def _make_standalone_handler(
    tool_label: str,
    operations: dict[str, str | Callable[..., Any]],
) -> Callable[[dict[str, Any]], str]:
    """Create a sync handler that dispatches by operation without project resolution."""
    ops = _resolve_ops(operations)

    def handler(arguments: dict[str, Any]) -> str:
        return _dispatch_standalone_ops(arguments, ops, tool_label)

    return handler


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
        get_api_pack_handler,
        list_api_packs_handler,
        search_api_packs_handler,
    )

    # Set project root for project-local pack discovery
    project_path = _resolve_project(arguments)
    if project_path is not None:
        from dazzle.api_kb.loader import set_project_root

        set_project_root(project_path)

    standalone_ops: dict[str, Callable[..., str]] = {
        "list": list_api_packs_handler,
        "search": search_api_packs_handler,
        "get": get_api_pack_handler,
    }

    operation = arguments.get("operation")

    standalone = standalone_ops.get(operation)  # type: ignore[arg-type]
    if standalone is not None:
        return standalone(arguments)

    return unknown_op_response(operation, "API pack")


# =============================================================================
# Mock Handler
# =============================================================================

_MOD_MOCK = "dazzle.mcp.server.handlers.mock"

handle_mock: Callable[[dict[str, Any]], str] = _make_project_handler(
    "mock",
    {
        "status": f"{_MOD_MOCK}:mock_status_handler",
        "request_log": f"{_MOD_MOCK}:mock_request_log_handler",
    },
)


# =============================================================================
# Story Handler
# =============================================================================


def handle_story(arguments: dict[str, Any]) -> str:
    """Handle consolidated story operations (read-only)."""
    from .handlers.process import scope_fidelity_handler, stories_coverage_handler
    from .handlers.stories import (
        get_stories_handler,
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
        "get": get_stories_handler,
        "coverage": stories_coverage_handler,
        "scope_fidelity": scope_fidelity_handler,
    }

    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return unknown_op_response(operation, "story")
    return handler(project_path, arguments)


# =============================================================================
# Rhythm Handler
# =============================================================================


def handle_rhythm(arguments: dict[str, Any]) -> str:
    """Handle consolidated rhythm operations (read-only)."""
    from .handlers.rhythm import (
        coverage_rhythms_handler,
        get_rhythm_handler,
        list_rhythms_handler,
    )

    operation = arguments.get("operation")
    project_path = _resolve_project(arguments)

    if project_path is None:
        return _project_error()

    ops: dict[str, Callable[..., str]] = {
        "coverage": coverage_rhythms_handler,
        "get": get_rhythm_handler,
        "list": list_rhythms_handler,
    }

    handler = ops.get(operation)  # type: ignore[arg-type]
    if handler is None:
        return unknown_op_response(operation, "rhythm")
    return handler(project_path, arguments)


# =============================================================================
# Demo Data Handler
# =============================================================================

_MOD_DEMO = "dazzle.mcp.server.handlers.demo_data"

handle_demo_data: Callable[[dict[str, Any]], str] = _make_project_handler(
    "demo data",
    {
        "get": f"{_MOD_DEMO}:get_demo_blueprint_handler",
    },
)


# =============================================================================
# SiteSpec Handler
# =============================================================================

_MOD_SITE = "dazzle.mcp.server.handlers.sitespec"

handle_sitespec: Callable[[dict[str, Any]], str] = _make_project_handler(
    "sitespec",
    {
        "get": f"{_MOD_SITE}:get_sitespec_handler",
        "validate": f"{_MOD_SITE}:validate_sitespec_handler",
        "scaffold": f"{_MOD_SITE}:scaffold_site_handler",
        "get_copy": f"{_MOD_SITE}:get_copy_handler",
        "scaffold_copy": f"{_MOD_SITE}:scaffold_copy_handler",
        "review_copy": f"{_MOD_SITE}:review_copy_handler",
        "coherence": f"{_MOD_SITE}:coherence_handler",
        "get_theme": f"{_MOD_SITE}:get_theme_handler",
        "scaffold_theme": f"{_MOD_SITE}:scaffold_theme_handler",
        "validate_theme": f"{_MOD_SITE}:validate_theme_handler",
        "generate_tokens": f"{_MOD_SITE}:generate_tokens_handler",
        "generate_imagery_prompts": f"{_MOD_SITE}:generate_imagery_prompts_handler",
        "review": f"{_MOD_SITE}:review_sitespec_handler",
        "advise": f"{_MOD_SITE}:advise_sitespec_handler",
    },
)


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

_MOD_PROC = "dazzle.mcp.server.handlers.process"

handle_process: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "process",
    {
        "list": f"{_MOD_PROC}:list_processes_handler",
        "inspect": f"{_MOD_PROC}:inspect_process_handler",
        "list_runs": f"{_MOD_PROC}:list_process_runs_handler",
        "get_run": f"{_MOD_PROC}:get_process_run_handler",
        "coverage": f"{_MOD_PROC}:stories_coverage_handler",
    },
)


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

    return unknown_op_response(operation, "status")


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

    return unknown_op_response(operation, "knowledge")


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
            return error_response("email is required")
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
            return error_response("user_id or email is required")
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
            return error_response("user_id is required")
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
            return error_response("user_id is required")
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
            return error_response("user_id is required")
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
            return error_response("session_id is required")
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
        return unknown_op_response(operation, "user_management")


# =============================================================================
# Test Design Handler
# =============================================================================

_MOD_TD = "dazzle.mcp.server.handlers.test_design"

handle_test_design: Callable[[dict[str, Any]], str] = _make_project_handler(
    "test design",
    {
        "get": f"{_MOD_TD}:get_test_designs_handler",
        "gaps": f"{_MOD_TD}:get_test_gaps_handler",
    },
)


# =============================================================================
# Pitch Handler
# =============================================================================

_MOD_PITCH = "dazzle.mcp.server.handlers.pitch"

handle_pitch: Callable[[dict[str, Any]], str] = _make_project_handler(
    "pitch",
    {
        "get": f"{_MOD_PITCH}:get_pitchspec_handler",
    },
)


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
        return error_response(f"Concept not found: {name}")
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
            return error_response(f"Failed to read file: {e}")
    if import_data is None:
        return error_response("Either 'data' or 'file_path' is required")
    mode = arguments.get("mode", "merge")
    try:
        stats = graph.import_project_data(import_data, mode=mode)
        return json.dumps({"status": "success", "mode": mode, **stats}, indent=2)
    except ValueError as e:
        return error_response(str(e))


def _handle_graph_triggers(arguments: dict[str, Any]) -> str:
    """Show everything that triggers when an entity event fires."""
    from .state import get_active_project_path

    entity = arguments.get("entity") or arguments.get("name")
    event = arguments.get("event", "created")

    project_root = get_active_project_path()
    if not project_root:
        return error_response("No active project")

    from .common import load_project_appspec

    appspec = load_project_appspec(project_root)

    results: list[dict[str, Any]] = []

    # Check LLM intent triggers
    for intent in appspec.llm_intents or []:
        for trigger in intent.triggers:
            if entity and trigger.on_entity != entity:
                continue
            if trigger.on_event.value != event:
                continue
            results.append(
                {
                    "type": "llm_intent",
                    "name": intent.name,
                    "entity": trigger.on_entity,
                    "event": trigger.on_event.value,
                    "input_map": trigger.input_map,
                    "write_back": trigger.write_back,
                    "when": trigger.when,
                }
            )

    # Check process triggers
    for process in appspec.processes or []:
        if process.trigger and process.trigger.entity_name:
            if entity and process.trigger.entity_name != entity:
                continue
            if process.trigger.event_type != event:
                continue
            results.append(
                {
                    "type": "process",
                    "name": process.name,
                    "entity": process.trigger.entity_name,
                    "event": process.trigger.event_type,
                    "steps": [s.name for s in process.steps],
                }
            )

    return json.dumps(
        {
            "entity": entity,
            "event": event,
            "trigger_count": len(results),
            "triggers": results,
        },
        indent=2,
    )


def handle_graph(arguments: dict[str, Any]) -> str:
    """Handle knowledge graph operations."""
    from .state import get_knowledge_graph, refresh_knowledge_graph

    graph = get_knowledge_graph()
    if graph is None:
        return error_response("Knowledge graph not initialized")

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
        "triggers": lambda args: _handle_graph_triggers(args),
    }

    handler_fn = handler_ops.get(operation)  # type: ignore[arg-type]
    if handler_fn is None:
        return unknown_op_response(operation, "graph")
    return handler_fn(arguments)


# =============================================================================
# Discovery Handler
# =============================================================================

_MOD_DISC = "dazzle.mcp.server.handlers.discovery"

handle_discovery: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "discovery",
    {
        "coherence": f"{_MOD_DISC}:app_coherence_handler",
    },
)


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
# Composition Handler
# =============================================================================

_MOD_COMP = "dazzle.mcp.server.handlers.composition"

handle_composition: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "composition",
    {
        "audit": f"{_MOD_COMP}:audit_composition_handler",
        "capture": f"{_MOD_COMP}:capture_composition_handler",
        "analyze": f"{_MOD_COMP}:analyze_composition_handler",
        "report": f"{_MOD_COMP}:report_composition_handler",
        "bootstrap": f"{_MOD_COMP}:bootstrap_composition_handler",
        "inspect_styles": f"{_MOD_COMP}:inspect_styles_handler",
    },
)


# =============================================================================
# Test Intelligence Handler
# =============================================================================

_MOD_TI = "dazzle.mcp.server.handlers.test_intelligence"

handle_test_intelligence: Callable[[dict[str, Any]], str] = _make_project_handler(
    "test intelligence",
    {
        "summary": f"{_MOD_TI}:test_summary_handler",
        "failures": f"{_MOD_TI}:test_failures_handler",
        "regression": f"{_MOD_TI}:test_regression_handler",
        "coverage": f"{_MOD_TI}:test_coverage_handler",
        "context": f"{_MOD_TI}:test_context_handler",
    },
)


# =============================================================================
# Sentinel Handler
# =============================================================================

_MOD_SENT = "dazzle.mcp.server.handlers.sentinel"

handle_sentinel: Callable[[dict[str, Any]], str] = _make_project_handler(
    "sentinel",
    {
        "findings": f"{_MOD_SENT}:findings_handler",
        "status": f"{_MOD_SENT}:status_handler",
        "history": f"{_MOD_SENT}:history_handler",
    },
)


# =============================================================================
# LLM Handler
# =============================================================================

_MOD_LLM = "dazzle.mcp.server.handlers.llm"

handle_llm: Callable[[dict[str, Any]], str] = _make_project_handler(
    "llm",
    {
        "list_intents": f"{_MOD_LLM}:list_intents_handler",
        "list_models": f"{_MOD_LLM}:list_models_handler",
        "inspect_intent": f"{_MOD_LLM}:inspect_intent_handler",
        "get_config": f"{_MOD_LLM}:get_config_handler",
    },
)


# =============================================================================
# Main Dispatcher
# =============================================================================

# Map of consolidated tool names to their handlers
CONSOLIDATED_TOOL_HANDLERS = {
    "dsl": handle_dsl,
    "api_pack": handle_api_pack,
    "mock": handle_mock,
    "story": handle_story,
    "rhythm": handle_rhythm,
    "demo_data": handle_demo_data,
    "test_design": handle_test_design,
    "sitespec": handle_sitespec,
    "semantics": handle_semantics,
    "process": handle_process,
    "status": handle_status,
    "knowledge": handle_knowledge,
    "pitch": handle_pitch,
    "user_management": handle_user_management,
    "bootstrap": handle_bootstrap,
    "spec_analyze": handle_spec_analyze,
    "graph": handle_graph,
    "discovery": handle_discovery,
    "user_profile": handle_user_profile,
    "policy": handle_policy,
    "composition": handle_composition,
    "sentinel": handle_sentinel,
    "test_intelligence": handle_test_intelligence,
    "llm": handle_llm,
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
        # Pre-resolve project path synchronously (MCP roots/list is unreliable
        # in practice — clients may not respond, causing hangs. See #498.)
        if "_resolved_project_path" not in arguments:
            try:
                from .state import resolve_project_path

                resolved = resolve_project_path(arguments.get("project_path"))
                arguments = {**arguments, "_resolved_project_path": resolved}
            except Exception:
                pass  # Fall through to per-handler resolution

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
