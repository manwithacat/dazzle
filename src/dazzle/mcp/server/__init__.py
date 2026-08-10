"""
DAZZLE MCP Server implementation (MCP Python SDK v2 / spec 2026-07-28).

Low-level ``Server`` with constructor ``on_*`` handlers (decorators removed in
SDK v2). App state (project root, KG, session dirs) remains process-local;
protocol sessions are no longer required by the transport.

Supports:
- Normal Mode: directory with dazzle.toml
- Dev Mode: Dazzle development environment (examples/, src/dazzle/)
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

try:
    from mcp.server.caching import CacheHint
except (ImportError, ModuleNotFoundError, AttributeError):  # pragma: no cover
    CacheHint = None  # type: ignore[misc, assignment]
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    GetPromptRequestParams,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    Prompt,
    PromptArgument,
    PromptMessage,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

from dazzle.mcp.examples import get_example_metadata
from dazzle.mcp.resources import create_resources
from dazzle.mcp.semantics_kb import get_dsl_patterns, get_semantic_index

from .glossary import get_glossary
from .handlers_consolidated import dispatch_consolidated_tool
from .state import (
    get_active_project_path,
    get_available_projects,
    get_knowledge_graph,
    get_project_root,
    init_dev_mode,
    init_knowledge_graph,
    is_dev_mode,
    set_project_root,
)
from .tool_handlers import (
    get_active_project_info,
    get_entities,
    get_surfaces,
    list_modules,
    list_projects,
    select_project,
    validate_all_projects,
)
from .tools_consolidated import get_all_consolidated_tools

# Configure logging to stderr only (stdout is reserved for JSON-RPC protocol)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

try:
    from dazzle._version import get_version

    _dazzle_version: str = get_version() or ""
except Exception:
    _dazzle_version = ""


# ============================================================================
# Tool helpers (also used by tests / verify-mcp)
# ============================================================================


async def list_tools_handler() -> list[Tool]:
    """List available DAZZLE tools (public helper for tests)."""
    logger.info("Using consolidated tools mode")
    return get_all_consolidated_tools()


async def _handle_list_tools(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListToolsResult:
    del ctx, params  # no pagination yet
    return ListToolsResult(tools=await list_tools_handler())


async def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    session: Any = None,
    progress_token: str | int | None = None,
) -> str:
    """Dispatch one tool; return JSON/text payload string."""
    result = await dispatch_consolidated_tool(
        name, arguments or {}, session=session, progress_token=progress_token
    )
    if result is not None:
        return result

    # Dev mode `project` tool (consolidated in #1074)
    if name == "project":
        op = (arguments or {}).get("operation", "")
        if op == "list":
            return list_projects()
        if op == "select":
            return select_project(arguments)
        if op == "get_active":
            forwarded = {k: v for k, v in (arguments or {}).items() if k != "operation"}
            routed = await dispatch_consolidated_tool(
                "status",
                {"operation": "active_project", **forwarded},
                session=session,
            )
            return routed if routed is not None else get_active_project_info()
        if op == "validate_all":
            return validate_all_projects()
        return json.dumps(
            {
                "error": (
                    f"Unknown operation {op!r} for project tool. "
                    "Valid: list, get_active, select, validate_all"
                )
            }
        )

    return json.dumps({"error": f"Unknown tool: {name}"})


async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
    """Execute a tool (public helper for tests — no protocol context)."""
    text = await _execute_tool(name, arguments or {}, session=None, progress_token=None)
    return [TextContent(type="text", text=text)]


async def _handle_call_tool(
    ctx: ServerRequestContext,
    params: CallToolRequestParams,
) -> CallToolResult:
    progress_token = None
    if ctx.meta and "progress_token" in ctx.meta:
        progress_token = ctx.meta["progress_token"]
    try:
        text = await _execute_tool(
            params.name,
            params.arguments or {},
            session=ctx.session,
            progress_token=progress_token,
        )
        return CallToolResult(
            content=[TextContent(type="text", text=text)],
            is_error=False,
        )
    except Exception as exc:  # noqa: BLE001 — surface tool failures as is_error
        logger.exception("Tool %s failed", params.name)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps({"error": str(exc)}))],
            is_error=True,
        )


# ============================================================================
# Resources
# ============================================================================


def _resource(
    uri: str,
    name: str,
    description: str,
    mime_type: str = "text/plain",
) -> Resource:
    return Resource(uri=uri, name=name, description=description, mime_type=mime_type)


async def list_resources_handler() -> list[Resource]:
    """List resources (public helper)."""
    resources: list[Resource] = [
        _resource(
            "dazzle://docs/glossary",
            "DAZZLE Glossary (v0.2)",
            "Definitions of DAZZLE v0.2 terms (surface, persona, workspace, attention signals, etc.)",
            "text/markdown",
        ),
        _resource(
            "dazzle://docs/quick-reference",
            "DAZZLE Quick Reference",
            "DSL syntax quick reference with examples",
            "text/markdown",
        ),
        _resource(
            "dazzle://docs/dsl-reference",
            "DAZZLE DSL Reference (v0.2)",
            "Complete DSL v0.2 reference documentation with UX semantic layer",
            "text/markdown",
        ),
        _resource(
            "dazzle://semantics/index",
            "DAZZLE Semantic Concept Index (v0.2)",
            "Structured index of all DSL v0.2 concepts with definitions, syntax, and examples",
            "application/json",
        ),
        _resource(
            "dazzle://examples/catalog",
            "Example Projects Catalog",
            "Catalog of example projects with metadata about features they demonstrate",
            "application/json",
        ),
        _resource(
            "dazzle://docs/context",
            "DAZZLE Context",
            "Quick reference context for Claude - key concepts, tools, and common workflows",
            "text/markdown",
        ),
        _resource(
            "dazzle://docs/patterns",
            "DSL Patterns",
            "Common DSL patterns with copy-paste examples (CRUD, dashboard, role-based access, etc.)",
            "application/json",
        ),
        _resource(
            "dazzle://docs/workflows",
            "Workflow Guides",
            "Step-by-step guides for common tasks (getting_started, add_entity, add_workspace, etc.)",
            "application/json",
        ),
        _resource(
            "dazzle://user/profile",
            "User Profile",
            "Adaptive user profile with scored dimensions (technical depth, domain clarity, UX focus) and LLM guidance for adjusting communication register",
            "application/json",
        ),
    ]

    project_path = get_active_project_path()
    if project_path and (project_path / "dazzle.toml").exists():
        for r in create_resources(project_path):
            resources.append(
                _resource(
                    str(r["uri"]),
                    str(r["name"]),
                    str(r["description"]),
                    str(r.get("mimeType") or r.get("mime_type") or "text/plain"),
                )
            )
    return resources


async def _handle_list_resources(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListResourcesResult:
    del ctx, params
    return ListResourcesResult(resources=await list_resources_handler())


async def read_resource(uri: str) -> str:
    """Read a resource body by URI (public helper for tests)."""
    uri = str(uri)

    if uri == "dazzle://docs/glossary":
        return get_glossary()

    if uri == "dazzle://docs/quick-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        quick_ref = docs_dir / "DAZZLE_DSL_QUICK_REFERENCE.md"
        if quick_ref.exists():
            return quick_ref.read_text(encoding="utf-8")
        return "Quick reference not found"

    if uri == "dazzle://docs/dsl-reference":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        dsl_ref = docs_dir / "v0.2" / "DAZZLE_DSL_REFERENCE.md"
        if dsl_ref.exists():
            return dsl_ref.read_text(encoding="utf-8")
        return "DSL reference not found"

    if uri == "dazzle://docs/htmx-templates":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        htmx_spec = docs_dir / "reference" / "htmx-templates.md"
        if htmx_spec.exists():
            return htmx_spec.read_text(encoding="utf-8")
        return "HTMX template specification not found"

    if uri == "dazzle://docs/runtime-capabilities":
        docs_dir = Path(__file__).parent.parent.parent.parent / "docs"
        rt_caps = docs_dir / "reference" / "runtime-capabilities.md"
        if rt_caps.exists():
            return rt_caps.read_text(encoding="utf-8")
        return "Runtime capabilities specification not found"

    if uri == "dazzle://semantics/index":
        return json.dumps(get_semantic_index(), indent=2)

    if uri == "dazzle://examples/catalog":
        return json.dumps(get_example_metadata(), indent=2)

    if uri == "dazzle://docs/context":
        from dazzle.mcp.prompts import get_dazzle_context

        return get_dazzle_context()

    if uri == "dazzle://docs/patterns":
        return json.dumps(get_dsl_patterns(), indent=2)

    if uri == "dazzle://docs/workflows":
        from dazzle.mcp.cli_help import get_workflow_guide

        workflows = [
            "getting_started",
            "new_project",
            "add_entity",
            "add_workspace",
            "add_personas",
            "add_relationships",
            "add_attention_signals",
            "setup_testing",
            "troubleshoot",
        ]
        result = {name: get_workflow_guide(name) for name in workflows}
        return json.dumps(result, indent=2)

    if uri == "dazzle://user/profile":
        from dazzle.mcp.user_profile import load_profile, profile_to_context

        profile = load_profile()
        return json.dumps(profile_to_context(profile), indent=2)

    if uri.startswith("dazzle://project/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        if uri == "dazzle://project/manifest":
            manifest_path = project_path / "dazzle.toml"
            if manifest_path.exists():
                return manifest_path.read_text(encoding="utf-8")
            return "Manifest not found"

        if uri == "dazzle://modules":
            return list_modules(project_path)

        if uri == "dazzle://entities":
            return get_entities(project_path)

        if uri == "dazzle://surfaces":
            return get_surfaces(project_path)

    if uri.startswith("dazzle://dsl/"):
        project_path = get_active_project_path()
        if not project_path:
            return json.dumps({"error": "No active project"})

        file_path = uri.replace("dazzle://dsl/", "")
        dsl_file = project_path / file_path
        if dsl_file.exists():
            return dsl_file.read_text(encoding="utf-8")
        return f"DSL file not found: {file_path}"

    return f"Unknown resource: {uri}"


def _mime_for_uri(uri: str) -> str:
    if (
        uri.endswith(".json")
        or "/semantics/" in uri
        or uri.endswith("/patterns")
        or uri.endswith("/workflows")
        or uri.endswith("/catalog")
        or uri.endswith("/profile")
    ):
        return "application/json"
    if "glossary" in uri or "reference" in uri or "context" in uri or uri.endswith(".md"):
        return "text/markdown"
    return "text/plain"


async def _handle_read_resource(
    ctx: ServerRequestContext,
    params: ReadResourceRequestParams,
) -> ReadResourceResult:
    del ctx
    uri = str(params.uri)
    text = await read_resource(uri)
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri=uri,
                text=text,
                mime_type=_mime_for_uri(uri),
            )
        ]
    )


# ============================================================================
# Prompts
# ============================================================================


def _prompt_text(name: str, args: dict[str, str]) -> str:
    if name == "validate":
        return """Please validate the DAZZLE project:

