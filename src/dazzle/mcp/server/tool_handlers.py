"""
MCP Server tool handler implementations.

This module contains the implementations for all MCP tools.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC
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
from dazzle.mcp.inference import list_all_patterns, lookup_inference
from dazzle.mcp.semantics import get_mcp_version, lookup_concept

from .state import (
    get_active_project,
    get_active_project_path,
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

        result: dict[str, Any] = {
            "status": "valid",
            "project_path": str(project_root),
            "modules": len(modules),
            "entities": len(app_spec.domain.entities),
            "surfaces": len(app_spec.surfaces),
            "apis": len(app_spec.apis),
        }

        # Add project context in dev mode
        if is_dev_mode():
            result["project"] = get_active_project()

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps(
            {"status": "error", "project_path": str(project_root), "error": str(e)},
            indent=2,
        )


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

        return json.dumps({"project_path": str(project_root), "modules": modules}, indent=2)
    except Exception as e:
        return json.dumps({"project_path": str(project_root), "error": str(e)}, indent=2)


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


def lookup_inference_handler(args: dict[str, Any]) -> str:
    """Search the inference knowledge base for DSL generation patterns."""
    list_all = args.get("list_all", False)

    if list_all:
        result = list_all_patterns()
        return json.dumps(result, indent=2)

    query = args.get("query")
    if not query:
        return json.dumps(
            {
                "error": "Either 'query' parameter or 'list_all: true' is required",
                "hint": "Use 'query' with keywords from your SPEC, or 'list_all: true' to see trigger keywords",
            }
        )

    detail = args.get("detail", "minimal")
    if detail not in ("minimal", "full"):
        detail = "minimal"

    result = lookup_inference(query, detail=detail)
    return json.dumps(result, indent=2)


# ============================================================================
# Internal/Development Tools
# ============================================================================


def get_mcp_status_handler(args: dict[str, Any]) -> str:
    """Get MCP server status and optionally reload modules."""

    reload_requested = args.get("reload", False)
    result: dict[str, Any] = {
        "mode": "dev" if is_dev_mode() else "normal",
        "project_root": str(get_project_root()),
    }

    # Get current version info
    version_info = get_mcp_version()
    result["semantics_version"] = version_info

    if reload_requested:
        if not is_dev_mode():
            result["reload"] = "skipped - only available in dev mode"
        else:
            # Reload the semantics data from TOML files
            try:
                from dazzle.mcp.semantics_kb import reload_cache

                reload_cache()

                # Get the new version after reload
                from dazzle.mcp.semantics import get_mcp_version as new_get_version

                new_version_info = new_get_version()
                result["reload"] = "success"
                result["new_semantics_version"] = new_version_info

            except Exception as e:
                result["reload"] = f"failed: {e}"

    # Add active project info in dev mode
    if is_dev_mode():
        result["active_project"] = get_active_project()
        result["available_projects"] = list(get_available_projects().keys())

    return json.dumps(result, indent=2)


# ============================================================================
# DNR Logging Tools
# ============================================================================


def get_dnr_logs_handler(args: dict[str, Any]) -> str:
    """Get DNR runtime logs for debugging."""
    count = args.get("count", 50)
    level = args.get("level")
    errors_only = args.get("errors_only", False)

    # Get project path
    project_path = get_active_project_path() or get_project_root()
    log_dir = project_path / ".dazzle" / "logs"
    log_file = log_dir / "dnr.log"

    result: dict[str, Any] = {
        "log_file": str(log_file),
        "project": str(project_path),
    }

    if not log_file.exists():
        result["status"] = "no_logs"
        result["message"] = (
            "No log file found. Start the DNR server with `dazzle dnr serve` to generate logs."
        )
        result["hint"] = f"Log file will be created at: {log_file}"
        return json.dumps(result, indent=2)

    try:
        entries: list[dict[str, Any]] = []
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if level and entry.get("level") != level.upper():
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue

        if errors_only:
            # Return error summary
            errors = [e for e in entries if e.get("level") == "ERROR"]
            warnings = [e for e in entries if e.get("level") == "WARNING"]

            # Group by component
            by_component: dict[str, list[dict[str, Any]]] = {}
            for error in errors:
                comp = error.get("component", "unknown")
                if comp not in by_component:
                    by_component[comp] = []
                by_component[comp].append(error)

            result["status"] = "error_summary"
            result["total_entries"] = len(entries)
            result["error_count"] = len(errors)
            result["warning_count"] = len(warnings)
            result["errors_by_component"] = {k: len(v) for k, v in by_component.items()}
            result["recent_errors"] = errors[-10:]  # Last 10 errors
        else:
            # Return recent logs
            recent = entries[-count:] if count < len(entries) else entries
            result["status"] = "ok"
            result["total_entries"] = len(entries)
            result["returned"] = len(recent)
            result["entries"] = recent

        return json.dumps(result, indent=2)

    except OSError as e:
        result["status"] = "error"
        result["error"] = str(e)
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


# ============================================================================
# API Knowledgebase Tool Implementations
# ============================================================================


def list_api_packs_handler(args: dict[str, Any]) -> str:
    """List all available API packs."""
    from dazzle.api_kb import list_packs

    packs = list_packs()

    return json.dumps(
        {
            "count": len(packs),
            "packs": [
                {
                    "name": p.name,
                    "provider": p.provider,
                    "category": p.category,
                    "description": p.description,
                    "version": p.version,
                }
                for p in packs
            ],
        },
        indent=2,
    )


def search_api_packs_handler(args: dict[str, Any]) -> str:
    """Search for API packs by category, provider, or query."""
    from dazzle.api_kb import search_packs

    category = args.get("category")
    provider = args.get("provider")
    query = args.get("query")

    packs = search_packs(category=category, provider=provider, query=query)

    return json.dumps(
        {
            "query": {
                "category": category,
                "provider": provider,
                "text": query,
            },
            "count": len(packs),
            "packs": [
                {
                    "name": p.name,
                    "provider": p.provider,
                    "category": p.category,
                    "description": p.description,
                    "version": p.version,
                }
                for p in packs
            ],
        },
        indent=2,
    )


def get_api_pack_handler(args: dict[str, Any]) -> str:
    """Get full details of an API pack."""
    from dazzle.api_kb import load_pack

    pack_name = args.get("pack_name")
    if not pack_name:
        return json.dumps({"error": "pack_name parameter required"})

    pack = load_pack(pack_name)
    if pack is None:
        return json.dumps({"error": f"Pack '{pack_name}' not found"})

    return json.dumps(
        {
            "name": pack.name,
            "provider": pack.provider,
            "category": pack.category,
            "version": pack.version,
            "description": pack.description,
            "base_url": pack.base_url,
            "docs_url": pack.docs_url,
            "auth": {
                "type": pack.auth.auth_type if pack.auth else None,
                "env_var": pack.auth.env_var if pack.auth else None,
                "token_url": pack.auth.token_url if pack.auth else None,
                "scopes": pack.auth.scopes if pack.auth else None,
            },
            "env_vars": [
                {
                    "name": e.name,
                    "required": e.required,
                    "description": e.description,
                    "example": e.example,
                }
                for e in pack.env_vars
            ],
            "operations": [
                {
                    "name": o.name,
                    "method": o.method,
                    "path": o.path,
                    "description": o.description,
                }
                for o in pack.operations
            ],
            "foreign_models": [
                {
                    "name": m.name,
                    "description": m.description,
                    "key": m.key_field,
                    "fields": m.fields,
                }
                for m in pack.foreign_models
            ],
        },
        indent=2,
    )


def generate_service_dsl_handler(args: dict[str, Any]) -> str:
    """Generate DSL service and foreign_model blocks from an API pack."""
    from dazzle.api_kb import load_pack

    pack_name = args.get("pack_name")
    if not pack_name:
        return json.dumps({"error": "pack_name parameter required"})

    pack = load_pack(pack_name)
    if pack is None:
        return json.dumps({"error": f"Pack '{pack_name}' not found"})

    # Generate the DSL code
    dsl_parts = []

    # Service block
    dsl_parts.append(pack.generate_service_dsl())

    # Foreign model blocks
    for model in pack.foreign_models:
        dsl_parts.append(pack.generate_foreign_model_dsl(model))

    dsl_code = "\n\n".join(dsl_parts)

    return json.dumps(
        {
            "pack": pack_name,
            "provider": pack.provider,
            "dsl": dsl_code,
            "env_vars_required": [e.name for e in pack.env_vars if e.required],
            "hint": "Add this to your DSL file and configure the env vars",
        },
        indent=2,
    )


def get_env_vars_for_packs_handler(args: dict[str, Any]) -> str:
    """Get .env.example content for specified packs or all packs."""
    from dazzle.api_kb.loader import generate_env_example

    pack_names = args.get("pack_names")

    env_example = generate_env_example(pack_names)

    return json.dumps(
        {
            "packs": pack_names if pack_names else "all",
            "env_example": env_example,
            "hint": "Add this to your .env file and fill in the values",
        },
        indent=2,
    )


# ============================================================================
# Story/Behaviour Layer Tool Implementations
# ============================================================================


def get_dsl_spec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get complete DSL specification for story generation."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Build comprehensive spec
        spec: dict[str, Any] = {
            "project_path": str(project_root),
            "app_name": app_spec.name,
            "entities": [],
            "surfaces": [],
            "personas": [],
            "workspaces": [],
            "state_machines": [],
        }

        # Entities with fields and state machines
        for entity in app_spec.domain.entities:
            entity_info: dict[str, Any] = {
                "name": entity.name,
                "title": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind.value) if f.type.kind else str(f.type),
                        "required": f.is_required,
                    }
                    for f in entity.fields
                ],
            }

            # Add state machine if present
            if entity.state_machine:
                sm = entity.state_machine
                entity_info["state_machine"] = {
                    "field": sm.status_field,
                    "states": sm.states,
                    "transitions": [
                        {
                            "from": t.from_state,
                            "to": t.to_state,
                            "trigger": t.trigger.value if t.trigger else None,
                        }
                        for t in sm.transitions
                    ],
                }
                spec["state_machines"].append(
                    {"entity": entity.name, "field": sm.status_field, "states": sm.states}
                )

            spec["entities"].append(entity_info)

        # Surfaces with modes
        for surface in app_spec.surfaces:
            spec["surfaces"].append(
                {
                    "name": surface.name,
                    "title": surface.title,
                    "entity": surface.entity_ref,
                    "mode": surface.mode.value if surface.mode else None,
                }
            )

        # Personas
        for persona in app_spec.personas:
            spec["personas"].append(
                {
                    "id": persona.id,
                    "label": persona.label,
                    "description": persona.description,
                }
            )

        # Workspaces
        for workspace in app_spec.workspaces:
            spec["workspaces"].append(
                {
                    "name": workspace.name,
                    "title": workspace.title,
                    "purpose": workspace.purpose,
                    "regions": [r.name for r in workspace.regions],
                }
            )

        return json.dumps(spec, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def propose_stories_from_dsl_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze DSL and propose behavioural user stories."""
    from datetime import datetime

    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import get_next_story_id

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        max_stories = args.get("max_stories", 30)
        filter_entities = args.get("entities")

        stories: list[StorySpec] = []
        story_count = 0

        # Get starting story ID
        base_id = get_next_story_id(project_root)
        base_num = int(base_id[3:])

        def next_id() -> str:
            nonlocal story_count
            result = f"ST-{base_num + story_count:03d}"
            story_count += 1
            return result

        now = datetime.now(UTC).isoformat()

        # Default persona
        default_actor = "User"
        if app_spec.personas:
            default_actor = app_spec.personas[0].label or app_spec.personas[0].id

        # Generate stories from entities
        for entity in app_spec.domain.entities:
            if filter_entities and entity.name not in filter_entities:
                continue

            if story_count >= max_stories:
                break

            # Find persona for this entity (from workspace regions or UX variants)
            actor = default_actor
            for ws in app_spec.workspaces:
                if any(
                    r.name == entity.name or entity.name.lower() in r.name.lower()
                    for r in ws.regions
                ):
                    # Workspace doesn't have persona directly, use default
                    break

            # Story: Create entity via form
            stories.append(
                StorySpec(
                    story_id=next_id(),
                    title=f"{actor} creates a new {entity.title or entity.name}",
                    actor=actor,
                    trigger=StoryTrigger.FORM_SUBMITTED,
                    scope=[entity.name],
                    preconditions=[f"{actor} has permission to create {entity.name}"],
                    happy_path_outcome=[
                        f"New {entity.name} is saved to database",
                        f"{actor} sees confirmation message",
                    ],
                    side_effects=[],
                    constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][
                        :3
                    ],
                    variants=["Validation error on required field"],
                    status=StoryStatus.DRAFT,
                    created_at=now,
                )
            )

            # Story: State machine transitions
            if entity.state_machine and story_count < max_stories:
                sm = entity.state_machine
                for transition in sm.transitions[:3]:  # Limit transitions
                    if story_count >= max_stories:
                        break

                    stories.append(
                        StorySpec(
                            story_id=next_id(),
                            title=f"{actor} changes {entity.name} from {transition.from_state} to {transition.to_state}",
                            actor=actor,
                            trigger=StoryTrigger.STATUS_CHANGED,
                            scope=[entity.name],
                            preconditions=[
                                f"{entity.name}.{sm.status_field} is '{transition.from_state}'"
                            ],
                            happy_path_outcome=[
                                f"{entity.name}.{sm.status_field} becomes '{transition.to_state}'",
                                "Timestamp is recorded",
                            ],
                            side_effects=[],
                            constraints=[f"Transition only allowed from '{transition.from_state}'"],
                            variants=[],
                            status=StoryStatus.DRAFT,
                            created_at=now,
                        )
                    )

        # Convert to JSON-serializable format
        stories_data = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "actor": s.actor,
                "trigger": s.trigger.value,
                "scope": s.scope,
                "preconditions": s.preconditions,
                "happy_path_outcome": s.happy_path_outcome,
                "side_effects": s.side_effects,
                "constraints": s.constraints,
                "variants": s.variants,
                "status": s.status.value,
                "created_at": s.created_at,
            }
            for s in stories
        ]

        return json.dumps(
            {
                "proposed_count": len(stories_data),
                "max_stories": max_stories,
                "note": "These are draft stories. Review and call save_stories with accepted stories.",
                "stories": stories_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save stories to .dazzle/stories/stories.json."""
    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import add_stories, get_stories_file

    stories_data = args.get("stories", [])
    overwrite = args.get("overwrite", False)

    if not stories_data:
        return json.dumps({"error": "No stories provided"})

    try:
        # Convert to StorySpec objects with validation
        stories: list[StorySpec] = []
        for s in stories_data:
            story = StorySpec(
                story_id=s["story_id"],
                title=s["title"],
                actor=s["actor"],
                trigger=StoryTrigger(s["trigger"]),
                scope=s.get("scope", []),
                preconditions=s.get("preconditions", []),
                happy_path_outcome=s.get("happy_path_outcome", []),
                side_effects=s.get("side_effects", []),
                constraints=s.get("constraints", []),
                variants=s.get("variants", []),
                status=StoryStatus(s.get("status", "draft")),
                created_at=s.get("created_at"),
                accepted_at=s.get("accepted_at"),
            )
            stories.append(story)

        # Save stories
        all_stories = add_stories(project_root, stories, overwrite=overwrite)
        stories_file = get_stories_file(project_root)

        return json.dumps(
            {
                "status": "saved",
                "file": str(stories_file),
                "saved_count": len(stories),
                "total_count": len(all_stories),
                "overwrite": overwrite,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve stories filtered by status."""
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status, get_stories_file

    status_filter = args.get("status_filter", "all")

    try:
        status = None
        if status_filter != "all":
            status = StoryStatus(status_filter)

        stories = get_stories_by_status(project_root, status)
        stories_file = get_stories_file(project_root)

        stories_data = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "actor": s.actor,
                "trigger": s.trigger.value,
                "scope": s.scope,
                "preconditions": s.preconditions,
                "happy_path_outcome": s.happy_path_outcome,
                "side_effects": s.side_effects,
                "constraints": s.constraints,
                "variants": s.variants,
                "status": s.status.value,
                "created_at": s.created_at,
                "accepted_at": s.accepted_at,
            }
            for s in stories
        ]

        return json.dumps(
            {
                "file": str(stories_file),
                "filter": status_filter,
                "count": len(stories_data),
                "stories": stories_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def generate_story_stubs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate Python service stubs from accepted stories."""
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status
    from dazzle.stubs.story_stub_generator import generate_story_stubs_file

    story_ids = args.get("story_ids")
    output_dir = args.get("output_dir", "services")

    try:
        # Get accepted stories
        stories = get_stories_by_status(project_root, StoryStatus.ACCEPTED)

        if story_ids:
            stories = [s for s in stories if s.story_id in story_ids]

        if not stories:
            return json.dumps(
                {
                    "status": "no_stories",
                    "message": "No accepted stories found. Use get_stories to see available stories.",
                }
            )

        # Generate stubs
        stubs_code = generate_story_stubs_file(stories)

        # Write to file
        output_path = project_root / output_dir
        output_path.mkdir(parents=True, exist_ok=True)
        stubs_file = output_path / "story_handlers.py"
        stubs_file.write_text(stubs_code, encoding="utf-8")

        return json.dumps(
            {
                "status": "generated",
                "file": str(stubs_file),
                "story_count": len(stories),
                "stories": [s.story_id for s in stories],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Demo Data Blueprint Tool Implementations
# ============================================================================


# NATO phonetic alphabet for tenant naming
NATO_PREFIXES = [
    "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot",
    "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima",
]


def _infer_domain_suffix(domain_description: str) -> str:
    """Infer a domain suffix from the description."""
    desc_lower = domain_description.lower()

    # Domain patterns
    if any(w in desc_lower for w in ["solar", "renewable", "energy", "battery"]):
        return "Solar Ltd"
    elif any(w in desc_lower for w in ["property", "letting", "estate", "rental"]):
        return "Lettings Ltd"
    elif any(w in desc_lower for w in ["account", "finance", "tax", "bookkeep"]):
        return "Finance Ltd"
    elif any(w in desc_lower for w in ["task", "project", "todo"]):
        return "Tasks Ltd"
    elif any(w in desc_lower for w in ["crm", "client", "customer"]):
        return "Services Ltd"
    else:
        return "Ltd"


def _infer_field_strategy(
    field_name: str, field_type: str, entity_name: str, is_enum: bool = False
) -> tuple[str, dict[str, Any]]:
    """Infer a field strategy from field name and type."""
    name_lower = field_name.lower()

    # Primary key / ID fields
    if name_lower == "id" or name_lower.endswith("_id") and "uuid" in field_type.lower():
        return "uuid_generate", {}

    # Foreign key fields
    if name_lower.endswith("_id"):
        target = field_name[:-3]  # Remove _id suffix
        return "foreign_key", {"target_entity": target.title(), "target_field": "id"}

    # Person name patterns
    if any(w in name_lower for w in ["name", "full_name", "first_name", "last_name"]):
        return "person_name", {"locale": "en_GB"}

    # Company name patterns
    if any(w in name_lower for w in ["company", "organization", "business"]):
        return "company_name", {}

    # Email patterns
    if "email" in name_lower:
        return "email_from_name", {"source_field": "full_name", "domains": ["example.test"]}

    # Username patterns
    if "username" in name_lower:
        return "username_from_name", {"source_field": "full_name"}

    # Password patterns
    if "password" in name_lower:
        return "hashed_password_placeholder", {"plaintext_demo_password": "Demo1234!"}

    # Boolean patterns
    if field_type.lower() == "bool" or name_lower.startswith("is_") or name_lower.startswith("has_"):
        return "boolean_weighted", {"true_weight": 0.3}

    # Date patterns
    if any(w in name_lower for w in ["date", "created", "updated", "at"]):
        return "date_relative", {"anchor": "today", "min_offset_days": -365, "max_offset_days": 0}

    # Currency/amount patterns
    if any(w in name_lower for w in ["amount", "price", "total", "cost", "value"]):
        return "currency_amount", {"min": 10, "max": 10000, "decimals": 2}

    # Numeric patterns
    if field_type.lower() in ["int", "integer"]:
        return "numeric_range", {"min": 1, "max": 100}

    # Enum fields
    if is_enum:
        return "enum_weighted", {"enum_values": [], "weights": []}

    # Text patterns
    if any(w in name_lower for w in ["description", "notes", "comments", "text"]):
        return "free_text_lorem", {"min_words": 5, "max_words": 20}

    # Title patterns
    if any(w in name_lower for w in ["title", "subject", "heading"]):
        return "free_text_lorem", {"min_words": 3, "max_words": 8}

    # Default to lorem text
    return "free_text_lorem", {"min_words": 2, "max_words": 5}


def propose_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze DSL and propose a Demo Data Blueprint."""
    from dazzle.core.ir.demo_blueprint import (
        DemoDataBlueprint,
        EntityBlueprint,
        FieldPattern,
        FieldStrategy,
        PersonaBlueprint,
        TenantBlueprint,
    )

    domain_description = args.get("domain_description", "")
    tenant_count = args.get("tenant_count", 2)

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Generate tenant blueprints
        domain_suffix = _infer_domain_suffix(domain_description)
        tenants = []
        for i in range(min(tenant_count, len(NATO_PREFIXES))):
            prefix = NATO_PREFIXES[i]
            slug = f"{prefix.lower()}-{domain_suffix.replace(' ', '-').lower()}"
            tenants.append(
                TenantBlueprint(
                    name=f"{prefix} {domain_suffix}",
                    slug=slug,
                    notes=f"Demo tenant {i + 1}" if i == 0 else None,
                )
            )

        # Generate persona blueprints from DSL personas
        personas = []
        for persona in app_spec.personas:
            personas.append(
                PersonaBlueprint(
                    persona_name=persona.label or persona.id,
                    description=persona.description or f"{persona.label or persona.id} user",
                    default_role=f"role_{persona.id.lower()}",
                    default_user_count=2 if persona.id.lower() in ["staff", "user"] else 1,
                )
            )

        # Default personas if none defined
        if not personas:
            personas = [
                PersonaBlueprint(
                    persona_name="Staff",
                    description="Regular staff users",
                    default_role="role_staff",
                    default_user_count=3,
                ),
            ]

        # Generate entity blueprints
        entities = []
        for entity in app_spec.domain.entities:
            # Check for tenant_id field
            tenant_scoped = any(f.name == "tenant_id" for f in entity.fields)

            # Generate field patterns
            field_patterns = []
            for field in entity.fields:
                # Detect field type
                field_type_str = (
                    field.type.kind.value if field.type and field.type.kind else "str"
                )
                is_enum = bool(
                    field.type and field.type.kind and field.type.kind.value == "enum"
                )

                strategy, params = _infer_field_strategy(
                    field.name, field_type_str, entity.name, is_enum
                )

                # Add enum values if applicable
                if is_enum and field.type.enum_values:
                    params["enum_values"] = field.type.enum_values
                    params["weights"] = [1.0 / len(field.type.enum_values)] * len(
                        field.type.enum_values
                    )

                field_patterns.append(
                    FieldPattern(
                        field_name=field.name,
                        strategy=FieldStrategy(strategy),
                        params=params,
                    )
                )

            # Determine row count based on entity type
            row_count = 20
            if entity.name.lower() in ["user", "tenant"]:
                row_count = 0  # Generated from personas/tenants
            elif entity.name.lower() in ["invoice", "order", "transaction"]:
                row_count = 100
            elif entity.name.lower() in ["client", "customer", "contact"]:
                row_count = 30

            entities.append(
                EntityBlueprint(
                    name=entity.name,
                    row_count_default=row_count,
                    notes=entity.title,
                    tenant_scoped=tenant_scoped,
                    field_patterns=field_patterns,
                )
            )

        # Create blueprint
        blueprint = DemoDataBlueprint(
            project_id=manifest.name or project_root.name,
            domain_description=domain_description,
            seed=42,
            tenants=tenants,
            personas=personas,
            entities=entities,
        )

        # Convert to JSON
        blueprint_data = blueprint.model_dump(mode="json")

        return json.dumps(
            {
                "status": "proposed",
                "project_path": str(project_root),
                "tenant_count": len(tenants),
                "persona_count": len(personas),
                "entity_count": len(entities),
                "note": "Review and adjust, then call save_demo_blueprint to persist.",
                "blueprint": blueprint_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save a Demo Data Blueprint to .dazzle/demo_data/blueprint.json."""
    from dazzle.core.demo_blueprint_persistence import save_blueprint
    from dazzle.core.ir.demo_blueprint import DemoDataBlueprint

    blueprint_data = args.get("blueprint")
    if not blueprint_data:
        return json.dumps({"error": "blueprint parameter required"})

    try:
        # Validate and create blueprint
        blueprint = DemoDataBlueprint.model_validate(blueprint_data)

        # Save blueprint
        blueprint_file = save_blueprint(project_root, blueprint)

        return json.dumps(
            {
                "status": "saved",
                "file": str(blueprint_file),
                "project_id": blueprint.project_id,
                "tenant_count": len(blueprint.tenants),
                "persona_count": len(blueprint.personas),
                "entity_count": len(blueprint.entities),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load the current Demo Data Blueprint."""
    from dazzle.core.demo_blueprint_persistence import get_blueprint_file, load_blueprint

    try:
        blueprint = load_blueprint(project_root)
        blueprint_file = get_blueprint_file(project_root)

        if blueprint is None:
            return json.dumps(
                {
                    "status": "not_found",
                    "file": str(blueprint_file),
                    "message": "No blueprint found. Use propose_demo_blueprint to create one.",
                }
            )

        return json.dumps(
            {
                "status": "loaded",
                "file": str(blueprint_file),
                "blueprint": blueprint.model_dump(mode="json"),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def generate_demo_data_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate demo data files from the blueprint."""
    from dazzle.core.demo_blueprint_persistence import load_blueprint
    from dazzle.demo_data.blueprint_generator import BlueprintDataGenerator

    output_format = args.get("format", "csv")
    output_dir = args.get("output_dir", "demo_data")
    filter_entities = args.get("entities")

    try:
        blueprint = load_blueprint(project_root)
        if blueprint is None:
            return json.dumps(
                {
                    "status": "no_blueprint",
                    "message": "No blueprint found. Use propose_demo_blueprint first.",
                }
            )

        # Create generator
        generator = BlueprintDataGenerator(blueprint)

        # Generate data
        output_path = project_root / output_dir
        files = generator.generate_all(
            output_path,
            format=output_format,
            entities=filter_entities,
        )

        # Get login matrix
        login_matrix = generator.get_login_matrix()
        login_file = output_path / "login_matrix.md"
        login_file.write_text(login_matrix, encoding="utf-8")

        return json.dumps(
            {
                "status": "generated",
                "output_dir": str(output_path),
                "format": output_format,
                "files": {name: str(path) for name, path in files.items()},
                "login_matrix": str(login_file),
                "total_rows": sum(generator.row_counts.values()),
                "row_counts": generator.row_counts,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
