"""
Rhythm tool handlers.

Handles rhythm listing, retrieval, evaluation, coverage, and proposal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import error_response, load_project_appspec, wrap_handler_errors


@wrap_handler_errors
def list_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all rhythms in the project."""
    app_spec = load_project_appspec(project_root)

    rhythms = []
    for r in app_spec.rhythms:
        rhythms.append(
            {
                "name": r.name,
                "title": r.title,
                "persona": r.persona,
                "cadence": r.cadence,
                "phase_count": len(r.phases),
                "ambient_phases": sum(1 for p in r.phases if p.kind and p.kind.value == "ambient"),
                "scene_count": sum(len(p.scenes) for p in r.phases),
            }
        )

    return json.dumps({"rhythms": rhythms}, indent=2)


@wrap_handler_errors
def get_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get full details of a specific rhythm."""
    app_spec = load_project_appspec(project_root)
    name = args.get("name")

    for r in app_spec.rhythms:
        if r.name == name:
            return json.dumps(
                {
                    "name": r.name,
                    "title": r.title,
                    "persona": r.persona,
                    "cadence": r.cadence,
                    "phases": [
                        {
                            "name": p.name,
                            "kind": p.kind.value if p.kind else None,
                            "scenes": [
                                {
                                    "name": s.name,
                                    "title": s.title,
                                    "surface": s.surface,
                                    "actions": s.actions,
                                    "entity": s.entity,
                                    "expects": s.expects,
                                    "story": s.story,
                                }
                                for s in p.scenes
                            ],
                        }
                        for p in r.phases
                    ],
                },
                indent=2,
            )

    return error_response(f"Rhythm '{name}' not found")


@wrap_handler_errors
def evaluate_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Evaluate a rhythm — static analysis of completeness."""
    app_spec = load_project_appspec(project_root)
    name = args.get("name")

    rhythm = None
    for r in app_spec.rhythms:
        if r.name == name:
            rhythm = r
            break

    if rhythm is None:
        return error_response(f"Rhythm '{name}' not found")

    surface_names = {s.name for s in app_spec.surfaces}
    entity_names = {e.name for e in app_spec.domain.entities}
    persona_ids = {p.id for p in app_spec.personas}

    surface_entities: dict[str, str | None] = {}
    for s in app_spec.surfaces:
        surface_entities[s.name] = getattr(s, "entity_ref", None)

    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "check": "persona_exists",
            "target": rhythm.persona,
            "pass": rhythm.persona in persona_ids,
        }
    )

    for phase in rhythm.phases:
        for scene in phase.scenes:
            checks.append(
                {
                    "check": "surface_exists",
                    "phase": phase.name,
                    "scene": scene.name,
                    "target": scene.surface,
                    "pass": scene.surface in surface_names,
                }
            )

            if scene.entity:
                entity_exists = scene.entity in entity_names
                checks.append(
                    {
                        "check": "entity_exists",
                        "phase": phase.name,
                        "scene": scene.name,
                        "target": scene.entity,
                        "pass": entity_exists,
                    }
                )

                if scene.surface in surface_entities:
                    surf_entity = surface_entities[scene.surface]
                    entity_match = surf_entity == scene.entity if surf_entity else False
                    checks.append(
                        {
                            "check": "surface_entity_match",
                            "phase": phase.name,
                            "scene": scene.name,
                            "surface": scene.surface,
                            "entity": scene.entity,
                            "surface_entity": surf_entity,
                            "pass": entity_match,
                        }
                    )

    passed = sum(1 for c in checks if c["pass"])
    total = len(checks)

    return json.dumps(
        {
            "rhythm": name,
            "summary": f"{passed}/{total} checks passed",
            "checks": checks,
        },
        indent=2,
    )


@wrap_handler_errors
def coverage_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse persona and surface coverage across all rhythms."""
    app_spec = load_project_appspec(project_root)

    all_persona_ids = {p.id for p in app_spec.personas}
    all_surface_names = {s.name for s in app_spec.surfaces}

    personas_with_rhythms: set[str] = set()
    surfaces_exercised: set[str] = set()

    for r in app_spec.rhythms:
        personas_with_rhythms.add(r.persona)
        for phase in r.phases:
            for scene in phase.scenes:
                surfaces_exercised.add(scene.surface)

    return json.dumps(
        {
            "total_personas": len(all_persona_ids),
            "total_surfaces": len(all_surface_names),
            "total_rhythms": len(app_spec.rhythms),
            "personas_with_rhythms": sorted(personas_with_rhythms),
            "personas_without_rhythms": sorted(all_persona_ids - personas_with_rhythms),
            "surfaces_exercised": sorted(surfaces_exercised),
            "surfaces_unexercised": sorted(all_surface_names - surfaces_exercised),
        },
        indent=2,
    )


@wrap_handler_errors
def propose_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Propose a rhythm for a given persona based on app analysis."""
    app_spec = load_project_appspec(project_root)
    persona_id = args.get("persona")

    if not persona_id:
        return error_response("'persona' parameter required for propose")

    persona = None
    for p in app_spec.personas:
        if p.id == persona_id:
            persona = p
            break

    if persona is None:
        return error_response(f"Persona '{persona_id}' not found")

    list_surfaces: list[str] = []
    detail_surfaces: list[str] = []

    for s in app_spec.surfaces:
        mode = getattr(s, "mode", None)
        if mode == "list":
            list_surfaces.append(s.name)
        else:
            detail_surfaces.append(s.name)

    lines = [
        f'rhythm {persona_id}_journey "{getattr(persona, "name", persona_id)} Journey":',
        f"  persona: {persona_id}",
        "",
    ]

    if list_surfaces:
        lines.append("  phase discovery:")
        for sname in list_surfaces:
            safe = sname.replace(" ", "_").lower()
            lines.append(f'    scene browse_{safe} "Browse {sname}":')
            lines.append(f"      on: {sname}")
            lines.append("      action: browse")
            lines.append("")

    if detail_surfaces:
        lines.append("  phase engagement:")
        for sname in detail_surfaces:
            safe = sname.replace(" ", "_").lower()
            entity_ref = None
            for s in app_spec.surfaces:
                if s.name == sname:
                    entity_ref = getattr(s, "entity_ref", None)
                    break
            lines.append(f'    scene use_{safe} "Use {sname}":')
            lines.append(f"      on: {sname}")
            lines.append("      action: submit")
            if entity_ref:
                lines.append(f"      entity: {entity_ref}")
            lines.append("")

    return json.dumps(
        {
            "persona": persona_id,
            "proposed_dsl": "\n".join(lines),
        },
        indent=2,
    )
