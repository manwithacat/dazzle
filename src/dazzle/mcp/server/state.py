"""
MCP Server state management.

This module contains the global server state and accessor functions
for project root, dev mode, active project management, and knowledge graph.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

    from dazzle.mcp.knowledge_graph import KnowledgeGraph
    from dazzle.mcp.server.activity_log import ActivityLog, ActivityStore

logger = logging.getLogger("dazzle.mcp")

# ============================================================================
# Server State
# ============================================================================

# Store project root (set during initialization)
_project_root: Path = Path.cwd()

# Dev mode state
_is_dev_mode: bool = False
_active_project: str | None = None  # Name of the active example project
_available_projects: dict[str, Path] = {}  # project_name -> project_path

# Knowledge graph state
_knowledge_graph: KnowledgeGraph | None = None
_graph_db_path: Path | None = None

# Activity log state
_activity_log: ActivityLog | None = None
_activity_store: ActivityStore | None = None


def set_project_root(path: Path) -> None:
    """Set the project root for the server."""
    global _project_root
    _project_root = path


def get_project_root() -> Path:
    """Get the current project root."""
    return _project_root


def is_dev_mode() -> bool:
    """Check if server is in dev mode."""
    return _is_dev_mode


def get_active_project() -> str | None:
    """Get the name of the active project."""
    return _active_project


def set_active_project(name: str | None) -> None:
    """Set the active project name."""
    global _active_project
    _active_project = name


def get_available_projects() -> dict[str, Path]:
    """Get the dictionary of available projects."""
    return _available_projects


def get_active_project_path() -> Path | None:
    """Get the path to the active project, or None if not set."""
    if not _is_dev_mode:
        return _project_root
    # In dev mode, prefer CWD if it has a dazzle.toml
    if (_project_root / "dazzle.toml").exists():
        return _project_root
    if _active_project and _active_project in _available_projects:
        return _available_projects[_active_project]
    return None


# Alias for backward compatibility
def get_project_path() -> Path | None:
    """Get the path to the current project. Alias for get_active_project_path."""
    return get_active_project_path()


def resolve_project_path(project_path: str | None = None) -> Path:
    """
    Resolve the project path from various sources.

    Priority:
    1. Explicit project_path parameter (if provided and valid)
    2. Active project path (in dev mode)
    3. Server's project root

    Args:
        project_path: Optional explicit path from tool arguments

    Returns:
        Resolved Path to the project directory

    Raises:
        ValueError: If the resolved path doesn't exist or isn't a valid project
    """
    # If explicit path provided, use it
    if project_path:
        path = Path(project_path).resolve()
        if not path.exists():
            raise ValueError(f"Project path does not exist: {path}")
        if not path.is_dir():
            raise ValueError(f"Project path is not a directory: {path}")
        # Check for dazzle.toml to confirm it's a valid project
        if not (path / "dazzle.toml").exists():
            raise ValueError(f"Not a valid Dazzle project (no dazzle.toml found): {path}")
        return path

    # Try active project path
    active_path = get_active_project_path()
    if active_path:
        return active_path

    # Fall back to project root
    return _project_root


# ============================================================================
# MCP Roots-based Resolution
# ============================================================================

# Cache: frozenset of root URIs -> resolved Path
_roots_cache: dict[frozenset[str], Path] = {}


def _path_from_file_uri(uri: str) -> Path | None:
    """Convert a file:// URI to a Path, or return None for non-file URIs."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


async def resolve_project_path_from_roots(
    session: ServerSession | None,
    explicit_path: str | None = None,
) -> Path:
    """Resolve project path using MCP client roots.

    Priority:
    1. Explicit project_path parameter (validated)
    2. Client workspace roots containing dazzle.toml (cached per root set)
    3. Active project path / server project root (existing fallback)

    Args:
        session: The MCP server session to query for roots.
        explicit_path: Optional explicit path from tool arguments.

    Returns:
        Resolved Path to the project directory.

    Raises:
        ValueError: If explicit_path is invalid.
    """
    # Explicit path takes priority — delegate to sync resolver
    if explicit_path:
        return resolve_project_path(explicit_path)

    # No session available — fall back to sync resolver
    if session is None:
        return resolve_project_path(None)

    # Try to get roots from the client
    try:
        roots_result = await session.list_roots()
        root_uris = frozenset(str(r.uri) for r in roots_result.roots)
    except Exception:
        logger.debug("list_roots() unavailable, falling back to default resolution")
        return resolve_project_path(None)

    # Check cache
    if root_uris in _roots_cache:
        return _roots_cache[root_uris]

    # Search roots for a dazzle.toml
    for root in roots_result.roots:
        path = _path_from_file_uri(str(root.uri))
        if path and path.is_dir() and (path / "dazzle.toml").exists():
            _roots_cache[root_uris] = path
            logger.info(f"Resolved project from MCP root: {path}")
            return path

    # No root had dazzle.toml — fall back
    fallback = resolve_project_path(None)
    _roots_cache[root_uris] = fallback
    return fallback


