"""
Story/behaviour tool handlers.

Handles DSL spec extraction, story retrieval, the story wall and composition views.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.core.ir.stories import StoryStatus

from .common import extract_progress, load_project_appspec, wrap_handler_errors
from .serializers import (
    serialize_entity_detail,
    serialize_entity_summary,
    serialize_story,
    serialize_story_summary,
    serialize_surface_detail,
    serialize_surface_summary,
)


@wrap_handler_errors
def get_dsl_spec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get DSL specification with lazy loading support.

    Default: returns compact summaries of all entities and surfaces.
    With entity_names/surface_names: returns full details for those items only.
    """
    progress = extract_progress(args)
    progress.log_sync("Loading DSL specification...")
    app_spec = load_project_appspec(project_root)

    entity_names: list[str] = args.get("entity_names") or []
    surface_names: list[str] = args.get("surface_names") or []
    detail_requested = bool(entity_names or surface_names)

    if detail_requested:
        # Return full details for requested items only
        result: dict[str, Any] = {
            "project_path": str(project_root),
            "app_name": app_spec.name,
        }

        if entity_names:
            entity_set = set(entity_names)
            result["entities"] = [
                serialize_entity_detail(e) for e in app_spec.domain.entities if e.name in entity_set
            ]

        if surface_names:
            surface_set = set(surface_names)
            result["surfaces"] = [
                serialize_surface_detail(s) for s in app_spec.surfaces if s.name in surface_set
            ]

        return json.dumps(result, indent=2)

    # Default: compact summaries
    spec: dict[str, Any] = {
        "project_path": str(project_root),
        "app_name": app_spec.name,
        "entities": [serialize_entity_summary(e) for e in app_spec.domain.entities],
        "surfaces": [serialize_surface_summary(s) for s in app_spec.surfaces],
        "personas": [
            {"id": p.id, "label": p.label, "description": p.description} for p in app_spec.personas
        ],
        "workspaces": [
            {
                "name": w.name,
                "title": w.title,
                "purpose": w.purpose,
                "regions": [r.name for r in w.regions],
            }
            for w in app_spec.workspaces
        ],
        "guidance": (
            "Use dsl(operation='get_spec', entity_names=['EntityName']) "
            "or dsl(operation='get_spec', surface_names=['surface_name']) "
            "for full field and section details."
        ),
    }

    return json.dumps(spec, indent=2)


@wrap_handler_errors
def get_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve stories filtered by status.

    Returns compact summaries by default. When ``story_ids`` is provided,
    returns full content for those specific stories only, keeping context
    usage proportional to what the caller actually needs.
    """

    progress = extract_progress(args)
    status_filter = args.get("status_filter", "all")
    story_ids = args.get("story_ids")

    progress.log_sync("Loading stories from appspec...")
    app_spec = load_project_appspec(project_root)
    stories = list(app_spec.stories)

    # Filter by status
    if status_filter != "all":
        status = StoryStatus(status_filter)
        stories = [s for s in stories if s.status == status]

    if story_ids:
        # Return full content for requested stories only
        id_set = set(story_ids)
        filtered = [s for s in stories if s.story_id in id_set]
        return json.dumps(
            {
                "source": "dsl",
                "filter": status_filter,
                "count": len(filtered),
                "stories": [serialize_story(s) for s in filtered],
            },
            indent=2,
        )

    # Default: return compact summaries
    return json.dumps(
        {
            "source": "dsl",
            "filter": status_filter,
            "count": len(stories),
            "stories": [serialize_story_summary(s) for s in stories],
            "guidance": "Use story(operation='get', story_ids=['ST-001']) to fetch full story details.",
        },
        indent=2,
    )


def _composition_focus_view(
    story_id: str,
    story_by_id: dict[str, Any],
    by_story: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Story-centric composition view: where a story is composed, and whether
    any of those placements is an ``active`` phase (#1559 slice 2)."""
    placements = by_story.get(story_id, [])
    return {
        "exists": story_id in story_by_id,
        "composed_by": placements,
        "active_phases": [p for p in placements if p["phase_kind"] == "active"],
    }


