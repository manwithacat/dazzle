"""
MCP Server state management.

This module contains the global server state and accessor functions
for project root, dev mode, and active project management.
"""

from __future__ import annotations

import logging
from pathlib import Path

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
    if _active_project and _active_project in _available_projects:
        return _available_projects[_active_project]
    return None


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
