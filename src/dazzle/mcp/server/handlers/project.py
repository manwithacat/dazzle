"""
Project management tool handlers.

Handles project listing, selection, validation, and dev mode operations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.mcp.runtime_tools import set_appspec_data

from ..state import (
    get_active_project,
    get_available_projects,
    get_project_root,
    is_dev_mode,
    set_active_project,
)
from .common import error_response, extract_progress

logger = logging.getLogger("dazzle.mcp")


def list_projects() -> str:
    """List all available example projects."""
    if not is_dev_mode():
        return json.dumps(
            {
                "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
            }
        )

    available_projects = get_available_projects()
    active_project = get_active_project()
    projects = []

    for name, path in sorted(available_projects.items()):
        is_active = name == active_project

        # Try to get project info
        try:
            manifest = load_manifest(path / "dazzle.toml")
            project_info = {
                "name": name,
                "path": str(path),
                "active": is_active,
                "manifest_name": manifest.name,
                "version": manifest.version,
                "type": manifest.project_type,  # example | benchmark | test | internal
            }
        except Exception as e:
            project_info = {
                "name": name,
                "path": str(path),
                "active": is_active,
                "type": "unknown",
                "error": str(e),
            }

        projects.append(project_info)

    return json.dumps(
        {
            "mode": "dev",
            "project_count": len(projects),
            "active_project": active_project,
            "projects": projects,
        },
        indent=2,
    )


def load_appspec_for_project(project_path: Path) -> bool:
    """
    Load AppSpec for a project to enable DNR tools.

    Args:
        project_path: Path to the project directory

    Returns:
        True if AppSpec was successfully loaded, False otherwise
    """
    try:
        # Load manifest first
        manifest_path = project_path / "dazzle.toml"
        if not manifest_path.exists():
            logger.warning(f"No dazzle.toml found in {project_path}")
            return False

        manifest = load_manifest(manifest_path)

        # Discover and parse DSL files
        dsl_files = discover_dsl_files(project_path, manifest)
        if not dsl_files:
            logger.warning(f"No DSL files found in {project_path}")
            return False

        # Parse modules
        modules = parse_modules(dsl_files)
        if not modules:
            logger.warning(f"No modules parsed from {project_path}")
            return False

        # Build AppSpec
        appspec = build_appspec(modules, manifest.project_root)
        if not appspec.domain.entities:
            logger.warning(f"No entities found in {project_path}")
            return False

        # Store AppSpec data for DNR tools
        set_appspec_data(appspec.model_dump())

        logger.info(
            f"Loaded AppSpec for {project_path.name}: "
            f"{len(appspec.domain.entities)} entities, {len(appspec.surfaces)} surfaces"
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to load AppSpec for {project_path}: {e}")
        return False


def select_project(args: dict[str, Any]) -> str:
    """Select an example project to work with."""
    progress = extract_progress(args)
    progress.log_sync("Selecting project...")
    if not is_dev_mode():
        return json.dumps(
            {
                "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
            }
        )

    project_name = args.get("project_name")
    if not project_name:
        return error_response("project_name required")

    available_projects = get_available_projects()

    # Support absolute paths to external projects
    if project_name not in available_projects:
        candidate = Path(project_name)
        if candidate.is_absolute() and (candidate / "dazzle.toml").is_file():
            # Register the external project so it persists for the session
            resolved_name = candidate.name
            available_projects[resolved_name] = candidate
            project_name = resolved_name
        else:
            return json.dumps(
                {
                    "error": f"Project '{project_name}' not found. Pass an absolute path to an external project directory containing dazzle.toml.",
                    "available_projects": list(available_projects.keys()),
                }
            )

    set_active_project(project_name)
    project_path = available_projects[project_name]

    # Re-initialize knowledge graph for the new project (isolation fix)
    try:
        from ..state import reinit_knowledge_graph

        reinit_knowledge_graph(project_path)
    except Exception as e:
        logger.warning(f"Failed to reinit knowledge graph for {project_name}: {e}")

    # Return info about the selected project
    result: dict[str, Any] = {
        "status": "selected",
        "project": project_name,
        "path": str(project_path),
    }

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        result["manifest_name"] = manifest.name
        result["version"] = manifest.version
    except Exception as e:
        result["warning"] = f"Could not load manifest: {e}"

    # Auto-load AppSpec for DNR tools
    appspec_loaded = load_appspec_for_project(project_path)
    if appspec_loaded:
        result["appspec"] = "loaded"
    else:
        result["appspec"] = "not loaded (DSL parse error or no entities)"

    return json.dumps(result, indent=2)


def get_active_project_info(resolved_path: Path | None = None) -> str:
    """Get the currently selected project.

    Args:
        resolved_path: If provided (from MCP roots resolution), use this path
            instead of internal state when it contains a dazzle.toml.
    """
    # If we have a roots-resolved path with a manifest, use it directly
    if resolved_path is not None and (resolved_path / "dazzle.toml").exists():
        manifest = load_manifest(resolved_path / "dazzle.toml")
        result: dict[str, Any] = {
            "mode": "dev" if is_dev_mode() else "normal",
            "project_root": str(resolved_path),
            "manifest_name": manifest.name,
            "version": manifest.version,
        }

        appspec_loaded = load_appspec_for_project(resolved_path)
        result["appspec"] = "loaded" if appspec_loaded else "not loaded"

        return json.dumps(result, indent=2)

    if not is_dev_mode():
        # In normal mode, return info about the project root
        project_root = get_project_root()
        manifest_path = project_root / "dazzle.toml"

        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            result = {
                "mode": "normal",
                "project_root": str(project_root),
                "manifest_name": manifest.name,
                "version": manifest.version,
            }

            # Auto-load AppSpec for DNR tools
            appspec_loaded = load_appspec_for_project(project_root)
            result["appspec"] = "loaded" if appspec_loaded else "not loaded"

            return json.dumps(result, indent=2)
        else:
            return json.dumps(
                {
                    "mode": "normal",
                    "project_root": str(project_root),
                    "error": "No dazzle.toml found",
                },
                indent=2,
            )

    # In dev mode, check if CWD has a dazzle.toml first
    project_root = get_project_root()
    cwd_manifest = project_root / "dazzle.toml"
    if cwd_manifest.exists():
        manifest = load_manifest(cwd_manifest)
        result = {
            "mode": "dev",
            "source": "cwd",
            "project_root": str(project_root),
            "manifest_name": manifest.name,
            "version": manifest.version,
        }

        appspec_loaded = load_appspec_for_project(project_root)
        result["appspec"] = "loaded" if appspec_loaded else "not loaded"

        return json.dumps(result, indent=2)

    active_project = get_active_project()
    available_projects = get_available_projects()

    if active_project is None:
        return json.dumps(
            {
                "mode": "dev",
                "active_project": None,
                "message": "No project selected. Use 'select_project' to choose one.",
                "available_projects": list(available_projects.keys()),
            },
            indent=2,
        )

    project_path = available_projects.get(active_project)
    if project_path is None:
        return json.dumps(
            {
                "mode": "dev",
                "error": f"Active project '{active_project}' not found",
            },
            indent=2,
        )

    manifest = load_manifest(project_path / "dazzle.toml")
    return json.dumps(
        {
            "mode": "dev",
            "active_project": active_project,
            "path": str(project_path),
            "manifest_name": manifest.name,
            "version": manifest.version,
        },
        indent=2,
    )


def validate_all_projects() -> str:
    """Validate all example projects."""
    if not is_dev_mode():
        return json.dumps(
            {
                "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
            }
        )

    available_projects = get_available_projects()
    results = {}

    for name, path in sorted(available_projects.items()):
        try:
            manifest = load_manifest(path / "dazzle.toml")
            dsl_files = discover_dsl_files(path, manifest)
            modules = parse_modules(dsl_files)
            app_spec = build_appspec(modules, manifest.project_root)

            results[name] = {
                "status": "valid",
                "modules": len(modules),
                "entities": len(app_spec.domain.entities),
                "surfaces": len(app_spec.surfaces),
                "apis": len(app_spec.apis),
            }
        except Exception as e:
            results[name] = {
                "status": "error",
                "error": str(e),
            }

    # Summary
    valid_count = sum(1 for r in results.values() if r["status"] == "valid")
    error_count = sum(1 for r in results.values() if r["status"] == "error")

    return json.dumps(
        {
            "summary": {
                "total": len(results),
                "valid": valid_count,
                "errors": error_count,
            },
            "projects": results,
        },
        indent=2,
    )
