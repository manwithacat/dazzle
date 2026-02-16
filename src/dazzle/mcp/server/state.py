"""
MCP Server state management.

This module contains the global server state and accessor functions
for project root, dev mode, active project management, and knowledge graph.
"""

from __future__ import annotations

import logging
import sys
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

from dazzle.mcp.server.paths import (
    project_activity_log,
    project_kg_db,
    project_manifest,
)

if TYPE_CHECKING:
    from mcp.server.session import ServerSession

    from dazzle.mcp.knowledge_graph import KnowledgeGraph
    from dazzle.mcp.server.activity_log import ActivityLog, ActivityStore

logger = logging.getLogger("dazzle.mcp")


# ============================================================================
# Centralized Server State
# ============================================================================


class ServerState:
    """Centralized MCP server state.

    Holds all mutable server state as instance attributes instead of
    scattered module-level globals.  A single module-level instance
    ``_state`` is created and all existing public functions delegate to it,
    so callers are unaffected.
    """

    _ROOTS_CACHE_MAX = 128

    def __init__(self) -> None:
        self.project_root: Path = Path.cwd()
        self.is_dev_mode: bool = False
        self.active_project: str | None = None
        self.available_projects: dict[str, Path] = {}
        self.knowledge_graph: KnowledgeGraph | None = None
        self.graph_db_path: Path | None = None
        self.activity_log: ActivityLog | None = None
        self.activity_store: ActivityStore | None = None
        self._roots_cache: dict[frozenset[str], Path] = {}

    def reset(self) -> None:
        """Reset all state to defaults."""
        self.project_root = Path.cwd()
        self.is_dev_mode = False
        self.active_project = None
        self.available_projects.clear()
        self.knowledge_graph = None
        self.graph_db_path = None
        self.activity_log = None
        self.activity_store = None
        self._roots_cache.clear()

    # -- roots cache with bounded size ------------------------------------

    def roots_cache_get(self, key: frozenset[str]) -> Path | None:
        """Look up a cached root resolution."""
        return self._roots_cache.get(key)

    def roots_cache_set(self, key: frozenset[str], value: Path) -> None:
        """Store a root resolution, evicting oldest if cache is full."""
        if len(self._roots_cache) >= self._ROOTS_CACHE_MAX:
            # Evict the first (oldest-inserted) entry
            oldest = next(iter(self._roots_cache))
            del self._roots_cache[oldest]
        self._roots_cache[key] = value


# Module-level singleton holding all mutable MCP server state.
# Designed for single-threaded asyncio use — not thread-safe.
# Accessed via the public functions below; tests may call ``reset_state()``
# to get a clean instance.
_state = ServerState()


# ============================================================================
# Public accessor functions (signatures unchanged)
# ============================================================================


def reset_state() -> None:
    """Reset server state to initial values. Primarily for testing."""
    global _state
    _state = ServerState()


def set_project_root(path: Path) -> None:
    """Set the project root for the server."""
    _state.project_root = path


def get_project_root() -> Path:
    """Get the current project root."""
    return _state.project_root


def is_dev_mode() -> bool:
    """Check if server is in dev mode."""
    return _state.is_dev_mode


def get_active_project() -> str | None:
    """Get the name of the active project."""
    return _state.active_project


def set_active_project(name: str | None) -> None:
    """Set the active project name."""
    _state.active_project = name


def get_available_projects() -> dict[str, Path]:
    """Get the dictionary of available projects."""
    return _state.available_projects