1. Use the validate_dsl tool to check for syntax errors
2. Report any validation errors found
3. If valid, summarize the project structure (modules, entities, surfaces)"""

    if name == "review_dsl":
        aspect = args.get("aspect", "all")
        return f"""Please review the DAZZLE DSL focusing on: {aspect}

1. Read the DSL files using the dazzle://dsl/* resources
2. Analyze the design based on DAZZLE best practices
3. Check for:
   - Proper entity/surface naming conventions
   - CRUD pattern completeness
   - Appropriate use of personas and UX semantics
   - Security considerations (if aspect=security or all)
   - Performance implications (if aspect=performance or all)
4. Suggest specific improvements with examples"""

    if name == "code_review":
        stack = args.get("stack", "base")
        return f"""Please review the generated code for stack: {stack}

1. Use the build tool to generate code if not already built
2. Examine the generated code in build/{stack}/
3. Check for:
   - Code quality and best practices
   - Security vulnerabilities
   - Performance issues
   - Proper error handling
4. Suggest improvements"""

    if name == "suggest_surfaces":
        entity_name = args.get("entity_name", "")
        if not entity_name:
            return "Error: entity_name argument required"
        return f"""Please suggest surface definitions for the {entity_name} entity:

1. Use inspect_entity to examine the {entity_name} entity
2. Determine appropriate CRUD surfaces needed
3. Suggest UX semantics for each surface:
   - Purpose statement
   - Information needs (show, sort, filter, search)
   - Attention signals if applicable
   - Persona variants if needed
