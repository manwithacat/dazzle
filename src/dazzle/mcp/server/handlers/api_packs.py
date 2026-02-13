"""
API packs tool handlers.

Handles API pack listing, searching, details, and DSL generation.
"""

from __future__ import annotations

import json
from typing import Any

from dazzle.mcp.server.progress import ProgressContext
from dazzle.mcp.server.progress import noop as _noop_progress


def list_api_packs_handler(args: dict[str, Any]) -> str:
    """List all available API packs."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    from dazzle.api_kb import list_packs

    progress.log_sync("Listing API packs...")
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
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    from dazzle.api_kb import search_packs

    progress.log_sync("Searching API packs...")
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
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    from dazzle.api_kb import load_pack

    pack_name = args.get("pack_name")
    if pack_name:
        progress.log_sync(f"Loading API pack '{pack_name}'...")
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
            "infrastructure": _serialize_infrastructure(pack.infrastructure),
        },
        indent=2,
    )


def _serialize_infrastructure(infra: Any) -> dict[str, Any] | None:
    """Serialize InfrastructureSpec to JSON-compatible dict."""
    if infra is None:
        return None
    result: dict[str, Any] = {"hosting": infra.hosting}
    if infra.docker:
        result["docker"] = {
            "image": infra.docker.image,
            "port": infra.docker.port,
            "requires": infra.docker.requires,
            "environment": infra.docker.environment,
            "healthcheck_path": infra.docker.healthcheck_path,
            "volumes": infra.docker.volumes,
        }
    if infra.local_env_overrides:
        result["local_env_overrides"] = infra.local_env_overrides
    if infra.sandbox:
        result["sandbox"] = {
            "available": infra.sandbox.available,
            "env_prefix": infra.sandbox.env_prefix,
            "docs": infra.sandbox.docs,
        }
    return result


def generate_service_dsl_handler(args: dict[str, Any]) -> str:
    """Generate DSL service and foreign_model blocks from an API pack."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    from dazzle.api_kb import load_pack

    progress.log_sync("Generating DSL from API pack...")
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


def infrastructure_handler(project_path: Any, args: dict[str, Any]) -> str:
    """Discover infrastructure requirements for services declared in DSL."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Discovering infrastructure requirements...")
    from pathlib import Path

    from dazzle.api_kb import load_pack
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    if project_path is None:
        return json.dumps({"error": "No active project"})

    try:
        manifest = load_manifest(Path(project_path) / "dazzle.toml")
        dsl_files = discover_dsl_files(Path(project_path), manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        return json.dumps({"error": f"Failed to load project: {e}"})

    services: list[dict[str, Any]] = []
    for svc in getattr(appspec, "services", []) or []:
        spec_inline = getattr(svc, "spec_inline", None) or ""
        pack_name = spec_inline.removeprefix("pack:") if spec_inline.startswith("pack:") else None
        pack = load_pack(pack_name) if pack_name else None

        entry: dict[str, Any] = {
            "service": svc.name,
            "title": getattr(svc, "title", None),
            "pack": pack_name,
        }

        if pack and pack.infrastructure:
            entry["infrastructure"] = _serialize_infrastructure(pack.infrastructure)
            entry["env_vars"] = [
                {"name": e.name, "required": e.required, "description": e.description}
                for e in pack.env_vars
            ]
        else:
            entry["infrastructure"] = None
            entry["hint"] = (
                "No infrastructure metadata in API pack" if pack_name else "No pack reference"
            )

        services.append(entry)

    # Classify
    self_hosted = [
        s
        for s in services
        if (s.get("infrastructure") or {}).get("hosting") in ("self_hosted", "both")
    ]
    cloud_only = [
        s for s in services if (s.get("infrastructure") or {}).get("hosting") == "cloud_only"
    ]
    unknown = [s for s in services if s.get("infrastructure") is None]

    return json.dumps(
        {
            "service_count": len(services),
            "self_hosted_count": len(self_hosted),
            "cloud_only_count": len(cloud_only),
            "unknown_count": len(unknown),
            "services": services,
        },
        indent=2,
    )


def get_env_vars_for_packs_handler(args: dict[str, Any]) -> str:
    """Get .env.example content for specified packs or all packs."""
    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Generating env vars...")
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
