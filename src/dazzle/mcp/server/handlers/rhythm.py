"""
Rhythm tool handlers.

Handles rhythm listing, retrieval, evaluation, coverage, and proposal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.core.ir.rhythm import LifecycleReport, LifecycleStep

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

    # Ambient phase — what the system surfaces when nothing is due
    lines.append("  phase ambient:")
    lines.append("    kind: ambient")
    first_surface = (
        list_surfaces[0]
        if list_surfaces
        else (detail_surfaces[0] if detail_surfaces else "dashboard")
    )
    lines.append('    scene check_status "Check Status":')
    lines.append(f"      on: {first_surface}")
    lines.append("      action: browse")
    lines.append('      expects: "relevant_information_visible"')
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

    # Seed KG relations (advisory — never blocks)
    _seed_gap_relations(gaps)

    # Persist
    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    (eval_dir / f"gaps-{ts}.json").write_text(json.dumps(result, indent=2))

    return json.dumps(result, indent=2)


def _seed_gap_relations(gaps: list[dict[str, Any]]) -> None:
    """Seed gap_blocks_scene relations into KG."""
    try:
        from dazzle.mcp.server.state import get_knowledge_graph

        graph = get_knowledge_graph()
        if graph is None:
            return
    except Exception:
        return

    import hashlib

    for gap in gaps:
        if gap.get("scene") and gap.get("rhythm"):
            gap_id = f"gap:{gap['kind']}:{hashlib.md5(gap['description'].encode()).hexdigest()[:8]}"
            scene_id = f"scene:{gap['rhythm']}.{gap['scene']}"
            try:
                graph.store.create_relation(
                    source_id=gap_id,
                    target_id=scene_id,
                    relation_type="gap_blocks_scene",
                    metadata={"severity": gap["severity"], "kind": gap["kind"]},
                )
            except Exception:
                pass  # KG seeding is advisory, never blocks


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


# ---------------------------------------------------------------------------
# Lifecycle handler
# ---------------------------------------------------------------------------


@wrap_handler_errors
def lifecycle_rhythm_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Report lifecycle status against the 8-step operating model."""
    from dazzle.core.ir.stories import StoryStatus

    app_spec = load_project_appspec(project_root)

    steps: list[LifecycleStep] = []

    # Step 1: model_domain — entities exist with fields
    entities_with_fields = [e for e in app_spec.domain.entities if getattr(e, "fields", None)]
    if entities_with_fields:
        s1_status = "complete"
        s1_evidence = f"{len(entities_with_fields)} entities with fields"
        s1_suggestions: list[str] = []
    else:
        s1_status = "not_started"
        s1_evidence = "No entities with fields found"
        s1_suggestions = ["Define entities with fields in your DSL files"]
    steps.append(
        LifecycleStep(
            step=1,
            name="model_domain",
            status=s1_status,
            evidence=s1_evidence,
            suggestions=s1_suggestions,
        )
    )

    # Step 2: write_stories — at least one ACCEPTED story
    accepted_stories = [s for s in app_spec.stories if s.status == StoryStatus.ACCEPTED]
    if accepted_stories:
        s2_status = "complete"
        s2_evidence = f"{len(accepted_stories)} accepted stories"
        s2_suggestions: list[str] = []
    elif app_spec.stories:
        s2_status = "partial"
        s2_evidence = f"{len(app_spec.stories)} stories, none accepted"
        s2_suggestions = ["Review and accept draft stories"]
    else:
        s2_status = "not_started"
        s2_evidence = "No stories found"
        s2_suggestions = ["Use story propose to generate stories from your domain"]
    steps.append(
        LifecycleStep(
            step=2,
            name="write_stories",
            status=s2_status,
            evidence=s2_evidence,
            suggestions=s2_suggestions,
        )
    )

    # Step 3: write_rhythms — rhythms exist, cover all personas
    all_persona_ids = {p.id for p in app_spec.personas}
    personas_with_rhythms = {r.persona for r in app_spec.rhythms}
    if app_spec.rhythms and personas_with_rhythms >= all_persona_ids:
        s3_status = "complete"
        s3_evidence = (
            f"{len(app_spec.rhythms)} rhythms covering "
            f"{len(personas_with_rhythms)}/{len(all_persona_ids)} personas"
        )
        s3_suggestions: list[str] = []
    elif app_spec.rhythms:
        uncovered = sorted(all_persona_ids - personas_with_rhythms)
        s3_status = "partial"
        s3_evidence = f"{len(app_spec.rhythms)} rhythms, missing personas: {', '.join(uncovered)}"
        s3_suggestions = [f"Use rhythm propose --persona {p}" for p in uncovered]
    else:
        s3_status = "not_started"
        s3_evidence = "No rhythms found"
        s3_suggestions = ["Use rhythm propose to generate rhythms for each persona"]
    steps.append(
        LifecycleStep(
            step=3,
            name="write_rhythms",
            status=s3_status,
            evidence=s3_evidence,
            suggestions=s3_suggestions,
        )
    )

    # Step 4: map_scenes_to_stories — all scenes have story: refs
    all_scenes: list[tuple[str, str]] = []  # (scene_name, story_ref or "")
    for r in app_spec.rhythms:
        for phase in r.phases:
            for scene in phase.scenes:
                all_scenes.append((scene.name, scene.story or ""))

    scenes_with_story = [s for s in all_scenes if s[1]]
    if all_scenes and len(scenes_with_story) == len(all_scenes):
        s4_status = "complete"
        s4_evidence = f"All {len(all_scenes)} scenes mapped to stories"
        s4_suggestions: list[str] = []
    elif scenes_with_story:
        unmapped = [s[0] for s in all_scenes if not s[1]]
        s4_status = "partial"
        s4_evidence = f"{len(scenes_with_story)}/{len(all_scenes)} scenes mapped"
        s4_suggestions = [f"Add story: reference to scene '{name}'" for name in unmapped[:5]]
    else:
        s4_status = "not_started"
        s4_evidence = "No scenes mapped to stories" if all_scenes else "No scenes defined"
        s4_suggestions = ["Add story: references to rhythm scenes"]
    steps.append(
        LifecycleStep(
            step=4,
            name="map_scenes_to_stories",
            status=s4_status,
            evidence=s4_evidence,
            suggestions=s4_suggestions,
        )
    )

    # Step 5: build_from_stories — .dazzle/test_designs/*.json exists
    td_dir = project_root / ".dazzle" / "test_designs"
    td_files = list(td_dir.glob("*.json")) if td_dir.exists() else []
    if td_files:
        s5_status = "complete"
        s5_evidence = f"{len(td_files)} test design files"
        s5_suggestions: list[str] = []
    else:
        s5_status = "not_started"
        s5_evidence = "No test design files found"
        s5_suggestions = ["Use test_design auto_populate to generate test designs"]
    steps.append(
        LifecycleStep(
            step=5,
            name="build_from_stories",
            status=s5_status,
            evidence=s5_evidence,
            suggestions=s5_suggestions,
        )
    )

    # Step 6: evaluate_from_scenes — .dazzle/evaluations/eval-*.json exists
    eval_dir = project_root / ".dazzle" / "evaluations"
    eval_files = list(eval_dir.glob("eval-*.json")) if eval_dir.exists() else []
    if eval_files:
        s6_status = "complete"
        s6_evidence = f"{len(eval_files)} evaluation files"
        s6_suggestions: list[str] = []
    else:
        s6_status = "not_started"
        s6_evidence = "No evaluation files found"
        s6_suggestions = ["Use rhythm evaluate with submit_scores to record evaluations"]
    steps.append(
        LifecycleStep(
            step=6,
            name="evaluate_from_scenes",
            status=s6_status,
            evidence=s6_evidence,
            suggestions=s6_suggestions,
        )
    )

    # Step 7: find_gaps — .dazzle/evaluations/gaps-*.json exists
    gap_files = list(eval_dir.glob("gaps-*.json")) if eval_dir.exists() else []
    if gap_files:
        s7_status = "complete"
        s7_evidence = f"{len(gap_files)} gap analysis files"
        s7_suggestions: list[str] = []
    else:
        s7_status = "not_started"
        s7_evidence = "No gap analysis files found"
        s7_suggestions = ["Use rhythm gaps to run gap analysis"]
    steps.append(
        LifecycleStep(
            step=7,
            name="find_gaps",
            status=s7_status,
            evidence=s7_evidence,
            suggestions=s7_suggestions,
        )
    )

    # Step 8: iterate — always "partial" if any other step is complete
    any_complete = any(s.status == "complete" for s in steps)
    if any_complete:
        s8_status = "partial"
        s8_evidence = "Iteration is ongoing"
        s8_suggestions: list[str] = ["Continue refining based on gap analysis"]
    else:
        s8_status = "not_started"
        s8_evidence = "No steps completed yet"
        s8_suggestions = ["Start by modelling your domain with entities"]
    steps.append(
        LifecycleStep(
            step=8,
            name="iterate",
            status=s8_status,
            evidence=s8_evidence,
            suggestions=s8_suggestions,
        )
    )

    # Classify maturity
    step_statuses = {s.name: s.status for s in steps}
    if all(
        step_statuses.get(n) == "complete"
        for n in [
            "model_domain",
            "write_stories",
            "write_rhythms",
            "map_scenes_to_stories",
            "build_from_stories",
            "evaluate_from_scenes",
            "find_gaps",
        ]
    ):
        maturity = "mature"
    elif all(
        step_statuses.get(n) == "complete"
        for n in [
            "model_domain",
            "write_stories",
            "write_rhythms",
            "map_scenes_to_stories",
            "build_from_stories",
        ]
    ):
        maturity = "evaluating"
    elif all(
        step_statuses.get(n) == "complete"
        for n in ["model_domain", "write_stories", "write_rhythms"]
    ):
        maturity = "building"
    else:
        maturity = "new_domain"

    # current_focus: first step that isn't "complete"
    current_focus = "iterate"
    for s in steps:
        if s.status != "complete":
            current_focus = s.name
            break

    report = LifecycleReport(
        steps=steps,
        current_focus=current_focus,
        maturity=maturity,
    )

    return json.dumps(report.model_dump(), indent=2)
