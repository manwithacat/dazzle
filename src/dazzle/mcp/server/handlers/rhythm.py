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
    """Evaluate a rhythm — static analysis of completeness, or submit scores."""
    app_spec = load_project_appspec(project_root)
    name = args.get("name")
    action = args.get("action", "evaluate")

    rhythm = None
    for r in app_spec.rhythms:
        if r.name == name:
            rhythm = r
            break

    if rhythm is None:
        return error_response(f"Rhythm '{name}' not found")

    if action == "submit_scores":
        return _submit_scores(project_root, name, args.get("scores", []))

    # Structural evaluation
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

    stored_scores = _load_latest_scores(project_root, name)

    return json.dumps(
        {
            "rhythm": name,
            "summary": f"{passed}/{total} checks passed",
            "checks": checks,
            "scene_scores": stored_scores,
        },
        indent=2,
    )


def _submit_scores(project_root: Path, rhythm_name: str, scores_data: list[dict[str, Any]]) -> str:
    """Persist agent-produced scene evaluation scores."""
    import datetime

    from dazzle.core.ir.rhythm import SceneEvaluation

    evaluations = [SceneEvaluation(**s) for s in scores_data]

    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    path = eval_dir / f"eval-{ts}.json"

    data = {
        "rhythm": rhythm_name,
        "timestamp": ts,
        "evaluations": [e.model_dump() for e in evaluations],
    }
    path.write_text(json.dumps(data, indent=2))

    return json.dumps({"stored": str(path), "count": len(evaluations)})


def _load_latest_scores(project_root: Path, rhythm_name: str) -> list[dict[str, Any]] | None:
    """Load most recent evaluation scores for a rhythm."""
    eval_dir = project_root / ".dazzle" / "evaluations"
    if not eval_dir.exists():
        return None

    files = sorted(eval_dir.glob("eval-*.json"), reverse=True)
    for f in files:
        data = json.loads(f.read_text())
        if data.get("rhythm") == rhythm_name:
            return data.get("evaluations")
    return None


@wrap_handler_errors
def coverage_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse persona and surface coverage across all rhythms."""
    app_spec = load_project_appspec(project_root)

    all_persona_ids = {p.id for p in app_spec.personas}
    all_surface_names = {s.name for s in app_spec.surfaces}

    personas_with_rhythms: set[str] = set()
    personas_with_ambient: set[str] = set()
    surfaces_exercised: set[str] = set()

    for r in app_spec.rhythms:
        personas_with_rhythms.add(r.persona)
        for phase in r.phases:
            if phase.kind and phase.kind.value == "ambient":
                personas_with_ambient.add(r.persona)
            for scene in phase.scenes:
                surfaces_exercised.add(scene.surface)

    return json.dumps(
        {
            "total_personas": len(all_persona_ids),
            "total_surfaces": len(all_surface_names),
            "total_rhythms": len(app_spec.rhythms),
            "personas_with_rhythms": sorted(personas_with_rhythms),
            "personas_without_rhythms": sorted(all_persona_ids - personas_with_rhythms),
            "personas_with_ambient": sorted(personas_with_ambient),
            "personas_without_ambient": sorted(personas_with_rhythms - personas_with_ambient),
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


@wrap_handler_errors
def gaps_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse gaps between scenes and stories."""
    import datetime

    from dazzle.core.ir.stories import StoryStatus

    app_spec = load_project_appspec(project_root)

    gaps: list[dict[str, Any]] = []
    story_by_id = {s.story_id: s for s in app_spec.stories}
    scene_story_refs: set[str] = set()
    persona_has_ambient: dict[str, bool] = {}
    personas_with_rhythms: set[str] = set()

    for rhythm in app_spec.rhythms:
        personas_with_rhythms.add(rhythm.persona)
        has_ambient = False

        for phase in rhythm.phases:
            if phase.kind and phase.kind.value == "ambient":
                has_ambient = True

            for scene in phase.scenes:
                if scene.story:
                    scene_story_refs.add(scene.story)
                    story = story_by_id.get(scene.story)
                    if story is None:
                        gaps.append(
                            {
                                "kind": "capability",
                                "severity": "blocking",
                                "scene": scene.name,
                                "phase": phase.name,
                                "rhythm": rhythm.name,
                                "persona": rhythm.persona,
                                "story_ref": scene.story,
                                "surface_ref": scene.surface,
                                "description": (
                                    f"Scene '{scene.name}' references "
                                    f"non-existent story '{scene.story}'"
                                ),
                            }
                        )
                    elif story.status == StoryStatus.DRAFT:
                        gaps.append(
                            {
                                "kind": "capability",
                                "severity": "blocking",
                                "scene": scene.name,
                                "phase": phase.name,
                                "rhythm": rhythm.name,
                                "persona": rhythm.persona,
                                "story_ref": scene.story,
                                "surface_ref": scene.surface,
                                "description": (
                                    f"Scene '{scene.name}' references DRAFT story '{scene.story}'"
                                ),
                            }
                        )
                else:
                    gaps.append(
                        {
                            "kind": "unmapped",
                            "severity": "advisory",
                            "scene": scene.name,
                            "phase": phase.name,
                            "rhythm": rhythm.name,
                            "persona": rhythm.persona,
                            "story_ref": None,
                            "surface_ref": scene.surface,
                            "description": f"Scene '{scene.name}' has no story: reference",
                        }
                    )

        persona_has_ambient[rhythm.persona] = has_ambient

    # Orphan stories
    for story_id, story in story_by_id.items():
        if story_id not in scene_story_refs:
            gaps.append(
                {
                    "kind": "orphan",
                    "severity": "advisory",
                    "scene": None,
                    "phase": None,
                    "rhythm": "",
                    "persona": getattr(story, "actor", ""),
                    "story_ref": story_id,
                    "surface_ref": None,
                    "description": f"Story '{story_id}' is not referenced by any scene",
                }
            )

    # Ambient gaps
    for persona_id, has_ambient in persona_has_ambient.items():
        if not has_ambient:
            gaps.append(
                {
                    "kind": "ambient",
                    "severity": "advisory",
                    "scene": None,
                    "phase": None,
                    "rhythm": "",
                    "persona": persona_id,
                    "story_ref": None,
                    "surface_ref": None,
                    "description": f"Persona '{persona_id}' has no ambient phase",
                }
            )

    # Unscored personas
    personas_with_stories = {s.actor for s in app_spec.stories}
    for pid in sorted(personas_with_stories - personas_with_rhythms):
        gaps.append(
            {
                "kind": "unscored",
                "severity": "advisory",
                "scene": None,
                "phase": None,
                "rhythm": "",
                "persona": pid,
                "story_ref": None,
                "surface_ref": None,
                "description": f"Persona '{pid}' has stories but no rhythm",
            }
        )

    # Layer in evaluated gaps from stored scores
    _layer_evaluated_gaps(project_root, gaps)

    # Build summary
    summary = _build_gaps_summary(gaps)

    # Sort for roadmap: blocking > degraded > advisory
    severity_order = {"blocking": 0, "degraded": 1, "advisory": 2}
    roadmap = sorted(gaps, key=lambda g: severity_order.get(g["severity"], 9))

    result = {"gaps": gaps, "summary": summary, "roadmap_order": roadmap}

    # Persist
    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    (eval_dir / f"gaps-{ts}.json").write_text(json.dumps(result, indent=2))

    return json.dumps(result, indent=2)