@wrap_handler_errors
def story_composition_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Bidirectional story ⇄ rhythm composition map (#1559 slice 2).

    Reads the scene→story links that rhythms declare (the edge the KG already
    seeds as ``scene_exercises_story`` but that nothing read back). Answers both
    directions in one stateless read:

    - **story → rhythms** ("which phase composes story X, and is it active?") —
      pass ``story_ids`` to focus on specific stories.
    - **rhythm → stories** — the full ``by_story`` index plus the coherence
      signals: stories declared but composed into no journey
      (``stories_uncomposed``) and scenes that cite no story (``scenes_unlinked``).

    Purely a read of the AppSpec (the source of truth for the edge); no KG DB
    population required.
    """
    app_spec = load_project_appspec(project_root)
    story_by_id = {s.story_id: s for s in app_spec.stories}
    focus = set(args.get("story_ids") or [])

    edges: list[dict[str, Any]] = []
    by_story: dict[str, list[dict[str, Any]]] = {}
    scenes_unlinked: list[dict[str, Any]] = []

    for rhythm in app_spec.rhythms:
        for phase in rhythm.phases:
            phase_kind = phase.kind.value if phase.kind else None
            for scene in phase.scenes:
                if not scene.story:
                    scenes_unlinked.append(
                        {"rhythm": rhythm.name, "phase": phase.name, "scene": scene.name}
                    )
                    continue
                story = story_by_id.get(scene.story)
                placement = {
                    "rhythm": rhythm.name,
                    "phase": phase.name,
                    "phase_kind": phase_kind,
                    "scene": scene.name,
                    "surface": scene.surface,
                }
                by_story.setdefault(scene.story, []).append(placement)
                edges.append(
                    {
                        "story_id": scene.story,
                        "story_title": story.title if story else None,
                        "story_status": story.status.value if story else None,
                        "story_exists": story is not None,
                        **placement,
                    }
                )

    composed = set(by_story)
    uncomposed = sorted(sid for sid in story_by_id if sid not in composed)

    if focus:
        stories_view = {
            sid: _composition_focus_view(sid, story_by_id, by_story) for sid in sorted(focus)
        }
        return json.dumps({"story_ids": sorted(focus), "stories": stories_view}, indent=2)

    return json.dumps(
        {
            "edges": edges,
            "by_story": by_story,
            "stories_uncomposed": uncomposed,
            "scenes_unlinked": scenes_unlinked,
            "summary": {
                "total_stories": len(story_by_id),
                "composed": len(composed),
                "uncomposed": len(uncomposed),
                "linked_scenes": len(edges),
                "unlinked_scenes": len(scenes_unlinked),
            },
        },
        indent=2,
    )


@wrap_handler_errors
def wall_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Story Wall — founder-friendly board grouped by implementation status.

    Groups stories into three columns based on process coverage:
      - Working: stories fully covered by implementing processes
      - Needs polish: stories with partial process coverage
      - Not started: stories with no implementing process

    Optionally filtered by persona (actor).
    """

    from .process import stories_coverage_handler

    progress = extract_progress(args)
    actor_filter_str: str | None = args.get("persona")

    progress.log_sync("Loading stories for wall view...")
    app_spec = load_project_appspec(project_root)

    # Get accepted stories (the founder's approved work)
    stories = [s for s in app_spec.stories if s.status == StoryStatus.ACCEPTED]
    if not stories:
        # Fall back to all stories
        stories = list(app_spec.stories)

    progress.log_sync("Calculating coverage data...")
    # Get coverage data
    coverage_raw = stories_coverage_handler(project_root, {"limit": 500})
    coverage_data: dict[str, Any] = json.loads(coverage_raw)
    coverage_map: dict[str, str] = {}
    for item in coverage_data.get("stories", []):
        coverage_map[item.get("story_id", "")] = item.get("status", "uncovered")

    # Filter by persona if requested
    if actor_filter_str:
        stories = [
            s
            for s in stories
            if s.persona.lower() == actor_filter_str.lower()
            or actor_filter_str.lower() in s.persona.lower()
        ]

    # Collect unique personas for filter UI
    personas = sorted({s.persona for s in stories if s.persona})

    # Group by coverage status
    working: list[dict[str, Any]] = []
    needs_polish: list[dict[str, Any]] = []
    not_started: list[dict[str, Any]] = []

    for story in stories:
        summary = serialize_story_summary(story)
        cov_status = coverage_map.get(story.story_id, "uncovered")
        summary["coverage_status"] = cov_status
        if cov_status == "covered":
            working.append(summary)
        elif cov_status == "partial":
            needs_polish.append(summary)
        else:
            not_started.append(summary)

    total = len(stories)

    progress.log_sync("Rendering story wall...")
    # Render wall markdown
    md_lines = ["Story Wall (process coverage)", ""]
    if actor_filter_str:
        md_lines.append(f"Filtered by: {actor_filter_str}")
        md_lines.append("")

    md_lines.append(f"Working ({len(working)})")
    for s in working:
        md_lines.append(f"  [ok] {s['title']}  ({s['persona']})")
    md_lines.append("")
    md_lines.append(f"Needs polish ({len(needs_polish)})")
    for s in needs_polish:
        md_lines.append(f"  [..] {s['title']}  ({s['persona']})")
    md_lines.append("")
    md_lines.append(f"Not started ({len(not_started)})")
    for s in not_started:
        md_lines.append(f"  [  ] {s['title']}  ({s['persona']})")

    # #1605 pilot F: binding / static-prove buckets (agent closed loop).
    # Pure path — no extra MCP dependency on the dual-lock CLI pin.
    binding: dict[str, Any] = {}
    try:
        from dazzle.agent_loop import binding_wall

        binding = binding_wall(project_root, app_spec)
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")
        md_lines.append(binding.get("markdown") or "")
    except Exception as exc:
        binding = {"error": str(exc)[:200]}

    return json.dumps(
        {
            "view": "wall",
            "total": total,
            "working": working,
            "needs_polish": needs_polish,
            "not_started": not_started,
            "personas": personas,
            "filtered_by": actor_filter_str,
            "markdown": "\n".join(md_lines),
            "binding_wall": binding,
        },
        indent=2,
    )