4. Provide complete DSL code for the suggested surfaces"""

    if name == "optimize_dsl":
        return """Please analyze the DSL and suggest optimizations:

1. Use analyze_patterns to detect CRUD and integration patterns
2. Look for:
   - Incomplete CRUD patterns
   - Redundant surface definitions
   - Missing persona variants
   - Opportunities for workspaces
   - Better use of UX semantics
3. Suggest specific DSL improvements with before/after examples"""

    if name == "getting_started":
        return """Help the user get started with DAZZLE:

1. Use get_workflow_guide("getting_started") to get the complete guide
2. Walk them through:
   - Creating a new project with `dazzle init`
   - Understanding the project structure
   - Writing their first entity and surface in DSL
   - Running with `dazzle serve`
3. Offer to help them customize the starter code for their use case
4. Point them to lookup_concept("patterns") for common patterns they can use"""

    if name == "napkin_to_app":
        spec_path = args.get("spec_path", "spec.md")
        return f"""Transform a narrative spec into a running DAZZLE application.

## Phase 1: Read and Understand

1. Read the spec file at: {spec_path}
2. This is a rough "napkin spec" from a founder - expect it to be incomplete

## Phase 2: Cognition Pass (REQUIRED before writing ANY DSL)

Run these spec_analyze operations in sequence:

1. `spec_analyze(operation="discover_entities", spec_text=<spec content>)`
   - Extracts nouns, relationships, user roles
   - Review output, remove false positives

2. `spec_analyze(operation="identify_lifecycles", spec_text=<spec>, entities=<from step 1>)`
   - Identifies state transitions for key entities
   - Not every entity needs a state machine

3. `spec_analyze(operation="extract_personas", spec_text=<spec>)`
   - Identifies user roles and their primary actions
   - Each persona should have a workspace

4. `spec_analyze(operation="surface_rules", spec_text=<spec>)`
   - Extracts business rules (fees, constraints, validations)
   - Translate to computed fields, invariants, or guards

5. `spec_analyze(operation="generate_questions", spec_text=<spec>, entities=<from step 1>)`
   - Surfaces genuine ambiguities
   - ASK THE USER these questions before proceeding

6. After getting answers: `spec_analyze(operation="refine_spec", spec_text=<spec>, answers=<user answers>)`
   - Produces structured refined spec

## Phase 3: DSL Generation

Use `knowledge(operation="concept", term=<construct>)` for syntax - NOT examples.

Generate in this order:
1. Module header (app name, description)
2. Entities (domain model)
3. State machines (attach to status fields)
4. Surfaces (CRUD views per entity)
5. Workspaces (group by persona)
6. Services (if external integrations needed)

After each major section: `dsl(operation="validate")`

## Phase 4: Refinement

1. `dsl(operation="lint", extended=true)` - catch issues
2. `story(operation="propose")` - verify coverage
3. `dazzle serve` - run the app

## Key Principles