def get_active_project_path() -> Path | None:
    """Get the path to the active project, or None if not set."""
    if not _state.is_dev_mode:
        return _state.project_root
    # In dev mode, prefer CWD if it has a dazzle.toml
    if project_manifest(_state.project_root).exists():
        return _state.project_root
    if _state.active_project and _state.active_project in _state.available_projects:
        return _state.available_projects[_state.active_project]
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
        if not project_manifest(path).exists():
            raise ValueError(f"Not a valid Dazzle project (no dazzle.toml found): {path}")
        return path

    # Try active project path
    active_path = get_active_project_path()
    if active_path:
        return active_path

    # Fall back to project root
    return _state.project_root


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
    cached = _state.roots_cache_get(root_uris)
    if cached is not None:
        return cached

    # Search roots for a dazzle.toml
    for root in roots_result.roots:
        path = _path_from_file_uri(str(root.uri))
        if path and path.is_dir() and project_manifest(path).exists():
            _state.roots_cache_set(root_uris, path)
            logger.info(f"Resolved project from MCP root: {path}")
            return path

    # No root had dazzle.toml — fall back
    fallback = resolve_project_path(None)
    _state.roots_cache_set(root_uris, fallback)
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
    if project_manifest(root).exists():
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
            logger.debug("Failed to parse pyproject.toml", exc_info=True)

    return has_src and has_examples and has_pyproject


def _discover_example_projects(root: Path) -> dict[str, Path]:
    """Discover all example projects in the examples/ directory."""
    projects: dict[str, Path] = {}
    examples_dir = root / "examples"

    if not examples_dir.is_dir():
        return projects

    for item in examples_dir.iterdir():
        if item.is_dir():
            manifest_path = project_manifest(item)
            if manifest_path.exists():
                projects[item.name] = item

    return projects


def init_dev_mode(root: Path) -> None:
    """Initialize dev mode state."""
    _state.is_dev_mode = _detect_dev_environment(root)

    if _state.is_dev_mode:
        _state.available_projects = _discover_example_projects(root)
        # Auto-select first project if available
        if _state.available_projects:
            _state.active_project = sorted(_state.available_projects.keys())[0]
            logger.info(f"Dev mode: auto-selected project '{_state.active_project}'")
        logger.info(f"Dev mode enabled with {len(_state.available_projects)} example projects")
    else:
        _state.available_projects = {}
        _state.active_project = None


# ============================================================================
# Knowledge Graph Management
# ============================================================================


def init_knowledge_graph(root: Path) -> None:
    """
    Initialize the knowledge graph for the server.

    In dev mode, uses the Dazzle source code as the graph source.
    In normal mode, uses the project's .dazzle directory.
    """
    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    # Determine database path
    if _state.is_dev_mode:
        # Dev mode: store in Dazzle's .dazzle directory
        _state.graph_db_path = project_kg_db(root)
    else:
        # Normal mode: store in project's .dazzle directory
        _state.graph_db_path = project_kg_db(root)

    _state.graph_db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize the graph
    _state.knowledge_graph = KnowledgeGraph(_state.graph_db_path)
    logger.info(f"Knowledge graph initialized at: {_state.graph_db_path}")

    # Seed framework knowledge (concepts, patterns, inference triggers)
    from dazzle.mcp.knowledge_graph.seed import ensure_seeded

    seeded = ensure_seeded(_state.knowledge_graph)
    if seeded:
        logger.info("Framework knowledge seeded into knowledge graph")

    # Check if graph needs population with project data
    stats = _state.knowledge_graph.get_stats()
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
    if _state.knowledge_graph is None:
        return

    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_state.knowledge_graph)

    # In dev mode, populate from src/
    if _state.is_dev_mode:
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
    return _state.knowledge_graph


def get_graph_db_path() -> Path | None:
    """Get the path to the knowledge graph database."""
    return _state.graph_db_path