# ============================================================================
# Dev Mode Detection
# ============================================================================


def _detect_dev_environment(root: Path) -> bool:
    """
    Detect if we're running in the Dazzle development environment.

    Markers:
    - No dazzle.toml in root
    - Has src/dazzle/ directory (source code)
    - Has examples/ directory with projects
    - Has pyproject.toml with name containing "dazzle"
    """
    # If there's a dazzle.toml, it's a normal project
    if (root / "dazzle.toml").exists():
        return False

    # Check for dev environment markers
    has_src = (root / "src" / "dazzle").is_dir()
    has_examples = (root / "examples").is_dir()

    # Check pyproject.toml for dazzle package
    has_pyproject = False
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomllib

            data = tomllib.loads(pyproject_path.read_text())
            project_name = data.get("project", {}).get("name", "")
            has_pyproject = "dazzle" in project_name.lower()
        except Exception:
            pass

    return has_src and has_examples and has_pyproject


def _discover_example_projects(root: Path) -> dict[str, Path]:
    """Discover all example projects in the examples/ directory."""
    projects: dict[str, Path] = {}
    examples_dir = root / "examples"

    if not examples_dir.is_dir():
        return projects

    for item in examples_dir.iterdir():
        if item.is_dir():
            manifest_path = item / "dazzle.toml"
            if manifest_path.exists():
                projects[item.name] = item

    return projects


def init_dev_mode(root: Path) -> None:
    """Initialize dev mode state."""
    global _is_dev_mode, _available_projects, _active_project

    _is_dev_mode = _detect_dev_environment(root)

    if _is_dev_mode:
        _available_projects = _discover_example_projects(root)
        # Auto-select first project if available
        if _available_projects:
            _active_project = sorted(_available_projects.keys())[0]
            logger.info(f"Dev mode: auto-selected project '{_active_project}'")
        logger.info(f"Dev mode enabled with {len(_available_projects)} example projects")
    else:
        _available_projects = {}
        _active_project = None


# ============================================================================
# Knowledge Graph Management
# ============================================================================


def init_knowledge_graph(root: Path) -> None:
    """
    Initialize the knowledge graph for the server.

    In dev mode, uses the Dazzle source code as the graph source.
    In normal mode, uses the project's .dazzle directory.
    """
    global _knowledge_graph, _graph_db_path

    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    # Determine database path
    if _is_dev_mode:
        # Dev mode: store in Dazzle's .dazzle directory
        _graph_db_path = root / ".dazzle" / "knowledge_graph.db"
    else:
        # Normal mode: store in project's .dazzle directory
        _graph_db_path = root / ".dazzle" / "knowledge_graph.db"

    _graph_db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize the graph
    _knowledge_graph = KnowledgeGraph(_graph_db_path)
    logger.info(f"Knowledge graph initialized at: {_graph_db_path}")

    # Seed framework knowledge (concepts, patterns, inference triggers)
    from dazzle.mcp.knowledge_graph.seed import ensure_seeded

    seeded = ensure_seeded(_knowledge_graph)
    if seeded:
        logger.info("Framework knowledge seeded into knowledge graph")

    # Check if graph needs population with project data
    stats = _knowledge_graph.get_stats()
    # Count only non-framework entities to decide if auto-populate is needed
    framework_types = {"concept", "pattern", "inference"}
    project_entity_count = sum(
        count
        for etype, count in stats.get("entity_types", {}).items()
        if etype not in framework_types
    )
    if project_entity_count == 0:
        logger.info("Knowledge graph has no project data, auto-populating...")
        _auto_populate_graph(root)


def _auto_populate_graph(root: Path) -> None:
    """Auto-populate the knowledge graph from source code."""
    if _knowledge_graph is None:
        return

    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_knowledge_graph)

    # In dev mode, populate from src/
    if _is_dev_mode:
        src_path = root / "src"
        if src_path.exists():
            result = handlers.handle_auto_populate(
                root_path=str(src_path),
                max_files=1000,
            )
            logger.info(f"Auto-populated graph from {src_path}: {result}")
    else:
        # Normal mode: populate from project directory
        result = handlers.handle_auto_populate(
            root_path=str(root),
            max_files=500,
        )
        logger.info(f"Auto-populated graph from {root}: {result}")


