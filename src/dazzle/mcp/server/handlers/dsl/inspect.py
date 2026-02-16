"""DSL entity and surface inspection handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..common import extract_progress, load_project_appspec, wrap_handler_errors


@wrap_handler_errors
def inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    progress = extract_progress(args)
    entity_name = args.get("entity_name") or args.get("name")
    if not entity_name:
        return json.dumps({"error": "entity_name required"})

    progress.log_sync(f"Inspecting entity '{entity_name}'...")
    app_spec = load_project_appspec(project_root)

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


@wrap_handler_errors
def inspect_surface(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a surface definition."""
    progress = extract_progress(args)
    surface_name = args.get("surface_name") or args.get("name")
    if not surface_name:
        return json.dumps({"error": "surface_name required"})

    progress.log_sync(f"Inspecting surface '{surface_name}'...")
    app_spec = load_project_appspec(project_root)

    surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
    if not surface:
        return json.dumps({"error": f"Surface '{surface_name}' not found"})

    info: dict[str, Any] = {
        "name": surface.name,
        "entity": surface.entity_ref,
        "mode": str(surface.mode),
        "description": surface.title,
        "sections": len(surface.sections) if surface.sections else 0,
    }
    if hasattr(surface, "ux") and surface.ux:
        ux = surface.ux
        info["ux"] = {
            "purpose": ux.purpose,
            "sort": [str(s) for s in ux.sort] if ux.sort else [],
            "filter": list(ux.filter) if ux.filter else [],
            "search": list(ux.search) if ux.search else [],
            "empty_message": ux.empty_message,
            "attention_signals": len(ux.attention_signals),
            "persona_variants": [p.persona for p in ux.persona_variants],
        }
    return json.dumps(info, indent=2)