def reinit_knowledge_graph(project_root: Path) -> None:
    """
    Close the current KG and open a new per-project database.

    Used when switching projects to ensure isolation — each project
    gets its own knowledge_graph.db with framework + project data.
    """
    from dazzle.mcp.knowledge_graph import KnowledgeGraph
    from dazzle.mcp.knowledge_graph.seed import ensure_seeded

    # Close existing DB (file-based connections are per-call, so just discard)
    _state.knowledge_graph = None

    # Open new per-project DB
    _state.graph_db_path = project_kg_db(project_root)
    _state.graph_db_path.parent.mkdir(parents=True, exist_ok=True)

    _state.knowledge_graph = KnowledgeGraph(_state.graph_db_path)
    logger.info(f"Knowledge graph re-initialized at: {_state.graph_db_path}")

    # Seed framework data (fast if already seeded — version check)
    ensure_seeded(_state.knowledge_graph)

    # Populate project DSL data
    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_state.knowledge_graph)
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
    from dazzle.mcp.server.activity_log import ActivityLog

    log_path = project_activity_log(root)
    _state.activity_log = ActivityLog(log_path)
    _state.activity_log.clear()  # Fresh log per server session
    logger.info("Activity log initialized at: %s", log_path)

    # Also init the SQLite-backed activity store
    init_activity_store(root)


def init_activity_store(root: Path) -> None:
    """Initialize the SQLite-backed activity store from the KG."""
    graph = _state.knowledge_graph
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
            logger.debug("Failed to get version for activity session", exc_info=True)

        session_id = graph.start_activity_session(
            project_name=project_name,
            project_path=str(root),
            version=version,
        )
        _state.activity_store = ActivityStore(graph, session_id)
        logger.info("Activity store initialized (session %s)", session_id[:8])
    except Exception:
        logger.debug("Failed to init ActivityStore", exc_info=True)
        _state.activity_store = None


def get_activity_log() -> ActivityLog | None:
    """Get the activity log instance."""
    return _state.activity_log


def get_activity_store() -> ActivityStore | None:
    """Get the SQLite-backed activity store instance."""
    return _state.activity_store


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
    if _state.knowledge_graph is None:
        return {"error": "Knowledge graph not initialized"}

    from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers

    handlers = KnowledgeGraphHandlers(_state.knowledge_graph)

    populate_path = root_path or str(_state.project_root)
    if _state.is_dev_mode and not root_path:
        populate_path = str(_state.project_root / "src")

    result = handlers.handle_auto_populate(
        root_path=populate_path,
        max_files=1000,
    )
    return result


# ============================================================================
# Backward-compatible module proxy
# ============================================================================
#
# Some callers (tests) access old module-level globals like
# ``state._knowledge_graph`` directly.  The mapping below lets reads
# and writes of the old names proxy through to ``_state`` attributes.

_LEGACY_ATTR_MAP: dict[str, str] = {
    "_project_root": "project_root",
    "_is_dev_mode": "is_dev_mode",
    "_active_project": "active_project",
    "_available_projects": "available_projects",
    "_knowledge_graph": "knowledge_graph",
    "_graph_db_path": "graph_db_path",
    "_activity_log": "activity_log",
    "_activity_store": "activity_store",
    "_roots_cache": "_roots_cache",
}


class _StateModule(types.ModuleType):
    """Module subclass that proxies legacy global attribute names to ``_state``.

    Why: Several callers (especially tests) historically accessed module-level
    globals like ``state._knowledge_graph`` directly.  Rather than updating
    every call-site, this proxy intercepts ``__getattr__`` / ``__setattr__``
    and forwards reads/writes of the old underscore-prefixed names to the
    corresponding attributes on the ``_state`` singleton.  This keeps the
    module importable as ``from dazzle.mcp.server import state; state.X``
    while centralising mutable state inside ``ServerState``.
    """

    def __getattr__(self, name: str) -> Any:
        mapped = _LEGACY_ATTR_MAP.get(name)
        if mapped is not None:
            return getattr(_state, mapped)
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        mapped = _LEGACY_ATTR_MAP.get(name)
        if mapped is not None:
            setattr(_state, mapped, value)
        else:
            super().__setattr__(name, value)


# Replace this module in sys.modules so attribute access is intercepted.
_mod = _StateModule(__name__)
_mod.__dict__.update({k: v for k, v in sys.modules[__name__].__dict__.items() if k != "__class__"})
sys.modules[__name__] = _mod
