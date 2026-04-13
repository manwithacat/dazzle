"""
Consolidated tool handlers.

This module provides dispatch functions for consolidated tools.
Each handler routes the 'operation' parameter to existing handler functions.
"""

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
    """Delegate to handlers.common.error_response (canonical definition)."""
    from .handlers.common import error_response as _impl

    return _impl(msg)


def unknown_op_response(operation: str | None, tool: str) -> str:
    """Delegate to handlers.common.unknown_op_response (canonical definition)."""
    from .handlers.common import unknown_op_response as _impl

    return _impl(operation, tool)


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
    fn = ops.get(operation)  # type: ignore[arg-type]
    if fn is None:
        return unknown_op_response(operation, tool_label)
    return fn(project_path, arguments)


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
    fn = ops.get(operation)  # type: ignore[arg-type]
    if fn is None:
        return unknown_op_response(operation, tool_label)
    result = fn(project_path, arguments)
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
    fn = ops.get(operation)  # type: ignore[arg-type]
    if fn is None:
        return unknown_op_response(operation, tool_label)
    return fn(arguments)


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
            mod = importlib.import_module(  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
                module_path
            )
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

_MOD_DSL = "dazzle.mcp.server.handlers.dsl"
_MOD_DSL_STORIES = "dazzle.mcp.server.handlers.stories"
_MOD_DSL_FIDELITY = "dazzle.mcp.server.handlers.fidelity"


def _dsl_list_fragments(project_path: Path, args: dict[str, Any]) -> str:
    from dazzle_ui.runtime.fragment_registry import get_fragment_registry

    return json.dumps({"fragments": get_fragment_registry()}, indent=2)


handle_dsl: Callable[[dict[str, Any]], str] = _make_project_handler(
    "DSL",
    {
        "validate": f"{_MOD_DSL}:validate_dsl",
        "list_modules": f"{_MOD_DSL}:list_modules",
        "inspect_entity": f"{_MOD_DSL}:inspect_entity",
        "inspect_surface": f"{_MOD_DSL}:inspect_surface",
        "analyze": f"{_MOD_DSL}:analyze_patterns",
        "lint": f"{_MOD_DSL}:lint_project",
        "issues": f"{_MOD_DSL}:get_unified_issues",
        "get_spec": f"{_MOD_DSL_STORIES}:get_dsl_spec_handler",
        "fidelity": f"{_MOD_DSL_FIDELITY}:score_fidelity_handler",
        "export_frontend_spec": f"{_MOD_DSL}:export_frontend_spec_handler",
        "list_fragments": _dsl_list_fragments,
    },
)


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
        from dazzle.mcp.server.state import set_project_root

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
# DB Handler
# =============================================================================

_MOD_DB = "dazzle.mcp.server.handlers.db"

handle_db: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "db",
    {
        "status": f"{_MOD_DB}:db_status_handler",
        "verify": f"{_MOD_DB}:db_verify_handler",
    },
)


# =============================================================================
# Story Handler
# =============================================================================

_MOD_STORY = "dazzle.mcp.server.handlers.stories"
_MOD_STORY_PROC = "dazzle.mcp.server.handlers.process"

_story_dispatch: Callable[[dict[str, Any]], str] = _make_project_handler(
    "story",
    {
        "get": f"{_MOD_STORY}:get_stories_handler",
        "coverage": f"{_MOD_STORY_PROC}:stories_coverage_handler",
        "scope_fidelity": f"{_MOD_STORY_PROC}:scope_fidelity_handler",
    },
)


def handle_story(arguments: dict[str, Any]) -> str:
    """Handle consolidated story operations (read-only)."""
    # Special case: "get" with wall view
    if arguments.get("operation") == "get" and arguments.get("view") == "wall":
        project_path = _resolve_project(arguments)
        if project_path is None:
            return _project_error()
        from .handlers.stories import wall_stories_handler

        return wall_stories_handler(project_path, arguments)
    return _story_dispatch(arguments)


# =============================================================================
# Rhythm Handler
# =============================================================================

_MOD_RHYTHM = "dazzle.mcp.server.handlers.rhythm"

handle_rhythm: Callable[[dict[str, Any]], str] = _make_project_handler(
    "rhythm",
    {
        "coverage": f"{_MOD_RHYTHM}:coverage_rhythms_handler",
        "get": f"{_MOD_RHYTHM}:get_rhythm_handler",
        "list": f"{_MOD_RHYTHM}:list_rhythms_handler",
    },
)


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
# Feedback Handler
# =============================================================================

