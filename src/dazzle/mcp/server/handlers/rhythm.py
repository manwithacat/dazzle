"""
Rhythm tool handlers.

The ``rhythm`` MCP tool registers ``list``, ``get`` and ``coverage``; the pipeline
calls ``gaps_rhythm_handler``.
"""

import json
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from dazzle.core.ir.stories import StoryStatus

from .common import error_response, load_project_appspec, wrap_handler_errors

logger = logging.getLogger(__name__)


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
                            "cadence": p.cadence,
                            "depends_on": p.depends_on,
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


def _surfaces_accessible_by_persona(persona_id: str, surfaces: list[Any]) -> set[str]:
    """Compute which surfaces a persona can access based on ACL rules.

    Rules:
    - No access spec or require_auth=False → accessible to all
    - allow_personas set and persona not in it → inaccessible
    - deny_personas set and persona in it → inaccessible
    - Otherwise → accessible
    """
    accessible: set[str] = set()
    for s in surfaces:
        access = getattr(s, "access", None)
        if access is None or not access.require_auth:
            accessible.add(s.name)
            continue
        if access.deny_personas and persona_id in access.deny_personas:
            continue
        if access.allow_personas and persona_id not in access.allow_personas:
            continue
        accessible.add(s.name)
    return accessible


@wrap_handler_errors
def coverage_rhythms_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse persona and surface coverage across all rhythms."""
    app_spec = load_project_appspec(project_root)

    all_persona_ids = {p.id for p in app_spec.personas}
    all_surface_names = {s.name for s in app_spec.surfaces}
    all_workspace_names = {w.name for w in getattr(app_spec, "workspaces", [])}

    personas_with_rhythms: set[str] = set()
    personas_with_ambient: set[str] = set()
    surfaces_exercised: set[str] = set()
    workspaces_exercised: set[str] = set()
    # Per-persona: which surfaces/workspaces their rhythms exercise
    persona_targets: dict[str, set[str]] = {}

    for r in app_spec.rhythms:
        personas_with_rhythms.add(r.persona)
        if r.persona not in persona_targets:
            persona_targets[r.persona] = set()
        for phase in r.phases:
            if phase.kind and phase.kind.value == "ambient":
                personas_with_ambient.add(r.persona)
            for scene in phase.scenes:
                if scene.surface is None:
                    continue
                persona_targets[r.persona].add(scene.surface)
                if scene.surface in all_workspace_names:
                    workspaces_exercised.add(scene.surface)
                else:
                    surfaces_exercised.add(scene.surface)

    # Per-persona scoped coverage (surfaces + workspaces)
    persona_coverage: dict[str, dict[str, Any]] = {}
    for pid in sorted(personas_with_rhythms):
        accessible = _surfaces_accessible_by_persona(pid, app_spec.surfaces)
        # Workspaces are always accessible to their persona (no ACL on workspace level)
        accessible_all = accessible | all_workspace_names
        exercised = persona_targets.get(pid, set())
        exercised_accessible = exercised & accessible_all
        pct = round(100 * len(exercised_accessible) / len(accessible_all)) if accessible_all else 0
        persona_coverage[pid] = {
            "accessible_surfaces": len(accessible),
            "accessible_workspaces": len(all_workspace_names),
            "exercised": len(exercised_accessible),
            "coverage_pct": pct,
            "unexercised": sorted(accessible_all - exercised_accessible),
        }

    return json.dumps(
        {
            "total_personas": len(all_persona_ids),
            "total_surfaces": len(all_surface_names),
            "total_workspaces": len(all_workspace_names),
            "total_rhythms": len(app_spec.rhythms),
            "personas_with_rhythms": sorted(personas_with_rhythms),
            "personas_without_rhythms": sorted(all_persona_ids - personas_with_rhythms),
            "personas_with_ambient": sorted(personas_with_ambient),
            "personas_without_ambient": sorted(personas_with_rhythms - personas_with_ambient),
            "surfaces_exercised": sorted(surfaces_exercised),
            "surfaces_unexercised": sorted(all_surface_names - surfaces_exercised),
            "workspaces_exercised": sorted(workspaces_exercised),
            "workspaces_unexercised": sorted(all_workspace_names - workspaces_exercised),
            "persona_coverage": persona_coverage,
        },
        indent=2,
    )


def rhythm_gaps_impl(project_root: Path) -> dict[str, Any]:
    """Analyse gaps between scenes and stories."""
    import datetime

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
                    "persona": story.persona,
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
    personas_with_stories = {s.persona for s in app_spec.stories}
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

    result: dict[str, Any] = {"gaps": gaps, "summary": summary, "roadmap_order": roadmap}

    # Seed KG relations (advisory — never blocks)
    _seed_gap_relations(gaps)

    # Persist
    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    (eval_dir / f"gaps-{ts}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


@wrap_handler_errors
def gaps_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyse gaps between scenes and stories."""
    return json.dumps(rhythm_gaps_impl(project_root), indent=2)


def _seed_gap_relations(gaps: list[dict[str, Any]]) -> None:
    """Seed gap_blocks_scene relations into KG."""
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        graph = get_knowledge_graph()
        if graph is None:
            return
    except Exception:
        logger.debug("ignored exception in rhythm.py:847", exc_info=True)
        return

    import hashlib

    for gap in gaps:
        if gap.get("scene") and gap.get("rhythm"):
            gap_id = f"gap:{gap['kind']}:{hashlib.md5(gap['description'].encode(), usedforsecurity=False).hexdigest()[:8]}"
            scene_id = f"scene:{gap['rhythm']}.{gap['scene']}"
            # KG seeding is advisory, never blocks (#smells-1.1).
            with suppress(Exception):
                graph.create_relation(
                    source_id=gap_id,
                    target_id=scene_id,
                    relation_type="gap_blocks_scene",
                    metadata={"severity": gap["severity"], "kind": gap["kind"]},
                )


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
    data = json.loads(files[0].read_text(encoding="utf-8"))
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
