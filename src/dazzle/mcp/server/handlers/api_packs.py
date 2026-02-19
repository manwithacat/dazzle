"""
API packs tool handlers.

Handles API pack listing, searching, details, and DSL generation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import extract_progress, wrap_handler_errors


@wrap_handler_errors
def list_api_packs_handler(args: dict[str, Any]) -> str:
    """List all available API packs."""
    progress = extract_progress(args)
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


@wrap_handler_errors
def search_api_packs_handler(args: dict[str, Any]) -> str:
    """Search for API packs by category, provider, or query."""
    progress = extract_progress(args)
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


@wrap_handler_errors
def get_api_pack_handler(args: dict[str, Any]) -> str:
    """Get full details of an API pack."""
    progress = extract_progress(args)
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


@wrap_handler_errors
def generate_service_dsl_handler(args: dict[str, Any]) -> str:
    """Generate DSL service and foreign_model blocks from an API pack."""
    progress = extract_progress(args)
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


@wrap_handler_errors
def infrastructure_handler(project_path: Path | None, args: dict[str, Any]) -> str:
    """Discover infrastructure requirements for services declared in DSL."""
    progress = extract_progress(args)
    progress.log_sync("Discovering infrastructure requirements...")
    from dazzle.api_kb import load_pack

    from .common import load_project_appspec

    if project_path is None:
        return json.dumps({"error": "No active project"})

    appspec = load_project_appspec(Path(project_path))
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


@wrap_handler_errors
def scaffold_pack_handler(project_path: Path | None, args: dict[str, Any]) -> str:
    """Scaffold a new API pack TOML from OpenAPI spec or blank template."""
    progress = extract_progress(args)
    progress.log_sync("Scaffolding API pack...")

    from dazzle.api_kb.openapi_importer import import_from_openapi, scaffold_blank

    openapi_spec = args.get("openapi_spec")
    openapi_url = args.get("openapi_url")
    provider = args.get("provider", "MyVendor")
    category = args.get("category", "api")
    pack_name = args.get("pack_name", "")

    toml_content: str

    if openapi_spec:
        # Convert OpenAPI spec dict to TOML
        toml_content = import_from_openapi(openapi_spec)
    elif openapi_url:
        # Fetch and convert
        import json as _json

        import httpx

        try:
            resp = httpx.get(openapi_url, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "yaml" in content_type or openapi_url.endswith((".yaml", ".yml")):
                try:
                    import yaml

                    spec_data = yaml.safe_load(resp.text)
                except ImportError:
                    return _json.dumps(
                        {
                            "error": "PyYAML required for YAML OpenAPI specs. Install with: pip install pyyaml"
                        }
                    )
            else:
                spec_data = resp.json()
            toml_content = import_from_openapi(spec_data)
        except Exception as e:
            return _json.dumps({"error": f"Failed to fetch OpenAPI spec: {e}"})
    else:
        # Blank template
        if not pack_name:
            pack_name = f"{provider.lower().replace(' ', '_')}_{category}"
        toml_content = scaffold_blank(provider, category, pack_name)

    # Determine save path
    if not pack_name:
        # Extract from generated TOML
        import re

        match = re.search(r'name\s*=\s*"([^"]+)"', toml_content)
        pack_name = match.group(1) if match else "custom_pack"

    # Derive provider directory from pack_name
    parts = pack_name.split("_", 1)
    vendor_dir = parts[0] if len(parts) > 1 else pack_name
    save_path = f".dazzle/api_packs/{vendor_dir}/{pack_name}.toml"

    return json.dumps(
        {
            "toml": toml_content,
            "save_path": save_path,
            "hint": f'Save to {save_path} in your project directory, then reference with spec: inline "pack:{pack_name}"',
        },
        indent=2,
    )


@wrap_handler_errors
def get_env_vars_for_packs_handler(args: dict[str, Any]) -> str:
    """Get .env.example content for specified packs or all packs."""
    progress = extract_progress(args)
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