_MOD_FEEDBACK = "dazzle.mcp.server.handlers.feedback"

handle_feedback: Callable[[dict[str, Any]], str] = _make_project_handler(
    "feedback",
    {
        "list": f"{_MOD_FEEDBACK}:list_handler",
        "get": f"{_MOD_FEEDBACK}:get_handler",
        "triage": f"{_MOD_FEEDBACK}:triage_handler",
        "resolve": f"{_MOD_FEEDBACK}:resolve_handler",
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

_MOD_SEM = "dazzle.mcp.event_first_tools"


def _sem_wrap(ref: str) -> Callable[[Path, dict[str, Any]], str]:
    """Adapt an event_first_tools handler (args, project_path) to (project_path, args)."""
    lazy = _lazy_import(ref)

    def wrapper(project_path: Path, args: dict[str, Any]) -> str:
        result: str = lazy(args, project_path)
        return result

    return wrapper


handle_semantics: Callable[[dict[str, Any]], str] = _make_project_handler(
    "semantics",
    {
        "extract": _sem_wrap(f"{_MOD_SEM}:handle_extract_semantics"),
        "validate_events": _sem_wrap(f"{_MOD_SEM}:handle_validate_events"),
        "tenancy": _sem_wrap(f"{_MOD_SEM}:handle_infer_tenancy"),
        "compliance": _sem_wrap(f"{_MOD_SEM}:handle_infer_compliance"),
        "analytics": _sem_wrap(f"{_MOD_SEM}:handle_infer_analytics"),
        "extract_guards": _sem_wrap(f"{_MOD_SEM}:handle_extract_guards"),
    },
)


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

_MOD_STATUS = "dazzle.mcp.server.handlers.status"
_MOD_STATUS_PROJ = "dazzle.mcp.server.handlers.project"

_status_standalone: Callable[[dict[str, Any]], str] = _make_standalone_handler(
    "status",
    {
        "mcp": f"{_MOD_STATUS}:get_mcp_status_handler",
        "logs": f"{_MOD_STATUS}:get_dnr_logs_handler",
        "telemetry": f"{_MOD_STATUS}:get_telemetry_handler",
        "activity": f"{_MOD_STATUS}:get_activity_handler",
    },
)


def handle_status(arguments: dict[str, Any]) -> str:
    """Handle consolidated status operations."""
    # active_project uses a resolved path arg rather than the standard dispatch
    if arguments.get("operation") == "active_project":
        from .handlers.project import get_active_project_info

        return get_active_project_info(resolved_path=arguments.get("_resolved_project_path"))
    return _status_standalone(arguments)


# =============================================================================
# Knowledge Handler
# =============================================================================

_MOD_KNOW = "dazzle.mcp.server.handlers.knowledge"
_MOD_KNOW_TOOL = "dazzle.mcp.server.tool_handlers"

_knowledge_standalone: Callable[[dict[str, Any]], str] = _make_standalone_handler(
    "knowledge",
    {
        "concept": f"{_MOD_KNOW}:lookup_concept_handler",
        "examples": f"{_MOD_KNOW_TOOL}:find_examples_handler",
        "cli_help": f"{_MOD_KNOW}:get_cli_help_handler",
        "workflow": f"{_MOD_KNOW}:get_workflow_guide_handler",
        "inference": f"{_MOD_KNOW}:lookup_inference_handler",
        "changelog": f"{_MOD_KNOW}:get_changelog_handler",
    },
)

_knowledge_project: Callable[[dict[str, Any]], str] = _make_project_handler(
    "knowledge",
    {
        "get_spec": f"{_MOD_KNOW_TOOL}:get_product_spec_handler",
    },
)


def handle_knowledge(arguments: dict[str, Any]) -> str:
    """Handle consolidated knowledge operations."""
    # get_spec needs project context; all other ops are standalone
    if arguments.get("operation") == "get_spec":
        return _knowledge_project(arguments)
    if arguments.get("operation") == "search_commands":
        import json

        from dazzle.mcp.cli_help import search_commands

        query = arguments.get("query", "")
        return json.dumps(search_commands(query))
    return _knowledge_standalone(arguments)


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
    from .state import resolve_project_path

    entity = arguments.get("entity") or arguments.get("name")
    event = arguments.get("event", "created")

    try:
        project_root = resolve_project_path(arguments.get("project_path"))
    except ValueError as exc:
        return error_response(str(exc))

    from .handlers.common import load_project_appspec

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


def _handle_graph_topology(arguments: dict[str, Any]) -> str:
    """Derive project topology from the current AppSpec.

    Returns entity relationships, surface→entity mapping, workspace composition,
    and dead construct detection. All derived from the DSL — no separate indexing.
    """
    from .state import resolve_project_path

    try:
        project_root = resolve_project_path(arguments.get("project_path"))
    except ValueError as exc:
        return error_response(str(exc))

    from .handlers.common import load_project_appspec

    appspec = load_project_appspec(project_root)

    # Entity relationship graph
    entities_map: dict[str, dict[str, Any]] = {}
    for entity in appspec.domain.entities:
        refs: list[dict[str, str]] = []
        for field in entity.fields:
            if field.type.kind in ("ref", "belongs_to") and field.type.ref_entity:
                refs.append(
                    {
                        "field": field.name,
                        "target": field.type.ref_entity,
                        "kind": str(field.type.kind),
                        "required": "yes"
                        if "required" in [str(m) for m in field.modifiers]
                        else "no",
                    }
                )
        entities_map[entity.name] = {
            "field_count": len(entity.fields),
            "references": refs,
            "has_state_machine": getattr(entity, "state_machine", None) is not None,
            "has_access": getattr(entity, "access", None) is not None,
        }

    # Surface → entity mapping
    surface_map: dict[str, dict[str, Any]] = {}
    entity_surfaces: dict[str, list[str]] = {}  # reverse index
    for surface in appspec.surfaces:
        surface_map[surface.name] = {
            "entity_ref": surface.entity_ref,
            "mode": str(surface.mode),
            "title": surface.title,
        }
        if surface.entity_ref:
            entity_surfaces.setdefault(surface.entity_ref, []).append(surface.name)

    # Workspace composition
    workspace_map: dict[str, dict[str, Any]] = {}
    workspace_entities: dict[str, set[str]] = {}
    for ws in appspec.workspaces:
        regions: list[dict[str, str]] = []
        ws_ents: set[str] = set()
        for region in getattr(ws, "regions", []):
            source = getattr(region, "source", None) or ""
            regions.append(
                {
                    "name": getattr(region, "name", ""),
                    "type": str(getattr(region, "type", "")),
                    "source": source,
                }
            )
            if source:
                ws_ents.add(source)
        workspace_map[ws.name] = {
            "title": getattr(ws, "title", ws.name),
            "region_count": len(regions),
            "regions": regions,
            "entities": sorted(ws_ents),
        }
        workspace_entities[ws.name] = ws_ents

    # Dead construct detection
    all_entity_names = set(entities_map.keys())
    entities_with_surfaces = set(entity_surfaces.keys())
    entities_in_workspaces: set[str] = set()
    for ws_ents in workspace_entities.values():
        entities_in_workspaces |= ws_ents

    dead = {
        "entities_without_surfaces": sorted(all_entity_names - entities_with_surfaces),
        "entities_without_workspaces": sorted(entities_with_surfaces - entities_in_workspaces),
    }

    # Query filter (optional — return only info about a specific entity)
    entity_filter = arguments.get("entity")
    if entity_filter:
        filtered = {
            "entity": entity_filter,
            "details": entities_map.get(entity_filter, {}),
            "surfaces": entity_surfaces.get(entity_filter, []),
            "in_workspaces": [
                ws_name for ws_name, ents in workspace_entities.items() if entity_filter in ents
            ],
            "referenced_by": [
                {"entity": ename, "field": ref["field"]}
                for ename, edata in entities_map.items()
                for ref in edata["references"]
                if ref["target"] == entity_filter
            ],
        }
        return json.dumps(filtered, indent=2)

    return json.dumps(
        {
            "entities": len(entities_map),
            "surfaces": len(surface_map),
            "workspaces": len(workspace_map),
            "entity_graph": entities_map,
            "surface_map": surface_map,
            "workspace_map": workspace_map,
            "dead_constructs": dead,
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

    # Operations that use the KnowledgeGraphHandlers wrapper
    ops: dict[str, Callable[..., str]] = {
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
        "topology": lambda args: _handle_graph_topology(args),
    }

    return _dispatch_standalone_ops(arguments, ops, "graph")


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
# E2E Environment Handler
# =============================================================================

_MOD_E2E = "dazzle.mcp.server.handlers.e2e"

handle_e2e: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "e2e",
    {
        "list_modes": f"{_MOD_E2E}:e2e_list_modes_handler",
        "describe_mode": f"{_MOD_E2E}:e2e_describe_mode_handler",
        "status": f"{_MOD_E2E}:e2e_status_handler",
        "list_baselines": f"{_MOD_E2E}:e2e_list_baselines_handler",
    },
)


# =============================================================================
# Fitness Triage Handler
# =============================================================================

_MOD_FITNESS = "dazzle.mcp.server.handlers.fitness"

handle_fitness: Callable[[dict[str, Any]], Any] = _make_project_handler_async(
    "fitness",
    {
        "queue": f"{_MOD_FITNESS}:fitness_queue_handler",
    },
)


# =============================================================================
# User Profile Handler
# =============================================================================

_MOD_UP = "dazzle.mcp.server.handlers.user_profile"

handle_user_profile: Callable[[dict[str, Any]], str] = _lazy_import(
    f"{_MOD_UP}:handle_user_profile"
)


# =============================================================================
# Policy Handler
# =============================================================================

_MOD_POL = "dazzle.mcp.server.handlers.policy"

# handle_policy(project_path, args) handles its own op dispatch internally;
# wrap it so _make_project_handler resolves the project path before calling it.
_policy_inner: Callable[..., str] = _lazy_import(f"{_MOD_POL}:handle_policy")

handle_policy: Callable[[dict[str, Any]], str] = _make_project_handler(
    "policy",
    {
        "analyze": _policy_inner,
        "conflicts": _policy_inner,
        "coverage": _policy_inner,
        "simulate": _policy_inner,
    },
)


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
        "journey": f"{_MOD_TI}:test_journey_handler",
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
        "fuzz_summary": f"{_MOD_SENT}:fuzz_summary_handler",
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
# Param Handler
# =============================================================================

_MOD_PARAM = "dazzle.mcp.server.handlers.param"

handle_param: Callable[[dict[str, Any]], str] = _make_project_handler(
    "param",
    {
        "list": f"{_MOD_PARAM}:param_list_handler",
        "get": f"{_MOD_PARAM}:param_get_handler",
    },
)


# =============================================================================
# Conformance Handler
# =============================================================================

_MOD_CONF = "dazzle.mcp.server.handlers.conformance"

handle_conformance: Callable[[dict[str, Any]], str] = _make_project_handler(
    "conformance",
    {
        "summary": f"{_MOD_CONF}:conformance_summary_handler",
        "cases": f"{_MOD_CONF}:conformance_cases_handler",
        "gaps": f"{_MOD_CONF}:conformance_gaps_handler",
        "monitor_status": f"{_MOD_CONF}:conformance_monitor_status_handler",
    },
)


# =============================================================================
# Compliance Operations Handler
# =============================================================================

_MOD_COMPLIANCE = "dazzle.mcp.server.handlers.compliance_handler"

handle_compliance: Callable[[dict[str, Any]], str] = _make_project_handler(
    "compliance",
    {
        "compile": f"{_MOD_COMPLIANCE}:compile_compliance",
        "evidence": f"{_MOD_COMPLIANCE}:extract_evidence_op",
        "gaps": f"{_MOD_COMPLIANCE}:compliance_gaps",
        "summary": f"{_MOD_COMPLIANCE}:compliance_summary",
        "review": f"{_MOD_COMPLIANCE}:compliance_review",
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
    "db": handle_db,
    "story": handle_story,
    "rhythm": handle_rhythm,
    "demo_data": handle_demo_data,
    "feedback": handle_feedback,
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
    "e2e": handle_e2e,
    "fitness": handle_fitness,
    "user_profile": handle_user_profile,
    "policy": handle_policy,
    "composition": handle_composition,
    "sentinel": handle_sentinel,
    "test_intelligence": handle_test_intelligence,
    "llm": handle_llm,
    "param": handle_param,
    "conformance": handle_conformance,
    "compliance": handle_compliance,
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
