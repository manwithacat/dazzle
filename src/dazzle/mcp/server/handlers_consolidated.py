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
                "error": (
                    "No project selected. This MCP server is rooted at a framework "
                    "checkout (dev mode), which only discovers example apps under "
                    "examples/ and never auto-selects one — so a project living "
                    "outside examples/ is invisible to it. To work on a specific "
                    "project: call 'select_project', or pass 'project_path' directly, "
                    "or (recommended) configure a project-scoped MCP entry with "
                    "'--working-dir <project>', which gives that project its own lock, "
                    "its own knowledge graph, and its pinned dazzle version instead of "
                    "the framework-dev install. See docs/architecture/mcp-server.md "
                    "(Per-project vs. global configuration). (#1629 G1)"
                ),
                "mode": "dev",
                "hint": "Every project-scoped tool needs project_path=…/app or select_project.",
                "available_projects": list(get_available_projects().keys()),
            }
        )
    else:
        return json.dumps(
            {
                "error": "No dazzle.toml found in project root",
                "project_root": str(get_project_root()),
                "hint": (
                    "Pass project_path to the app directory that contains dazzle.toml, "
                    "or start MCP with --working-dir pointing at that app. (#1629 G1)"
                ),
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
    from dazzle.page.runtime.fragment_registry import get_fragment_registry

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
        "composition": f"{_MOD_STORY}:story_composition_handler",
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
        "tenancy": _sem_wrap(f"{_MOD_SEM}:handle_infer_tenancy"),
        "compliance": _sem_wrap(f"{_MOD_SEM}:handle_infer_compliance"),
        "analytics": _sem_wrap(f"{_MOD_SEM}:handle_infer_analytics"),
        "extract_guards": _sem_wrap(f"{_MOD_SEM}:handle_extract_guards"),
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
    # #1629 G3 — demo/runtime world model (project-scoped read)
    if arguments.get("operation") in ("demo_world", "runtime"):
        from .handlers.status import get_demo_world_handler

        project_path = _resolve_project(arguments)
        if project_path is None:
            return _project_error()
        return get_demo_world_handler(project_path, arguments)
    return _status_standalone(arguments)


# =============================================================================
# Knowledge Handler
# =============================================================================

_MOD_KNOW = "dazzle.mcp.server.handlers.knowledge"

_knowledge_standalone: Callable[[dict[str, Any]], str] = _make_standalone_handler(
    "knowledge",
    {
        "concept": f"{_MOD_KNOW}:lookup_concept_handler",
        "examples": f"{_MOD_KNOW}:find_examples_handler",
        "cli_help": f"{_MOD_KNOW}:get_cli_help_handler",
        "workflow": f"{_MOD_KNOW}:get_workflow_guide_handler",
        "inference": f"{_MOD_KNOW}:lookup_inference_handler",
        "changelog": f"{_MOD_KNOW}:get_changelog_handler",
        "counter_prior": f"{_MOD_KNOW}:counter_prior_handler",
    },
)

_knowledge_project: Callable[[dict[str, Any]], str] = _make_project_handler(
    "knowledge",
    {
        "get_spec": f"{_MOD_KNOW}:get_product_spec_handler",
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
        # #1629 G6 — schema advertised these; consolidated map omitted them
        "access_matrix": _policy_inner,
        "verify_status": _policy_inner,
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
# Guide Handler (v0.71.7 — guided-onboarding inspection)
# =============================================================================

_MOD_GUIDE = "dazzle.mcp.server.handlers.guide"

handle_guide: Callable[[dict[str, Any]], str] = _make_project_handler(
    "guide",
    {
        "list": f"{_MOD_GUIDE}:guide_list_handler",
        "get": f"{_MOD_GUIDE}:guide_get_handler",
        "concordance": f"{_MOD_GUIDE}:guide_concordance_handler",
        "narrate": f"{_MOD_GUIDE}:guide_narrate_handler",
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
# Agent Handler
# =============================================================================


def handle_agent(arguments: dict[str, Any]) -> str:
    """#1605 agent closed-loop tool (context / prove / playbook)."""
    from .handlers.agent_loop import handle_agent as _handle

    return _handle(arguments)


# =============================================================================
# Main Dispatcher
# =============================================================================


# Map of consolidated tool names to their handlers
CONSOLIDATED_TOOL_HANDLERS = {
    "dsl": handle_dsl,
    "db": handle_db,
    "story": handle_story,
    "rhythm": handle_rhythm,
    "feedback": handle_feedback,
    "sitespec": handle_sitespec,
    "semantics": handle_semantics,
    "status": handle_status,
    "knowledge": handle_knowledge,
    "bootstrap": handle_bootstrap,
    "spec_analyze": handle_spec_analyze,
    "discovery": handle_discovery,
    "policy": handle_policy,
    "sentinel": handle_sentinel,
    "guide": handle_guide,
    "conformance": handle_conformance,
    "compliance": handle_compliance,
    "agent": handle_agent,
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
                # Fall through to per-handler resolution if pre-resolve fails (#smells-1.1).
                logger.debug(
                    "Pre-resolve of project_path failed; per-handler resolution will retry",
                    exc_info=True,
                )

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
                # Never fail the tool call due to telemetry (#smells-1.1).
                logger.debug("KG telemetry log_tool_invocation failed", exc_info=True)
        return result
    return None