def _build_gaps_summary(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate gap counts."""
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_persona: dict[str, int] = {}
    for g in gaps:
        by_kind[g["kind"]] = by_kind.get(g["kind"], 0) + 1
        by_severity[g["severity"]] = by_severity.get(g["severity"], 0) + 1
        if g["persona"]:
            by_persona[g["persona"]] = by_persona.get(g["persona"], 0) + 1
    return {
        "total": len(gaps),
        "by_kind": by_kind,
        "by_severity": by_severity,
        "by_persona": by_persona,
    }


def _layer_evaluated_gaps(project_root: Path, gaps: list[dict[str, Any]]) -> None:
    """Layer in gaps from stored evaluation scores."""
    eval_dir = project_root / ".dazzle" / "evaluations"
    if not eval_dir.exists():
        return

    files = sorted(eval_dir.glob("eval-*.json"), reverse=True)
    if not files:
        return

    # Use the most recent evaluation file
    data = json.loads(files[0].read_text())
    evaluations = data.get("evaluations", [])
    rhythm_name = data.get("rhythm", "")

    for ev in evaluations:
        dims = {d["dimension"]: d["score"] for d in ev.get("dimensions", [])}
        scene_name = ev.get("scene_name", "")
        phase_name = ev.get("phase_name", "")

        if dims.get("action") == "fail":
            gaps.append(
                {
                    "kind": "capability",
                    "severity": "blocking",
                    "scene": scene_name,
                    "phase": phase_name,
                    "rhythm": rhythm_name,
                    "persona": "",
                    "story_ref": ev.get("story_ref"),
                    "surface_ref": None,
                    "description": f"Scene '{scene_name}' failed action dimension",
                }
            )
        elif dims.get("arrival") == "fail" or dims.get("orientation") == "fail":
            gaps.append(
                {
                    "kind": "surface",
                    "severity": "degraded",
                    "scene": scene_name,
                    "phase": phase_name,
                    "rhythm": rhythm_name,
                    "persona": "",
                    "story_ref": None,
                    "surface_ref": None,
                    "description": (f"Scene '{scene_name}' failed arrival/orientation dimension"),
                }
            )
        elif dims.get("completion") == "fail":
            gaps.append(
                {
                    "kind": "workflow",
                    "severity": "blocking",
                    "scene": scene_name,
                    "phase": phase_name,
                    "rhythm": rhythm_name,
                    "persona": "",
                    "story_ref": None,
                    "surface_ref": None,
                    "description": f"Scene '{scene_name}' failed completion dimension",
                }
            )