def get_knowledge_graph() -> KnowledgeGraph | None:
    """Get the knowledge graph instance."""
    return _knowledge_graph


def get_graph_db_path() -> Path | None:
    """Get the path to the knowledge graph database."""
    return _graph_db_path


def reinit_knowledge_graph(project_root: Path) -> None:
    """
    Close the current KG and open a new per-project database.

    Used when switching projects to ensure isolation — each project
    gets its own knowledge_graph.db with framework + project data.
    """
    global _knowledge_graph, _graph_db_path

    from dazzle.mcp.knowledge_graph import KnowledgeGraph
    from dazzle.mcp.knowledge_graph.seed import ensure_seeded

    # Close existing DB (file-based connections are per-call, so just discard)
    _knowledge_graph = None

    # Open new per-project DB
    _graph_db_path = project_root / ".dazzle" / "knowledge_graph.db"
    _graph_db_path.parent.mkdir(parents=True, exist_ok=True)

    _knowledge_graph = KnowledgeGraph(_graph_db_path)
    logger.info(f"Knowledge graph re-initialized at: {_graph_db_path}")

    # Seed framework data (fast if already seeded — version check)
    ensure_seeded(_knowledge_graph)

    # Populate project DSL data
    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_knowledge_graph)
    result = handlers.handle_populate_from_appspec(project_path=str(project_root))
    logger.info(f"Populated KG from DSL for {project_root.name}: {result}")


# ============================================================================
# Activity Log Management
# ============================================================================


def init_activity_log(root: Path) -> None:
    """Initialize the activity log for the server.

    Creates a fresh log at ``{root}/.dazzle/mcp-activity.log``,
    clearing any stale entries from a previous session.
    Also initializes the SQLite-backed ActivityStore if the KG is available.
    """
    global _activity_log, _activity_store

    from dazzle.mcp.server.activity_log import ActivityLog

    log_path = root / ".dazzle" / "mcp-activity.log"
    _activity_log = ActivityLog(log_path)
    _activity_log.clear()  # Fresh log per server session
    logger.info("Activity log initialized at: %s", log_path)

    # Also init the SQLite-backed activity store
    init_activity_store(root)


def init_activity_store(root: Path) -> None:
    """Initialize the SQLite-backed activity store from the KG."""
    global _activity_store

    graph = _knowledge_graph
    if graph is None:
        logger.debug("KG not available, skipping ActivityStore init")
        return

    from dazzle.mcp.server.activity_log import ActivityStore

    try:
        project_name = root.name
        version: str | None = None
        try:
            from dazzle._version import get_version

            version = get_version()
        except Exception:
            pass

        session_id = graph.start_activity_session(
            project_name=project_name,
            project_path=str(root),
            version=version,
        )
        _activity_store = ActivityStore(graph, session_id)
        logger.info("Activity store initialized (session %s)", session_id[:8])
    except Exception:
        logger.debug("Failed to init ActivityStore", exc_info=True)
        _activity_store = None


def get_activity_log() -> ActivityLog | None:
    """Get the activity log instance."""
    return _activity_log


def get_activity_store() -> ActivityStore | None:
    """Get the SQLite-backed activity store instance."""
    return _activity_store


def init_browser_gate(max_concurrent: int | None = None) -> None:
    """Configure the global Playwright browser gate at server startup.

    Bounds the number of concurrent Chromium instances to prevent memory
    exhaustion when LLM agents trigger multiple browser operations in parallel.
    """
    from dazzle.testing.browser_gate import configure_browser_gate

    configure_browser_gate(max_concurrent=max_concurrent)
    logger.info(
        "Browser gate configured (max_concurrent=%s)",
        max_concurrent or "default",
    )


def refresh_knowledge_graph(root_path: str | None = None) -> dict[str, Any]:
    """
    Refresh the knowledge graph by re-populating from source.

    Args:
        root_path: Optional specific path to populate from

    Returns:
        Population statistics
    """
    if _knowledge_graph is None:
        return {"error": "Knowledge graph not initialized"}

    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_knowledge_graph)

    populate_path = root_path or str(_project_root)
    if _is_dev_mode and not root_path:
        populate_path = str(_project_root / "src")

    result = handlers.handle_auto_populate(
        root_path=populate_path,
        max_files=1000,
    )
    return result
