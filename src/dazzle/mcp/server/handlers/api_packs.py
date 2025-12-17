"""
API packs tool handlers.

Handles API pack listing, searching, details, and DSL generation.
"""

from __future__ import annotations

import json
from typing import Any


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
