"""
Resource definitions for DAZZLE MCP server.

Resources are data sources that Claude Code can reference using @server:uri syntax.
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

logger = logging.getLogger(__name__)


def create_resources(project_root: Path) -> list[dict[str, Any]]:
    """
    Create available resources for the MCP server.

    Args:
        project_root: Path to the DAZZLE project root

    Returns:
        List of resource definitions with URI, name, and description
    """
    # Project-specific resources only (static resources are added by the server)
    resources: list[dict[str, Any]] = [
        {
            "uri": "dazzle://project/manifest",
            "name": "Project Manifest",
            "description": "dazzle.toml project configuration",
            "mimeType": "text/plain",
        },
        {
            "uri": "dazzle://modules",
            "name": "Project Modules",
            "description": "List of all modules and their dependencies",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://entities",
            "name": "Project Entities",
            "description": "All entity definitions in the project",
            "mimeType": "application/json",
        },
        {
            "uri": "dazzle://surfaces",
            "name": "Project Surfaces",
            "description": "All surface definitions in the project",
            "mimeType": "application/json",
        },
    ]

    # Add DSL file resources
    dsl_dir = project_root / "dsl"
    if dsl_dir.exists():
        for dsl_file in dsl_dir.glob("**/*.dsl"):
            relative_path = dsl_file.relative_to(project_root)
            resources.append(
                {
                    "uri": f"dazzle://dsl/{relative_path}",
                    "name": f"DSL: {dsl_file.stem}",
                    "description": f"DSL file: {relative_path}",
                    "mimeType": "text/plain",
                }
            )

    return resources


def _json_error_on_failure(fn: Callable[[Path], str]) -> Callable[[Path], str]:
    """Return ``{"error": ...}`` JSON instead of raising (resource reads never raise)."""

    @wraps(fn)
    def wrapper(project_path: Path) -> str:
        try:
            return fn(project_path)
        except Exception as e:
            logger.debug("Resource reader %s failed: %s", fn.__name__, e, exc_info=True)
            return json.dumps({"error": str(e)}, indent=2)

    return wrapper


@_json_error_on_failure
def list_modules(project_root: Path) -> str:
    """List all modules in the project."""
    manifest = load_manifest(project_root / "dazzle.toml")
    dsl_files = discover_dsl_files(project_root, manifest)
    parsed_modules = parse_modules(dsl_files)

    modules = {}
    for idx, module in enumerate(parsed_modules):
        modules[module.name] = {
            "file": str(dsl_files[idx].relative_to(project_root)),
            "dependencies": module.uses,
        }

    return json.dumps({"project_path": str(project_root), "modules": modules}, indent=2)


@_json_error_on_failure
def get_entities(project_path: Path) -> str:
    """Get all entity definitions from project."""
    app_spec = load_project_appspec(project_path)

    entities = {}
    for entity in app_spec.domain.entities:
        entities[entity.name] = {
            "name": entity.name,
            "title": entity.title,
            "fields": [
                {
                    "name": f.name,
                    "type": str(f.type),
                    "required": f.is_required,
                    "unique": f.is_unique,
                    "is_pk": f.is_primary_key,
                }
                for f in entity.fields
            ],
        }

    return json.dumps(entities, indent=2)


@_json_error_on_failure
def get_surfaces(project_path: Path) -> str:
    """Get all surface definitions from project."""
    app_spec = load_project_appspec(project_path)

    surfaces = {}
    for surface in app_spec.surfaces:
        surfaces[surface.name] = {
            "name": surface.name,
            "title": surface.title,
            "mode": surface.mode,
            "entity": surface.entity_ref,
            "has_ux": surface.ux is not None,
        }

    return json.dumps(surfaces, indent=2)
