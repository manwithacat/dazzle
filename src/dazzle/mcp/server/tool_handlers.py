"""
MCP Server tool handler implementations.

This module contains the implementations for all MCP tools.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.patterns import detect_crud_patterns, detect_integration_patterns
from dazzle.mcp.cli_help import get_cli_help, get_workflow_guide
from dazzle.mcp.dnr_tools_impl import set_backend_spec
from dazzle.mcp.examples import search_examples
from dazzle.mcp.semantics import lookup_concept

from .state import (
    get_active_project,
    get_available_projects,
    get_project_root,
    is_dev_mode,
    set_active_project,
)

logger = logging.getLogger("dazzle.mcp")


# ============================================================================
# Dev Mode Tool Implementations
# ============================================================================


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
            }
        except Exception as e:
            project_info = {
                "name": name,
                "path": str(path),
                "active": is_active,
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


def load_backend_spec_for_project(project_path: Path) -> bool:
    """
    Load BackendSpec for a project to enable DNR tools.

    Args:
        project_path: Path to the project directory

    Returns:
        True if BackendSpec was successfully loaded, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from dazzle_dnr_back.converters import convert_appspec_to_backend

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

        # Convert to BackendSpec
        backend_spec = convert_appspec_to_backend(appspec)

        # Set the BackendSpec for DNR tools
        set_backend_spec(backend_spec.model_dump())

        logger.info(
            f"Loaded BackendSpec for {project_path.name}: "
            f"{len(backend_spec.entities)} entities, {len(backend_spec.services)} services"
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to load BackendSpec for {project_path}: {e}")
        return False


def select_project(args: dict[str, Any]) -> str:
    """Select an example project to work with."""
    if not is_dev_mode():
        return json.dumps(
            {
                "error": "Not in dev mode. This tool is only available in the Dazzle development environment."
            }
        )

    project_name = args.get("project_name")
    if not project_name:
        return json.dumps({"error": "project_name required"})

    available_projects = get_available_projects()
    if project_name not in available_projects:
        return json.dumps(
            {
                "error": f"Project '{project_name}' not found",
                "available_projects": list(available_projects.keys()),
            }
        )

    set_active_project(project_name)
    project_path = available_projects[project_name]

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

    # Auto-load BackendSpec for DNR tools
    backend_spec_loaded = load_backend_spec_for_project(project_path)
    if backend_spec_loaded:
        result["backend_spec"] = "loaded"
    else:
        result["backend_spec"] = "not loaded (DSL parse error or no entities)"

    return json.dumps(result, indent=2)


def get_active_project_info() -> str:
    """Get the currently selected project."""
    if not is_dev_mode():
        # In normal mode, return info about the project root
        project_root = get_project_root()
        manifest_path = project_root / "dazzle.toml"

        if manifest_path.exists():
            try:
                manifest = load_manifest(manifest_path)
                result: dict[str, Any] = {
                    "mode": "normal",
                    "project_root": str(project_root),
                    "manifest_name": manifest.name,
                    "version": manifest.version,
                }

                # Auto-load BackendSpec for DNR tools
                backend_spec_loaded = load_backend_spec_for_project(project_root)
                result["backend_spec"] = "loaded" if backend_spec_loaded else "not loaded"

                return json.dumps(result, indent=2)
            except Exception as e:
                return json.dumps(
                    {
                        "mode": "normal",
                        "project_root": str(project_root),
                        "error": f"Could not load manifest: {e}",
                    },
                    indent=2,
                )
        else:
            return json.dumps(
                {
                    "mode": "normal",
                    "project_root": str(project_root),
                    "error": "No dazzle.toml found",
                },
                indent=2,
            )

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

    try:
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
    except Exception as e:
        return json.dumps(
            {
                "mode": "dev",
                "active_project": active_project,
                "path": str(project_path),
                "error": f"Could not load manifest: {e}",
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


# ============================================================================
# Project Tool Implementations
# ============================================================================


def validate_dsl(project_root: Path) -> str:
    """Validate DSL files in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        result = {
            "status": "valid",
            "modules": len(modules),
            "entities": len(app_spec.domain.entities),
            "surfaces": len(app_spec.surfaces),
            "apis": len(app_spec.apis),
        }

        # Add project context in dev mode
        if is_dev_mode():
            result["project"] = get_active_project()
            result["path"] = str(project_root)

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, indent=2)


def list_modules(project_root: Path) -> str:
    """List all modules in the project."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        parsed_modules = parse_modules(dsl_files)

        modules = {}
        for idx, module in enumerate(parsed_modules):
            modules[module.name] = {
                "file": str(dsl_files[idx].relative_to(project_root)),
                "dependencies": module.uses,
            }

        return json.dumps(modules, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    entity_name = args.get("entity_name")
    if not entity_name:
        return json.dumps({"error": "entity_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
        if not entity:
            return json.dumps({"error": f"Entity '{entity_name}' not found"})

        return json.dumps(
            {
                "name": entity.name,
                "description": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind),
                        "required": f.is_required,
                        "modifiers": [str(m) for m in f.modifiers],
                    }
                    for f in entity.fields
                ],
                "constraints": [str(c) for c in entity.constraints] if entity.constraints else [],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def inspect_surface(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a surface definition."""
    surface_name = args.get("surface_name")
    if not surface_name:
        return json.dumps({"error": "surface_name required"})

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
        if not surface:
            return json.dumps({"error": f"Surface '{surface_name}' not found"})

        return json.dumps(
            {
                "name": surface.name,
                "entity": surface.entity_ref,
                "mode": str(surface.mode),
                "description": surface.title,
                "sections": len(surface.sections) if surface.sections else 0,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def analyze_patterns(project_root: Path) -> str:
    """Analyze the project for patterns."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        crud_patterns = detect_crud_patterns(app_spec)
        integration_patterns = detect_integration_patterns(app_spec)

        return json.dumps(
            {
                "crud_patterns": [
                    {
                        "entity": p.entity_name,
                        "has_create": p.has_create,
                        "has_list": p.has_list,
                        "has_detail": p.has_detail,
                        "has_edit": p.has_edit,
                        "is_complete": p.is_complete,
                        "missing_operations": p.missing_operations,
                    }
                    for p in crud_patterns
                ],
                "integration_patterns": [
                    {
                        "name": p.integration_name,
                        "service": p.service_name,
                        "has_actions": p.has_actions,
                        "has_syncs": p.has_syncs,
                        "action_count": p.action_count,
                        "sync_count": p.sync_count,
                        "connected_entities": list(p.connected_entities or []),
                        "connected_surfaces": list(p.connected_surfaces or []),
                    }
                    for p in integration_patterns
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def lint_project(project_root: Path, args: dict[str, Any]) -> str:
    """Run linting on the project."""
    extended = args.get("extended", False)

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        warnings, _ = lint_appspec(app_spec, extended=extended)

        return json.dumps(
            {"warnings": len(warnings), "issues": [str(w) for w in warnings]},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Semantic Lookup Tool Implementations
# ============================================================================


def lookup_concept_handler(args: dict[str, Any]) -> str:
    """Look up a DAZZLE DSL concept."""
    term = args.get("term")
    if not term:
        return json.dumps({"error": "term parameter required"})

    result = lookup_concept(term)
    return json.dumps(result, indent=2)


def find_examples_handler(args: dict[str, Any]) -> str:
    """Find example projects by features or complexity."""
    features = args.get("features")
    complexity = args.get("complexity")

    results = search_examples(features=features, complexity=complexity)

    return json.dumps(
        {
            "query": {
                "features": features,
                "complexity": complexity,
            },
            "count": len(results),
            "examples": results,
        },
        indent=2,
    )


def get_cli_help_handler(args: dict[str, Any]) -> str:
    """Get CLI help for a command."""
    command = args.get("command")
    result = get_cli_help(command)
    return json.dumps(result, indent=2)


def get_workflow_guide_handler(args: dict[str, Any]) -> str:
    """Get workflow guide."""
    workflow = args.get("workflow")
    if not workflow:
        return json.dumps({"error": "workflow parameter required"})

    result = get_workflow_guide(workflow)
    return json.dumps(result, indent=2)


# ============================================================================
# Data Extraction Helpers
# ============================================================================


def get_entities(project_path: Path) -> str:
    """Get all entity definitions from project."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

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
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_surfaces(project_path: Path) -> str:
    """Get all surface definitions from project."""
    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

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
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