- Do NOT anchor to examples - generate from first principles
- ASK clarifying questions - don't assume
- Validate incrementally - don't write 500 lines then validate
- Document decisions in the refined spec"""

    return f"Unknown prompt: {name}"


async def list_prompts() -> list[dict[str, Any]]:
    """List prompts as plain dicts (legacy helper / tests)."""
    from dazzle.mcp.prompts import create_prompts

    return create_prompts()


async def get_prompt(name: str, arguments: dict[str, str] | None = None) -> str:
    """Get prompt body text (legacy helper / tests)."""
    return _prompt_text(name, arguments or {})


async def _handle_list_prompts(
    ctx: ServerRequestContext,
    params: PaginatedRequestParams | None,
) -> ListPromptsResult:
    del ctx, params
    raw = await list_prompts()
    prompts: list[Prompt] = []
    for p in raw:
        args = [
            PromptArgument(
                name=str(a["name"]),
                description=str(a.get("description") or ""),
                required=bool(a.get("required", False)),
            )
            for a in (p.get("arguments") or [])
        ]
        prompts.append(
            Prompt(
                name=str(p["name"]),
                description=str(p.get("description") or ""),
                arguments=args or None,
            )
        )
    return ListPromptsResult(prompts=prompts)


async def _handle_get_prompt(
    ctx: ServerRequestContext,
    params: GetPromptRequestParams,
) -> GetPromptResult:
    del ctx
    args = {k: str(v) for k, v in (params.arguments or {}).items()}
    text = _prompt_text(params.name, args)
    return GetPromptResult(
        description=f"DAZZLE prompt: {params.name}",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=text),
            )
        ],
    )


# ============================================================================
# Server instance (SDK v2: handlers via constructor on_*)
# ============================================================================

# Cacheable list results (2026-07-28) — hosts may cache tool catalogs.
_CacheableMethod = Literal[
    "prompts/list",
    "resources/list",
    "resources/read",
    "resources/templates/list",
    "server/discover",
    "tools/list",
]


def _cache_hints() -> Mapping[_CacheableMethod, Any] | None:
    if CacheHint is None:
        return None
    return {
        "tools/list": CacheHint(ttl_ms=60_000),
        "resources/list": CacheHint(ttl_ms=30_000),
        "prompts/list": CacheHint(ttl_ms=60_000),
    }


server = Server(
    "dazzle",
    version=_dazzle_version,
    cache_hints=_cache_hints(),
    on_list_tools=_handle_list_tools,
    on_call_tool=_handle_call_tool,
    on_list_resources=_handle_list_resources,
    on_read_resource=_handle_read_resource,
    on_list_prompts=_handle_list_prompts,
    on_get_prompt=_handle_get_prompt,
)


# ============================================================================
# Server Entry Point
# ============================================================================


async def run_server(project_root: Path | None = None) -> None:
    """Run the DAZZLE MCP server over stdio."""
    if project_root:
        set_project_root(project_root)
        logger.info("Project root set to: %s", project_root)
    else:
        logger.info("Using default project root: %s", get_project_root())

    # Multi-session isolation (#1628): each process gets its own state under
    # .dazzle/mcp-sessions/<id>/ (app state handles, not protocol sessions).
    # Exclusive fcntl lock only when DAZZLE_MCP_SHARED=1 (legacy shared KG).
    from .mcp_session import (
        ensure_mcp_session_id,
        exclusive_lock_required,
        mcp_lock_path,
        mcp_shared_mode,
        mcp_state_dir,
    )
    from .process_lock import EXIT_LOCK_CONTENTION, ProcessLock, format_conflict_message

    root = get_project_root()
    session_id = ensure_mcp_session_id()
    state_dir = mcp_state_dir(root)
    state_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "MCP session=%s shared=%s state_dir=%s protocol=2026-07-28/sdk-v2",
        session_id,
        mcp_shared_mode(),
        state_dir,
    )

    lock: ProcessLock | None = None
    if exclusive_lock_required():
        lock = ProcessLock(root, lock_path=mcp_lock_path(root))
        conflict = lock.acquire()
        if conflict is not None:
            message = format_conflict_message(conflict, root)
            logger.error("MCP server already running:\n%s", message)
            print(message, file=sys.stderr)
            sys.exit(EXIT_LOCK_CONTENTION)

    init_dev_mode(root)

    if is_dev_mode():
        logger.info("Running in DEV MODE with %s example projects", len(get_available_projects()))
        logger.info("Available projects: %s", list(get_available_projects().keys()))
        from .state import get_active_project

        logger.info("Active project: %s", get_active_project())
    else:
        logger.info("Running in NORMAL MODE")

    init_knowledge_graph(root)
    logger.info("Knowledge graph initialized")

    from .state import init_activity_log

    init_activity_log(root)

    logger.info("Starting DAZZLE MCP server (SDK v2)...")
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("stdio transport established, running server...")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    except Exception as e:
        logger.exception("Server error: %s", e)
        raise
    finally:
        if lock is not None:
            lock.release()


class DazzleMCPServer:
    """Class-based entry point for the MCP server.

    Thin object wrapper over ``run_server`` for callers that prefer
    ``DazzleMCPServer(root).run()``.
    """

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    async def run(self) -> None:
        await run_server(self.project_root)


__all__ = [
    "server",
    "run_server",
    "DazzleMCPServer",
    "set_project_root",
    "get_project_root",
    "is_dev_mode",
    "get_active_project_path",
    "get_knowledge_graph",
    "init_dev_mode",
    "init_knowledge_graph",
    "call_tool",
    "list_tools_handler",
    "list_resources_handler",
    "read_resource",
    "list_prompts",
    "get_prompt",
]
