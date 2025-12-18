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


def generate_tests_from_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate test designs from accepted stories."""
    from .handlers.stories import generate_tests_from_stories_handler as impl

    return impl(project_root, args)


# ============================================================================
# Demo Data Blueprint Tool Implementations
# ============================================================================


# NATO phonetic alphabet for tenant naming
NATO_PREFIXES = [
    "Alpha",
    "Bravo",
    "Charlie",
    "Delta",
    "Echo",
    "Foxtrot",
    "Golf",
    "Hotel",
    "India",
    "Juliet",
    "Kilo",
    "Lima",
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
    if (
        field_type.lower() == "bool"
        or name_lower.startswith("is_")
        or name_lower.startswith("has_")
    ):
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
    filter_entities = args.get("entities")  # v0.14.2: Optional entity filter for chunking
    include_metadata = args.get(
        "include_metadata", True
    )  # v0.14.2: Skip tenants/personas for batches
    quick_mode = args.get("quick_mode", False)  # v0.14.2: Minimal demo data generation

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # v0.14.2: Warn about large projects
        total_entities = len(app_spec.domain.entities)
        warnings: list[str] = []
        if total_entities > 15 and not filter_entities:
            warnings.append(
                f"Large project detected ({total_entities} entities). "
                f"Consider using 'entities' parameter to generate in batches of 10-15 to avoid truncation."
            )

        # Generate tenant blueprints (only if include_metadata)
        tenants = []
        if include_metadata:
            domain_suffix = _infer_domain_suffix(domain_description)
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

        # Generate persona blueprints from DSL personas (only if include_metadata)
        personas = []
        if include_metadata:
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

        # v0.14.2: Filter entities if specified
        dsl_entities = app_spec.domain.entities
        if filter_entities:
            filter_set = set(filter_entities)
            dsl_entities = [e for e in dsl_entities if e.name in filter_set]
            if len(dsl_entities) < len(filter_entities):
                found = {e.name for e in dsl_entities}
                missing = filter_set - found
                warnings.append(f"Entities not found in DSL: {', '.join(sorted(missing))}")

        # v0.14.2: Quick mode - prioritize entities with surfaces
        if quick_mode and not filter_entities:
            # Find entities referenced by surfaces
            surface_entities = {s.entity_ref for s in app_spec.surfaces if s.entity_ref}
            # Also include entities referenced by those entities (one level)
            ref_entities: set[str] = set()
            for entity in app_spec.domain.entities:
                if entity.name in surface_entities:
                    for field in entity.fields:
                        if field.type.ref_entity:
                            ref_entities.add(field.type.ref_entity)

            priority_entities = surface_entities | ref_entities
            if priority_entities:
                dsl_entities = [e for e in dsl_entities if e.name in priority_entities]
                warnings.append(
                    f"Quick mode: Selected {len(dsl_entities)} entities with surfaces/references "
                    f"(skipped {total_entities - len(dsl_entities)} others)"
                )

        # Generate entity blueprints
        entities = []
        for entity in dsl_entities:
            # Check for tenant_id field
            tenant_scoped = any(f.name == "tenant_id" for f in entity.fields)

            # Generate field patterns
            field_patterns = []
            for field in entity.fields:
                # Detect field type
                field_type_str = field.type.kind.value if field.type and field.type.kind else "str"
                is_enum = bool(field.type and field.type.kind and field.type.kind.value == "enum")

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
            if quick_mode:
                # v0.14.2: Quick mode uses minimal row counts
                row_count = 5
                if entity.name.lower() in ["user", "tenant"]:
                    row_count = 0  # Generated from personas/tenants
            else:
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

        # v0.14.2: Build response with warnings and chunking info
        response: dict[str, Any] = {
            "status": "proposed",
            "project_path": str(project_root),
            "total_dsl_entities": total_entities,
            "included_entities": len(entities),
            "tenant_count": len(tenants),
            "persona_count": len(personas),
        }

        # Add chunking guidance for large projects
        if filter_entities:
            response["note"] = (
                f"Generated blueprint for {len(entities)} of {total_entities} entities. "
                f"Merge with existing blueprint using save_demo_blueprint."
            )
        else:
            response["note"] = "Review and adjust, then call save_demo_blueprint to persist."

        if warnings:
            response["warnings"] = warnings

        # v0.14.2: List all entity names for chunking guidance
        if total_entities > 15 and not filter_entities:
            all_entity_names = [e.name for e in app_spec.domain.entities]
            response["all_entity_names"] = all_entity_names
            response["chunking_suggestion"] = {
                "batch_size": 10,
                "batch_count": (total_entities + 9) // 10,
                "example_call": {
                    "entities": all_entity_names[:10],
                    "include_metadata": True,
                },
            }

        response["blueprint"] = blueprint_data

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_demo_blueprint_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save a Demo Data Blueprint to .dazzle/demo_data/blueprint.json."""
    from dazzle.core.demo_blueprint_persistence import load_blueprint, save_blueprint
    from dazzle.core.ir.demo_blueprint import DemoDataBlueprint

    blueprint_data = args.get("blueprint")
    merge_entities = args.get("merge", False)  # v0.14.2: Merge with existing blueprint
    validate_coverage = args.get("validate", True)  # v0.14.2: Validate against DSL

    if not blueprint_data:
        return json.dumps({"error": "blueprint parameter required"})

    try:
        # Validate and create blueprint
        new_blueprint = DemoDataBlueprint.model_validate(blueprint_data)
        warnings: list[str] = []

        # v0.14.2: Merge with existing blueprint if requested
        if merge_entities:
            existing = load_blueprint(project_root)
            if existing:
                # Merge entities (new ones override existing)
                existing_entity_names = {e.name for e in existing.entities}
                new_entity_names = {e.name for e in new_blueprint.entities}

                merged_entities = list(new_blueprint.entities)
                for entity in existing.entities:
                    if entity.name not in new_entity_names:
                        merged_entities.append(entity)

                # Use existing tenants/personas if new blueprint doesn't have them
                tenants = new_blueprint.tenants if new_blueprint.tenants else existing.tenants
                personas = new_blueprint.personas if new_blueprint.personas else existing.personas

                new_blueprint = DemoDataBlueprint(
                    project_id=new_blueprint.project_id or existing.project_id,
                    domain_description=new_blueprint.domain_description
                    or existing.domain_description,
                    seed=new_blueprint.seed or existing.seed,
                    tenants=tenants,
                    personas=personas,
                    entities=merged_entities,
                )

                added_count = len(new_entity_names - existing_entity_names)
                warnings.append(
                    f"Merged {added_count} new entities with {len(existing_entity_names)} existing"
                )

        # v0.14.2: Validate coverage against DSL
        if validate_coverage:
            try:
                manifest = load_manifest(project_root / "dazzle.toml")
                dsl_files = discover_dsl_files(project_root, manifest)
                modules = parse_modules(dsl_files)
                app_spec = build_appspec(modules, manifest.project_root)

                dsl_entity_names = {e.name for e in app_spec.domain.entities}
                blueprint_entity_names = {e.name for e in new_blueprint.entities}

                # Check for missing entities
                missing = dsl_entity_names - blueprint_entity_names
                if missing:
                    warnings.append(
                        f"Blueprint missing {len(missing)} DSL entities: {', '.join(sorted(missing)[:5])}"
                        + (f"... and {len(missing) - 5} more" if len(missing) > 5 else "")
                    )

                # Check for entities with no field patterns
                empty_patterns = [e.name for e in new_blueprint.entities if not e.field_patterns]
                if empty_patterns:
                    warnings.append(
                        f"{len(empty_patterns)} entities have no field_patterns: {', '.join(empty_patterns[:3])}"
                        + (
                            f"... and {len(empty_patterns) - 3} more"
                            if len(empty_patterns) > 3
                            else ""
                        )
                    )

            except Exception as e:
                warnings.append(f"Could not validate against DSL: {e}")

        # Save blueprint
        blueprint_file = save_blueprint(project_root, new_blueprint)

        response: dict[str, Any] = {
            "status": "saved",
            "file": str(blueprint_file),
            "project_id": new_blueprint.project_id,
            "tenant_count": len(new_blueprint.tenants),
            "persona_count": len(new_blueprint.personas),
            "entity_count": len(new_blueprint.entities),
        }

        if warnings:
            response["warnings"] = warnings

        return json.dumps(response, indent=2)
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

        # v0.14.2: Pre-generation diagnostics
        warnings: list[str] = []
        diagnostics: dict[str, Any] = {}

        # Check for entities with no field patterns
        empty_pattern_entities = [e.name for e in blueprint.entities if not e.field_patterns]
        if empty_pattern_entities:
            warnings.append(
                f"{len(empty_pattern_entities)} entities have no field_patterns and will generate empty files: "
                f"{', '.join(empty_pattern_entities[:5])}"
                + (
                    f"... and {len(empty_pattern_entities) - 5} more"
                    if len(empty_pattern_entities) > 5
                    else ""
                )
            )
            diagnostics["empty_pattern_entities"] = empty_pattern_entities

        # Check for entities with 0 row_count
        zero_row_entities = [
            e.name
            for e in blueprint.entities
            if e.row_count_default == 0 and e.name.lower() not in ["user", "tenant"]
        ]
        if zero_row_entities:
            warnings.append(
                f"{len(zero_row_entities)} entities have row_count_default=0: {', '.join(zero_row_entities[:5])}"
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

        # v0.14.2: Post-generation diagnostics
        total_rows = sum(generator.row_counts.values())
        entities_with_data = [name for name, count in generator.row_counts.items() if count > 0]
        entities_without_data = [name for name, count in generator.row_counts.items() if count == 0]

        if entities_without_data:
            warnings.append(
                f"{len(entities_without_data)} entities generated 0 rows: {', '.join(entities_without_data[:5])}"
                + (
                    f"... and {len(entities_without_data) - 5} more"
                    if len(entities_without_data) > 5
                    else ""
                )
            )

        if total_rows == 0:
            warnings.append(
                "No data was generated! Check that field_patterns are defined for entities. "
                "Re-run propose_demo_blueprint with specific entities to regenerate patterns."
            )

        # Get login matrix
        login_matrix = generator.get_login_matrix()
        login_file = output_path / "login_matrix.md"
        login_file.write_text(login_matrix, encoding="utf-8")

        response: dict[str, Any] = {
            "status": "generated",
            "output_dir": str(output_path),
            "format": output_format,
            "files": {name: str(path) for name, path in files.items()},
            "login_matrix": str(login_file),
            "total_rows": total_rows,
            "row_counts": generator.row_counts,
            "entities_with_data": len(entities_with_data),
            "entities_without_data": len(entities_without_data),
        }

        if warnings:
            response["warnings"] = warnings

        if diagnostics:
            response["diagnostics"] = diagnostics

        return json.dumps(response, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ============================================================================
# Test Design Tool Implementations (v0.13.0)
# ============================================================================


def propose_persona_tests_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Generate test designs from persona goals and workflows.

    Analyzes a persona's goals from DSL and proposes tests that verify
    the persona can achieve their stated objectives.
    """
    from datetime import datetime

    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.testing.test_design_persistence import get_next_test_design_id

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        persona_filter = args.get("persona")
        max_tests = args.get("max_tests", 10)

        designs: list[TestDesignSpec] = []
        design_count = 0

        # Get starting ID
        base_id = get_next_test_design_id(project_root)
        base_num = int(base_id[3:])

        def next_id() -> str:
            nonlocal design_count
            result = f"TD-{base_num + design_count:03d}"
            design_count += 1
            return result

        now = datetime.utcnow()

        # Filter personas
        personas_to_process = app_spec.personas
        if persona_filter:
            personas_to_process = [
                p
                for p in personas_to_process
                if p.id == persona_filter or p.label == persona_filter
            ]

        if not personas_to_process:
            return json.dumps(
                {
                    "status": "no_personas",
                    "message": "No personas found in DSL. Add persona definitions to generate persona-centric tests.",
                    "available_personas": [p.id for p in app_spec.personas],
                }
            )

        for persona in personas_to_process:
            if design_count >= max_tests:
                break

            persona_name = persona.label or persona.id

            # Generate tests for each persona goal
            for goal in persona.goals[:3]:  # Limit goals per persona
                if design_count >= max_tests:
                    break

                # Create test design for this goal
                steps = [
                    TestDesignStep(
                        action=TestDesignAction.LOGIN_AS,
                        target=persona.id,
                        rationale=f"Authenticate as {persona_name}",
                    ),
                ]

                # Find surfaces this persona can access
                # Note: WorkspaceSpec doesn't directly link to persona; use all workspaces
                surfaces_for_persona = []
                for ws in app_spec.workspaces:
                    surfaces_for_persona.extend(ws.regions)

                # If persona has access to surfaces, navigate to first one
                if surfaces_for_persona:
                    steps.append(
                        TestDesignStep(
                            action=TestDesignAction.NAVIGATE_TO,
                            target=surfaces_for_persona[0].name
                            if surfaces_for_persona
                            else "dashboard",
                            rationale="Navigate to persona's primary workspace",
                        )
                    )

                # Add goal-specific action (inferred from goal text)
                if "create" in goal.lower() or "add" in goal.lower():
                    steps.append(
                        TestDesignStep(
                            action=TestDesignAction.CREATE,
                            target="entity",
                            data={"from_goal": goal},
                            rationale=f"Perform action to achieve: {goal}",
                        )
                    )
                elif "view" in goal.lower() or "see" in goal.lower():
                    steps.append(
                        TestDesignStep(
                            action=TestDesignAction.ASSERT_VISIBLE,
                            target="content",
                            data={"from_goal": goal},
                            rationale=f"Verify visibility for: {goal}",
                        )
                    )
                else:
                    steps.append(
                        TestDesignStep(
                            action=TestDesignAction.CLICK,
                            target="action",
                            data={"from_goal": goal},
                            rationale=f"Interact to achieve: {goal}",
                        )
                    )

                designs.append(
                    TestDesignSpec(
                        test_id=next_id(),
                        title=f"{persona_name} can {goal.lower().rstrip('.')}",
                        description=f"Test that {persona_name} persona can achieve goal: {goal}",
                        persona=persona.id,
                        trigger=TestDesignTrigger.USER_CLICK,
                        steps=steps,
                        expected_outcomes=[
                            f"Goal achieved: {goal}",
                            "No errors or permission denials",
                        ],
                        entities=[],  # Will be filled by agent
                        surfaces=[s.name for s in surfaces_for_persona[:2]],
                        tags=["persona", persona.id, "goal"],
                        status=TestDesignStatus.PROPOSED,
                        prompt_version="v1",
                        created_at=now,
                        updated_at=now,
                    )
                )

            # Generate test for persona accessing a workspace
            # Note: WorkspaceSpec doesn't directly link to persona; generate test for first workspace
            if app_spec.workspaces and design_count < max_tests:
                ws = app_spec.workspaces[0]  # Use first workspace
                designs.append(
                    TestDesignSpec(
                        test_id=next_id(),
                        title=f"{persona_name} can access {ws.title or ws.name} workspace",
                        description=f"Test that {persona_name} can access and use the {ws.name} workspace",
                        persona=persona.id,
                        trigger=TestDesignTrigger.PAGE_LOAD,
                        steps=[
                            TestDesignStep(
                                action=TestDesignAction.LOGIN_AS,
                                target=persona.id,
                                rationale=f"Authenticate as {persona_name}",
                            ),
                            TestDesignStep(
                                action=TestDesignAction.NAVIGATE_TO,
                                target=ws.name,
                                rationale=f"Go to {ws.title or ws.name} workspace",
                            ),
                            TestDesignStep(
                                action=TestDesignAction.ASSERT_VISIBLE,
                                target=f"workspace:{ws.name}",
                                rationale="Verify workspace is accessible",
                            ),
                        ],
                        expected_outcomes=[
                            f"Workspace {ws.name} loads successfully",
                            "All workspace regions are visible",
                        ],
                        entities=[],
                        surfaces=[r.name for r in ws.regions],
                        tags=["persona", persona.id, "workspace"],
                        status=TestDesignStatus.PROPOSED,
                        prompt_version="v1",
                        created_at=now,
                        updated_at=now,
                    )
                )

        # Convert to JSON-serializable format
        designs_data = [
            {
                "test_id": d.test_id,
                "title": d.title,
                "description": d.description,
                "persona": d.persona,
                "trigger": d.trigger.value,
                "steps": [
                    {
                        "action": s.action.value,
                        "target": s.target,
                        "data": s.data,
                        "rationale": s.rationale,
                    }
                    for s in d.steps
                ],
                "expected_outcomes": d.expected_outcomes,
                "entities": d.entities,
                "surfaces": d.surfaces,
                "tags": d.tags,
                "status": d.status.value,
            }
            for d in designs
        ]

        return json.dumps(
            {
                "proposed_count": len(designs_data),
                "max_tests": max_tests,
                "personas_analyzed": [p.id for p in personas_to_process],
                "note": "These are draft test designs. Review and call save_test_designs with accepted designs.",
                "designs": designs_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_test_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze coverage and suggest what's missing.

    Returns untested entities, persona goals, state transitions, and suggested test designs.
    """
    from dazzle.core.ir.test_design import TestGap, TestGapAnalysis, TestGapCategory
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Load existing test designs
        existing_designs = load_test_designs(project_root)
        existing_entities: set[str] = set()
        existing_personas: set[str] = set()

        for design in existing_designs:
            existing_entities.update(design.entities)
            if design.persona:
                existing_personas.add(design.persona)

        # Generate deterministic tests to see what we already cover
        testspec = generate_e2e_testspec(app_spec)

        gaps: list[TestGap] = []

        # Check for untested entities (no custom test designs)
        all_entities = {e.name for e in app_spec.domain.entities}
        untested_entities = all_entities - existing_entities

        for entity_name in untested_entities:
            entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
            if entity:
                # High severity if it has state machine or access control
                severity: str = "medium"
                if entity.state_machine:
                    severity = "high"
                if entity.access:
                    severity = "high"

                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_ENTITY,
                        target=entity_name,
                        severity=severity,  # type: ignore[arg-type]
                        suggestion=f"Add persona-centric test designs for {entity_name}",
                    )
                )

        # Check for untested persona goals
        for persona in app_spec.personas:
            if persona.id not in existing_personas:
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_PERSONA_GOAL,
                        target=persona.id,
                        severity="high",
                        suggestion=f"Use propose_persona_tests to generate tests for {persona.label or persona.id}",
                    )
                )
            else:
                # Check if all goals are covered
                persona_designs = [d for d in existing_designs if d.persona == persona.id]
                covered_goals = 0
                for goal in persona.goals:
                    if any(
                        goal.lower() in (d.title.lower() if d.title else "")
                        for d in persona_designs
                    ):
                        covered_goals += 1

                if covered_goals < len(persona.goals):
                    gaps.append(
                        TestGap(
                            category=TestGapCategory.UNTESTED_PERSONA_GOAL,
                            target=f"{persona.id} (partial)",
                            severity="medium",
                            suggestion=f"Only {covered_goals}/{len(persona.goals)} goals covered for {persona.id}",
                        )
                    )

        # Check for untested state transitions
        for entity in app_spec.domain.entities:
            if entity.state_machine:
                sm = entity.state_machine
                for transition in sm.transitions:
                    # Check if deterministic tests cover this
                    flow_id = (
                        f"{entity.name}_transition_{transition.from_state}_to_{transition.to_state}"
                    )
                    if not any(f.id == flow_id for f in testspec.flows):
                        gaps.append(
                            TestGap(
                                category=TestGapCategory.UNTESTED_STATE_TRANSITION,
                                target=f"{entity.name}: {transition.from_state} -> {transition.to_state}",
                                severity="medium",
                                suggestion=f"State transition test missing for {entity.name}",
                                related_entities=[entity.name],
                            )
                        )

        # Check for untested surfaces
        tested_surfaces: set[str] = set()
        for design in existing_designs:
            tested_surfaces.update(design.surfaces)
        for flow in testspec.flows:
            # Extract surfaces from flow targets
            for step in flow.steps:
                if step.target and step.target.startswith("view:"):
                    tested_surfaces.add(step.target.split(":", 1)[1])

        for surface in app_spec.surfaces:
            if surface.name not in tested_surfaces:
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_SURFACE,
                        target=surface.name,
                        severity="low",
                        suggestion=f"Add navigation test for {surface.title or surface.name}",
                    )
                )

        # Check for untested scenarios
        for scenario in app_spec.scenarios:
            # Check if any test design references this scenario
            if not any(d.scenario == scenario.name for d in existing_designs):
                gaps.append(
                    TestGap(
                        category=TestGapCategory.UNTESTED_SCENARIO,
                        target=scenario.name,
                        severity="medium",
                        suggestion=f"DSL scenario '{scenario.name}' has no corresponding test design",
                    )
                )

        # Calculate coverage score
        total_items = (
            len(all_entities)
            + len(app_spec.personas)
            + len(app_spec.surfaces)
            + len(app_spec.scenarios)
        )
        covered_items = (
            len(all_entities - untested_entities)
            + len(existing_personas)
            + len(tested_surfaces)
            + len(
                [
                    s
                    for s in app_spec.scenarios
                    if any(d.scenario == s.name for d in existing_designs)
                ]
            )
        )

        coverage_score = (covered_items / total_items * 100) if total_items > 0 else 100.0

        analysis = TestGapAnalysis(
            project_name=app_spec.name,
            total_entities=len(all_entities),
            total_surfaces=len(app_spec.surfaces),
            total_personas=len(app_spec.personas),
            total_scenarios=len(app_spec.scenarios),
            gaps=gaps,
            coverage_score=round(coverage_score, 1),
        )

        return json.dumps(
            {
                "project": analysis.project_name,
                "coverage_score": analysis.coverage_score,
                "totals": {
                    "entities": analysis.total_entities,
                    "surfaces": analysis.total_surfaces,
                    "personas": analysis.total_personas,
                    "scenarios": analysis.total_scenarios,
                },
                "gap_count": len(gaps),
                "gaps_by_severity": {
                    "high": len([g for g in gaps if g.severity == "high"]),
                    "medium": len([g for g in gaps if g.severity == "medium"]),
                    "low": len([g for g in gaps if g.severity == "low"]),
                },
                "gaps_by_category": analysis.gap_count_by_category,
                "gaps": [
                    {
                        "category": g.category.value,
                        "target": g.target,
                        "severity": g.severity,
                        "suggestion": g.suggestion,
                    }
                    for g in gaps
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save test designs to dsl/tests/designs.json."""
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.testing.test_design_persistence import add_test_designs, get_dsl_tests_dir

    designs_data = args.get("designs", [])
    overwrite = args.get("overwrite", False)

    if not designs_data:
        return json.dumps({"error": "No designs provided"})

    try:
        # Convert dict data to TestDesignSpec objects
        designs: list[TestDesignSpec] = []
        for d in designs_data:
            steps = []
            for s in d.get("steps", []):
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction(s["action"])
                        if s.get("action")
                        else TestDesignAction.CLICK,
                        target=s.get("target", ""),
                        data=s.get("data"),
                        rationale=s.get("rationale"),
                    )
                )

            designs.append(
                TestDesignSpec(
                    test_id=d["test_id"],
                    title=d["title"],
                    description=d.get("description"),
                    persona=d.get("persona"),
                    scenario=d.get("scenario"),
                    trigger=TestDesignTrigger(d["trigger"])
                    if d.get("trigger")
                    else TestDesignTrigger.USER_CLICK,
                    steps=steps,
                    expected_outcomes=d.get("expected_outcomes", []),
                    entities=d.get("entities", []),
                    surfaces=d.get("surfaces", []),
                    tags=d.get("tags", []),
                    status=TestDesignStatus(d.get("status", "proposed")),
                    notes=d.get("notes"),
                )
            )

        # Save designs
        all_designs = add_test_designs(project_root, designs, overwrite=overwrite, to_dsl=True)
        designs_file = get_dsl_tests_dir(project_root) / "designs.json"

        return json.dumps(
            {
                "status": "saved",
                "saved_count": len(designs),
                "total_count": len(all_designs),
                "file": str(designs_file),
                "overwrite": overwrite,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_test_designs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve test designs from storage."""
    from dazzle.core.ir.test_design import TestDesignStatus
    from dazzle.testing.test_design_persistence import (
        get_dsl_tests_dir,
        get_test_designs_by_status,
    )

    status_filter = args.get("status_filter")

    try:
        status = (
            TestDesignStatus(status_filter) if status_filter and status_filter != "all" else None
        )
        designs = get_test_designs_by_status(project_root, status)
        designs_file = get_dsl_tests_dir(project_root) / "designs.json"

        return json.dumps(
            {
                "count": len(designs),
                "filter": status_filter or "all",
                "file": str(designs_file) if designs_file.exists() else None,
                "designs": [
                    {
                        "test_id": d.test_id,
                        "title": d.title,
                        "description": d.description,
                        "persona": d.persona,
                        "scenario": d.scenario,
                        "trigger": d.trigger.value,
                        "steps": [
                            {
                                "action": s.action.value,
                                "target": s.target,
                                "data": s.data,
                                "rationale": s.rationale,
                            }
                            for s in d.steps
                        ],
                        "expected_outcomes": d.expected_outcomes,
                        "entities": d.entities,
                        "surfaces": d.surfaces,
                        "tags": d.tags,
                        "status": d.status.value,
                        "implementation_path": d.implementation_path,
                        "notes": d.notes,
                    }
                    for d in designs
                ],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_coverage_actions_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Get prioritized actions to increase test coverage.

    Returns actionable prompts an LLM can execute directly.
    """
    from dazzle.testing.test_design_persistence import load_test_designs
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    max_actions = args.get("max_actions", 5)
    focus = args.get("focus", "all")

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Load existing test designs and testspec
        existing_designs = load_test_designs(project_root)
        testspec = generate_e2e_testspec(app_spec)

        # Track what's covered
        covered_personas: set[str] = set()
        covered_entities: set[str] = set()
        covered_scenarios: set[str] = set()

        for design in existing_designs:
            if design.persona:
                covered_personas.add(design.persona)
            covered_entities.update(design.entities)
            if design.scenario:
                covered_scenarios.add(design.scenario)

        # Calculate coverage
        all_entities = {e.name for e in app_spec.domain.entities}
        all_personas = {p.id for p in app_spec.personas}
        all_scenarios = {s.name for s in app_spec.scenarios}

        # Build prioritized actions
        actions: list[dict[str, Any]] = []

        # Priority 1: Untested personas with goals (highest impact)
        if focus in ("all", "personas"):
            for persona in app_spec.personas:
                if persona.id not in covered_personas and persona.goals:
                    actions.append(
                        {
                            "priority": 1,
                            "category": "persona_tests",
                            "target": persona.id,
                            "title": f"Generate tests for {persona.label or persona.id}",
                            "impact": f"Covers {len(persona.goals)} persona goals",
                            "prompt": f"""Generate test designs for the "{persona.label or persona.id}" persona.

This persona has {len(persona.goals)} goals that need test coverage:
{chr(10).join(f"- {goal}" for goal in persona.goals)}

Use the `propose_persona_tests` MCP tool with persona="{persona.id}" to generate test designs, then review and save the accepted designs with `save_test_designs`.""",
                            "mcp_tool": "propose_persona_tests",
                            "mcp_args": {"persona": persona.id},
                        }
                    )

        # Priority 2: Entities with state machines (complex behavior)
        if focus in ("all", "state_machines", "entities"):
            for entity in app_spec.domain.entities:
                if entity.state_machine and entity.name not in covered_entities:
                    sm = entity.state_machine
                    transitions = [f"{t.from_state} → {t.to_state}" for t in sm.transitions]
                    actions.append(
                        {
                            "priority": 2,
                            "category": "state_machine_tests",
                            "target": entity.name,
                            "title": f"Add state machine tests for {entity.name}",
                            "impact": f"Covers {len(sm.transitions)} state transitions",
                            "prompt": f"""Create test designs for the {entity.name} entity's state machine.

The state machine has these transitions:
{chr(10).join(f"- {t}" for t in transitions)}

Create a test design that:
1. Creates a {entity.name} in each initial state
2. Triggers each valid transition
3. Verifies the state changes correctly
4. Tests that invalid transitions are rejected

Save the test design with `save_test_designs` using test_id="SM_{entity.name.upper()}_001".""",
                            "code_template": _generate_state_machine_test_template(entity.name, sm),
                        }
                    )

        # Priority 3: Untested scenarios (user workflows)
        if focus in ("all", "scenarios"):
            for scenario in app_spec.scenarios:
                if scenario.name not in covered_scenarios:
                    actions.append(
                        {
                            "priority": 3,
                            "category": "scenario_tests",
                            "target": scenario.name,
                            "title": f"Add tests for scenario: {scenario.name}",
                            "impact": "Covers defined user workflow",
                            "prompt": f"""Create a test design for the "{scenario.name}" scenario.

Description: {scenario.description or "No description"}

This scenario defines a user workflow that should be tested end-to-end. Create a test design that:
1. Sets up the required preconditions
2. Executes the scenario steps
3. Verifies the expected outcomes

Save with `save_test_designs` using test_id="SCENARIO_{scenario.name.upper()}_001".""",
                        }
                    )

        # Priority 4: Entities with access control (security)
        if focus in ("all", "entities"):
            for entity in app_spec.domain.entities:
                if entity.access and entity.name not in covered_entities:
                    actions.append(
                        {
                            "priority": 4,
                            "category": "access_control_tests",
                            "target": entity.name,
                            "title": f"Add access control tests for {entity.name}",
                            "impact": "Verifies permission rules",
                            "prompt": f"""Create test designs for {entity.name} access control.

The entity has access rules that need testing:
- Verify authorized personas can access the entity
- Verify unauthorized personas are denied
- Test each permission (view, create, edit, delete) if applicable

Save with `save_test_designs` using test_id="ACL_{entity.name.upper()}_001".""",
                        }
                    )

        # Priority 5: Basic entity coverage
        if focus in ("all", "entities"):
            for entity in app_spec.domain.entities:
                if (
                    entity.name not in covered_entities
                    and not entity.state_machine
                    and not entity.access
                ):
                    actions.append(
                        {
                            "priority": 5,
                            "category": "entity_tests",
                            "target": entity.name,
                            "title": f"Add CRUD tests for {entity.name}",
                            "impact": "Basic entity coverage",
                            "prompt": f"""Create test designs for basic {entity.name} CRUD operations.

Note: Deterministic CRUD tests are auto-generated, but you can add persona-specific tests that:
1. Test CRUD from a specific persona's perspective
2. Verify business rules and validation
3. Test edge cases specific to this entity

Save with `save_test_designs` using test_id="CRUD_{entity.name.upper()}_001".""",
                        }
                    )

        # Sort by priority and limit
        actions.sort(key=lambda x: x["priority"])
        actions = actions[:max_actions]

        # Calculate coverage score
        total_items = len(all_entities) + len(all_personas) + len(all_scenarios)
        covered_items = len(covered_entities) + len(covered_personas) + len(covered_scenarios)
        coverage_score = (covered_items / total_items * 100) if total_items > 0 else 100.0

        # Build summary
        summary = {
            "coverage_score": round(coverage_score, 1),
            "coverage_breakdown": {
                "entities": f"{len(covered_entities)}/{len(all_entities)}",
                "personas": f"{len(covered_personas)}/{len(all_personas)}",
                "scenarios": f"{len(covered_scenarios)}/{len(all_scenarios)}",
            },
            "deterministic_flows": len(testspec.flows),
            "custom_test_designs": len(existing_designs),
        }

        # Build response with guidance
        return json.dumps(
            {
                "summary": summary,
                "action_count": len(actions),
                "focus": focus,
                "guidance": (
                    "Execute these actions in order to increase coverage. "
                    "Each action includes a prompt you can follow directly. "
                    "After completing an action, call get_coverage_actions again to get the next set."
                ),
                "actions": [
                    {
                        "priority": a["priority"],
                        "category": a["category"],
                        "target": a["target"],
                        "title": a["title"],
                        "impact": a["impact"],
                        "prompt": a["prompt"],
                        "mcp_tool": a.get("mcp_tool"),
                        "mcp_args": a.get("mcp_args"),
                        "code_template": a.get("code_template"),
                    }
                    for a in actions
                ],
                "next_steps": (
                    "1. Read the first action's prompt\n"
                    "2. Execute the suggested MCP tool or follow the instructions\n"
                    "3. Save successful test designs with save_test_designs\n"
                    "4. Call get_coverage_actions again to see updated coverage and next actions"
                ),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _generate_state_machine_test_template(entity_name: str, state_machine: Any) -> str:
    """Generate a test design template for state machine testing."""
    transitions = state_machine.transitions
    status_field = state_machine.status_field

    template_steps = []
    for t in transitions[:3]:  # Limit to first 3 transitions
        template_steps.append(
            {
                "action": "create",
                "target": f"entity:{entity_name}",
                "data": {status_field: t.from_state},
                "rationale": f"Create {entity_name} in '{t.from_state}' state",
            }
        )
        template_steps.append(
            {
                "action": "trigger_transition",
                "target": f"entity:{entity_name}",
                "data": {
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                },
                "rationale": f"Transition from '{t.from_state}' to '{t.to_state}'",
            }
        )

    return json.dumps(
        {
            "test_id": f"SM_{entity_name.upper()}_001",
            "title": f"State machine transitions for {entity_name}",
            "description": f"Verify all valid state transitions for {entity_name}",
            "trigger": "user_click",
            "steps": template_steps,
            "expected_outcomes": [
                "All valid transitions complete successfully",
                "Final state matches expected state",
            ],
            "entities": [entity_name],
            "tags": ["state_machine", "automated"],
        },
        indent=2,
    )


def get_runtime_coverage_gaps_handler(project_root: Path, args: dict[str, Any]) -> str:
    """
    Analyze runtime UX coverage report to find gaps and generate tests.

    This reads the actual runtime coverage from test execution and identifies
    specific gaps that need test coverage.
    """
    max_actions = args.get("max_actions", 5)
    coverage_path = args.get("coverage_report_path")

    # Find coverage report
    if coverage_path:
        report_path = Path(coverage_path)
    else:
        # Default locations
        candidates = [
            project_root / "dsl" / "tests" / "runtime_coverage.json",
            project_root / ".dazzle" / "test_results" / "ux_coverage.json",
        ]
        report_path = None
        for candidate in candidates:
            if candidate.exists():
                report_path = candidate
                break

    if not report_path or not report_path.exists():
        return json.dumps(
            {
                "error": "No runtime coverage report found",
                "hint": (
                    "Run the E2E tests to generate a coverage report, then save it with "
                    "save_runtime_coverage or provide a path with coverage_report_path"
                ),
                "searched_paths": [str(c) for c in candidates]
                if not coverage_path
                else [str(coverage_path)],
            },
            indent=2,
        )

    try:
        # Load coverage report
        with open(report_path) as f:
            coverage = json.load(f)

        # Extract gaps
        actions: list[dict[str, Any]] = []

        # Gap 1: Missing CRUD operations per entity
        for entity_name, entity_data in coverage.get("entities", {}).items():
            missing_ops = entity_data.get("operations_missing", [])
            if missing_ops:
                for op in missing_ops:
                    actions.append(
                        {
                            "priority": 1,
                            "category": "crud_gap",
                            "target": f"{entity_name}:{op}",
                            "title": f"Add {op} test for {entity_name}",
                            "impact": "Will increase entity CRUD coverage",
                            "test_design": {
                                "test_id": f"RUNTIME_{entity_name.upper()}_{op.upper()}_001",
                                "title": f"Test {op} operation for {entity_name}",
                                "description": f"Fill runtime coverage gap: {op} operation for {entity_name}",
                                "trigger": "user_click",
                                "steps": _generate_crud_steps(entity_name, op),
                                "expected_outcomes": [
                                    f"{op.capitalize()} operation completes successfully"
                                ],
                                "entities": [entity_name],
                                "tags": ["crud", "runtime_gap", "automated"],
                                "status": "accepted",
                            },
                        }
                    )

            # Missing UI views
            missing_views = entity_data.get("ui_views_missing", [])
            if missing_views:
                for view in missing_views:
                    actions.append(
                        {
                            "priority": 2,
                            "category": "ui_view_gap",
                            "target": f"{entity_name}:{view}",
                            "title": f"Add {view} view test for {entity_name}",
                            "impact": "Will increase entity UI coverage",
                            "test_design": {
                                "test_id": f"RUNTIME_{entity_name.upper()}_VIEW_{view.upper()}_001",
                                "title": f"Test {view} view for {entity_name}",
                                "description": f"Fill runtime coverage gap: {view} view for {entity_name}",
                                "trigger": "user_click",
                                "steps": _generate_view_steps(entity_name, view),
                                "expected_outcomes": [
                                    f"{view.capitalize()} view renders correctly"
                                ],
                                "entities": [entity_name],
                                "tags": ["ui_view", "runtime_gap", "automated"],
                                "status": "accepted",
                            },
                        }
                    )

        # Gap 2: Missing routes
        routes_data = coverage.get("routes", {})
        if isinstance(routes_data, dict):
            total_routes = routes_data.get("total", 0)
            visited_routes = routes_data.get("visited", 0)
            if total_routes > visited_routes:
                # We don't have specific route names, suggest general navigation test
                actions.append(
                    {
                        "priority": 3,
                        "category": "route_gap",
                        "target": "routes",
                        "title": f"Add navigation tests ({visited_routes}/{total_routes} routes covered)",
                        "impact": f"Will improve route coverage from {round(visited_routes / total_routes * 100 if total_routes else 0)}%",
                        "prompt": (
                            f"There are {total_routes - visited_routes} unvisited routes. "
                            "Create test designs that navigate to each surface/page in the application. "
                            "Check the DSL for surface definitions to identify routes."
                        ),
                    }
                )

        # Sort by priority and limit
        actions.sort(key=lambda x: x["priority"])
        actions = actions[:max_actions]

        # Build summary
        overall = coverage.get("overall_coverage", 0)
        summary = {
            "runtime_coverage": round(overall, 1),
            "route_coverage": coverage.get("route_coverage", 0),
            "crud_coverage": coverage.get("entity_crud_coverage", 0),
            "ui_coverage": coverage.get("entity_ui_coverage", 0),
            "gaps_found": len(actions),
            "report_path": str(report_path),
        }

        # Extract test designs for direct saving
        test_designs = [a["test_design"] for a in actions if "test_design" in a]

        return json.dumps(
            {
                "summary": summary,
                "gap_count": len(actions),
                "guidance": (
                    "These test designs will fill gaps in runtime UX coverage. "
                    "Save them with save_test_designs to have them execute in future test runs."
                ),
                "actions": actions,
                "ready_to_save": test_designs,
                "next_steps": (
                    "1. Review the generated test designs\n"
                    "2. Save with: save_test_designs(designs=<ready_to_save>)\n"
                    "3. Run E2E tests to verify coverage improvement\n"
                    "4. Save updated coverage with save_runtime_coverage"
                ),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _generate_crud_steps(entity_name: str, operation: str) -> list[dict[str, Any]]:
    """Generate steps for a CRUD operation test."""
    entity_lower = entity_name.lower()
    route = f"/{entity_lower}s" if not entity_lower.endswith("s") else f"/{entity_lower}"

    if operation == "create":
        return [
            {"action": "navigate_to", "target": f"{route}/new", "rationale": "Go to create form"},
            {"action": "fill", "target": "form", "data": {}, "rationale": "Fill required fields"},
            {"action": "submit", "target": "form", "rationale": "Submit form"},
            {
                "action": "assert_visible",
                "target": f"entity:{entity_name}",
                "rationale": "Verify created",
            },
        ]
    elif operation == "read":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "first-item", "rationale": "Click first item"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify detail view"},
        ]
    elif operation == "update":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "edit-button", "rationale": "Click edit"},
            {"action": "fill", "target": "form", "data": {}, "rationale": "Modify fields"},
            {"action": "submit", "target": "form", "rationale": "Save changes"},
        ]
    elif operation == "delete":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list"},
            {"action": "click", "target": "delete-button", "rationale": "Click delete"},
            {"action": "click", "target": "confirm-delete", "rationale": "Confirm deletion"},
        ]
    elif operation == "list":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list view"},
            {
                "action": "assert_visible",
                "target": f"entity:{entity_name}",
                "rationale": "Verify list renders",
            },
        ]
    return []


def _generate_view_steps(entity_name: str, view: str) -> list[dict[str, Any]]:
    """Generate steps for a UI view test."""
    entity_lower = entity_name.lower()
    route = f"/{entity_lower}s" if not entity_lower.endswith("s") else f"/{entity_lower}"

    if view == "list":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list view"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify list renders"},
        ]
    elif view == "detail":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list first"},
            {"action": "click", "target": "first-item", "rationale": "Click to view detail"},
            {"action": "assert_visible", "target": "content", "rationale": "Verify detail view"},
        ]
    elif view == "create":
        return [
            {"action": "navigate_to", "target": f"{route}/new", "rationale": "Go to create form"},
            {"action": "assert_visible", "target": "form", "rationale": "Verify form renders"},
        ]
    elif view == "edit":
        return [
            {"action": "navigate_to", "target": route, "rationale": "Go to list first"},
            {"action": "click", "target": "edit-button", "rationale": "Click edit"},
            {"action": "assert_visible", "target": "form", "rationale": "Verify edit form"},
        ]
    return []


def save_runtime_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save runtime coverage report to dsl/tests/ for future analysis."""
    coverage_data = args.get("coverage_data")

    if not coverage_data:
        return json.dumps({"error": "coverage_data is required"}, indent=2)

    # Save to dsl/tests/runtime_coverage.json
    tests_dir = project_root / "dsl" / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    output_path = tests_dir / "runtime_coverage.json"
    with open(output_path, "w") as f:
        json.dump(coverage_data, f, indent=2)

    return json.dumps(
        {
            "success": True,
            "path": str(output_path),
            "message": "Runtime coverage saved. Use get_runtime_coverage_gaps to analyze gaps.",
        },
        indent=2,
    )


# ============================================================================
# SiteSpec Tool Implementations
# ============================================================================


def get_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load and return the SiteSpec from sitespec.yaml."""
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_sitespec,
        sitespec_exists,
    )

    use_defaults = args.get("use_defaults", True)

    try:
        sitespec = load_sitespec(project_root, use_defaults=use_defaults)

        # Convert to dict for JSON serialization
        result = {
            "exists": sitespec_exists(project_root),
            "version": sitespec.version,
            "brand": {
                "product_name": sitespec.brand.product_name,
                "tagline": sitespec.brand.tagline,
                "support_email": sitespec.brand.support_email,
                "company_legal_name": sitespec.brand.company_legal_name,
                "logo": {
                    "mode": sitespec.brand.logo.mode.value,
                    "text": sitespec.brand.logo.text,
                    "image_path": sitespec.brand.logo.image_path,
                },
            },
            "layout": {
                "theme": sitespec.layout.theme.value,
                "auth_entry": sitespec.layout.auth.primary_entry,
                "nav": {
                    "public": [
                        {"label": n.label, "href": n.href} for n in sitespec.layout.nav.public
                    ],
                    "authenticated": [
                        {"label": n.label, "href": n.href}
                        for n in sitespec.layout.nav.authenticated
                    ],
                },
                "footer": {
                    "columns": [
                        {
                            "title": col.title,
                            "links": [
                                {"label": link.label, "href": link.href} for link in col.links
                            ],
                        }
                        for col in sitespec.layout.footer.columns
                    ],
                    "disclaimer": sitespec.layout.footer.disclaimer,
                },
            },
            "pages": [
                {
                    "route": p.route,
                    "type": p.type.value,
                    "title": p.title,
                    "sections_count": len(p.sections),
                    "source": (
                        {"format": p.source.format.value, "path": p.source.path}
                        if p.source
                        else None
                    ),
                }
                for p in sitespec.pages
            ],
            "legal": {
                "terms": ({"route": sitespec.legal.terms.route} if sitespec.legal.terms else None),
                "privacy": (
                    {"route": sitespec.legal.privacy.route} if sitespec.legal.privacy else None
                ),
            },
            "auth_pages": {
                "login": {
                    "route": sitespec.auth_pages.login.route,
                    "enabled": sitespec.auth_pages.login.enabled,
                },
                "signup": {
                    "route": sitespec.auth_pages.signup.route,
                    "enabled": sitespec.auth_pages.signup.enabled,
                },
            },
            "integrations": {
                "app_mount_route": sitespec.integrations.app_mount_route,
                "auth_provider": sitespec.integrations.auth_provider.value,
            },
            "all_routes": sitespec.get_all_routes(),
        }

        return json.dumps(result, indent=2)

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error loading sitespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def validate_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate the SiteSpec for semantic correctness."""
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_sitespec,
        validate_sitespec,
    )

    check_content_files = args.get("check_content_files", True)

    try:
        sitespec = load_sitespec(project_root, use_defaults=True)
        result = validate_sitespec(
            sitespec,
            project_root,
            check_content_files=check_content_files,
        )

        return json.dumps(
            {
                "is_valid": result.is_valid,
                "error_count": len(result.errors),
                "warning_count": len(result.warnings),
                "errors": result.errors,
                "warnings": result.warnings,
            },
            indent=2,
        )

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error validating sitespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def scaffold_site_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Create default site structure with templates."""
    from dazzle.core.sitespec_loader import scaffold_site as do_scaffold_site

    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        result = do_scaffold_site(project_root, product_name, overwrite=overwrite)

        created_files: list[str] = []
        if result["sitespec"]:
            created_files.append(str(result["sitespec"]))
        content_files = result["content"]
        if isinstance(content_files, list):
            for f in content_files:
                created_files.append(str(f))

        return json.dumps(
            {
                "success": True,
                "product_name": product_name,
                "created_files": created_files,
                "message": f"Created {len(created_files)} files for site shell",
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Error scaffolding site")
        return json.dumps({"error": f"Failed to scaffold site: {e}"}, indent=2)
