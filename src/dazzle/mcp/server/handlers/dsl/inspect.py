"""DSL entity and surface inspection handlers."""

import json
from pathlib import Path
from typing import Any

from ..common import error_response, extract_progress, load_project_appspec, wrap_handler_errors


@wrap_handler_errors
def inspect_entity(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect an entity definition."""
    progress = extract_progress(args)
    entity_name = args.get("entity_name") or args.get("name")
    if not entity_name:
        return error_response("entity_name required")

    progress.log_sync(f"Inspecting entity '{entity_name}'...")
    app_spec = load_project_appspec(project_root)

    entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
    if not entity:
        return error_response(f"Entity '{entity_name}' not found")

    # Child entities' own IR fields don't include base fields — synthesise the
    # inherited view here so agents see the full field set when inspecting a
    # subtype child.
    base_entity = None
    if entity.subtype_of is not None:
        base_entity = next(
            (e for e in app_spec.domain.entities if e.name == entity.subtype_of),
            None,
        )

    def _field_dict(f: Any, inherited_from: str | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": f.name,
            "type": str(f.type.kind),
            "required": f.is_required,
            "modifiers": [str(m) for m in f.modifiers],
        }
        if inherited_from is not None:
            d["inherited_from"] = inherited_from
        return d

    fields: list[dict[str, Any]] = [_field_dict(f) for f in entity.fields]
    if base_entity is not None:
        # Append base fields after the child's own — preserves child's
        # primary ordering while making inheritance explicit to agents.
        own_names = {f.name for f in entity.fields}
        for f in base_entity.fields:
            if f.name in own_names:
                # Defensive: linker should reject overlap but if a future
                # rule allows override, prefer the child's declaration.
                continue
            fields.append(_field_dict(f, inherited_from=base_entity.name))

    return json.dumps(
        {
            "name": entity.name,
            "description": entity.title,
            "subtype_of": entity.subtype_of,
            "subtype_children": sorted(entity.subtype_children),
            "fields": fields,
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
        return error_response("surface_name required")

    progress.log_sync(f"Inspecting surface '{surface_name}'...")
    app_spec = load_project_appspec(project_root)

    surface = next((s for s in app_spec.surfaces if s.name == surface_name), None)
    if not surface:
        return error_response(f"Surface '{surface_name}' not found")

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
