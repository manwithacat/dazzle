"""
Story scope fidelity analysis — verify that implementing processes
actually exercise all entities declared in a story's scope.

The existing ``story(coverage)`` only checks linkage ("does this story
have a process?"), not whether the process steps reference every entity
in the story's ``scope`` list.

This handler performs the deterministic scope check:
for each story with a scope, verify that every scoped entity appears in
at least one step of the implementing process (via service name, step
name, human_task entity_path, or subprocess name).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..common import extract_progress, wrap_handler_errors
from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ScopeGap:
    """A single missing entity in a story's scope coverage."""

    entity: str
    hint: str  # e.g. "Add a .list or .read step for this entity"


@dataclass
class StoryScopeFidelity:
    """Scope fidelity result for a single story."""

    story_id: str
    title: str
    scope: list[str]
    status: Literal["full", "partial", "no_scope", "no_process"]
    covered_entities: list[str]
    missing_entities: list[str]
    implementing_processes: list[str]
    gaps: list[ScopeGap]


# =============================================================================
# Entity extraction from process steps
# =============================================================================


def _extract_entities_from_step(step: ProcessStepSpec) -> set[str]:
    """Extract entity name references from a single process step.

    Heuristic: entity names appear in service names (e.g. ``Task.create``),
    step names (e.g. ``load_task_context``), human_task entity_path
    (e.g. ``Task``), and subprocess names.
    """
    tokens: set[str] = set()

    # Service name: "Task.create" → "Task"
    if step.service:
        tokens.add(step.service)
        if "." in step.service:
            tokens.add(step.service.split(".")[0])

    # Step name: "load_task_context" → words
    tokens.add(step.name)

    # Human task entity_path: direct entity reference
    if step.human_task:
        if step.human_task.entity_path:
            tokens.add(step.human_task.entity_path)
        if step.human_task.surface:
            tokens.add(step.human_task.surface)

    # Subprocess name
    if step.subprocess:
        tokens.add(step.subprocess)

    # Recurse into parallel steps
    for ps in step.parallel_steps:
        tokens.update(_extract_entities_from_step(ps))

    return tokens


def _collect_process_entity_tokens(proc: ProcessSpec) -> set[str]:
    """Collect all entity-referencing tokens from a process."""
    tokens: set[str] = set()

    for step in proc.steps:
        tokens.update(_extract_entities_from_step(step))

    # Compensation handlers
    for comp in proc.compensations:
        if comp.service:
            tokens.add(comp.service)
            if "." in comp.service:
                tokens.add(comp.service.split(".")[0])
        tokens.add(comp.name)

    # Output fields
    for out in proc.outputs:
        tokens.add(out.name)

    # Process name itself
    tokens.add(proc.name)

    return tokens


def _entity_matches_tokens(entity_name: str, tokens: set[str]) -> bool:
    """Check if an entity name is referenced by any token in the set.

    Matching is case-insensitive and supports:
    - Exact match: "Task" in {"Task"}
    - Service prefix: "Task" in {"Task.create"}
    - Substring in step name: "Task" in {"load_task_context"}
    - Snake_case conversion: "ComplianceDeadline" matches "compliance_deadline"
    """
    entity_lower = entity_name.lower()
    # Convert PascalCase to snake_case for matching
    snake = _pascal_to_snake(entity_name)

    for token in tokens:
        token_lower = token.lower()
        if entity_lower == token_lower:
            return True
        if entity_lower in token_lower:
            return True
        if snake in token_lower:
            return True

    return False


def _pascal_to_snake(name: str) -> str:
    """Convert PascalCase to snake_case for matching."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


# =============================================================================
# Handler
# =============================================================================


@wrap_handler_errors
def scope_fidelity_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze scope fidelity: do implementing processes cover all story scope entities?

    Args (via args dict):
        status_filter: "all" | "full" | "partial" | "gaps_only" (default: "all")
            "gaps_only" shows stories with partial or no_process status only
        limit: Max stories to return (default: 50)
        offset: Pagination offset (default: 0)
    """
    progress = extract_progress(args)
    progress.log_sync("Loading app spec for scope fidelity analysis...")
    app_spec = _helpers.load_app_spec(project_root)

    # Load stories
    stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
    if not stories:
        from dazzle.core.stories_persistence import load_story_index

        story_index = load_story_index(project_root)
        if not story_index:
            return json.dumps(
                {
                    "error": "No stories found in project",
                    "hint": "Use story(operation='propose') to generate stories first.",
                }
            )
        # Convert index dicts to lightweight objects for uniform handling
        return _analyze_from_index(story_index, app_spec, project_root, args, progress)

    # Load processes (DSL + persisted)
    processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []
    from dazzle.core.process_persistence import load_processes as load_persisted_processes

    persisted = load_persisted_processes(project_root)
    dsl_names = {p.name for p in processes}
    for p in persisted:
        if p.name not in dsl_names:
            processes.append(p)

    # Build implements mapping: story_id -> [process_names]
    implements_map: dict[str, list[str]] = {}
    for proc in processes:
        for story_id in proc.implements:
            implements_map.setdefault(story_id, []).append(proc.name)

    # Analyze each story
    results: list[StoryScopeFidelity] = []
    full_count = 0
    partial_count = 0
    no_scope_count = 0
    no_process_count = 0
    total_scope_entities = 0
    total_covered_entities = 0

    # Exclude rejected stories
    rejected_count = 0
    active_stories = []
    for s in stories:
        if getattr(s, "status", "draft") == "rejected":
            rejected_count += 1
        else:
            active_stories.append(s)

    progress.log_sync(
        f"Analyzing scope fidelity for {len(active_stories)} stories "
        f"against {len(processes)} processes..."
    )

    for story in active_stories:
        scope = story.scope
        implementing = implements_map.get(story.story_id, [])

        if not scope:
            no_scope_count += 1
            results.append(
                StoryScopeFidelity(
                    story_id=story.story_id,
                    title=story.title,
                    scope=[],
                    status="no_scope",
                    covered_entities=[],
                    missing_entities=[],
                    implementing_processes=implementing,
                    gaps=[],
                )
            )
            continue

        total_scope_entities += len(scope)

        if not implementing:
            no_process_count += 1
            results.append(
                StoryScopeFidelity(
                    story_id=story.story_id,
                    title=story.title,
                    scope=scope,
                    status="no_process",
                    covered_entities=[],
                    missing_entities=list(scope),
                    implementing_processes=[],
                    gaps=[ScopeGap(entity=e, hint="No implementing process found") for e in scope],
                )
            )
            continue

        # Collect all tokens from implementing processes
        all_tokens: set[str] = set()
        for proc_name in implementing:
            matched_proc = next((p for p in processes if p.name == proc_name), None)
            if matched_proc:
                all_tokens.update(_collect_process_entity_tokens(matched_proc))

        covered = [e for e in scope if _entity_matches_tokens(e, all_tokens)]
        missing = [e for e in scope if not _entity_matches_tokens(e, all_tokens)]
        total_covered_entities += len(covered)

        gaps = [
            ScopeGap(
                entity=e,
                hint=f"Add a .list, .read, or context-loading step for {e}",
            )
            for e in missing
        ]

        if missing:
            partial_count += 1
            status: Literal["full", "partial", "no_scope", "no_process"] = "partial"
        else:
            full_count += 1
            status = "full"

        results.append(
            StoryScopeFidelity(
                story_id=story.story_id,
                title=story.title,
                scope=scope,
                status=status,
                covered_entities=covered,
                missing_entities=missing,
                implementing_processes=implementing,
                gaps=gaps,
            )
        )

    # Compute overall metrics
    scope_coverage_percent = (
        round(total_covered_entities / total_scope_entities * 100, 1)
        if total_scope_entities > 0
        else 100.0
    )
    stories_with_scope = full_count + partial_count + no_process_count
    stories_fully_covered_percent = (
        round(full_count / stories_with_scope * 100, 1) if stories_with_scope > 0 else 100.0
    )

    return _build_response(
        results=results,
        full_count=full_count,
        partial_count=partial_count,
        no_scope_count=no_scope_count,
        no_process_count=no_process_count,
        rejected_count=rejected_count,
        total_scope_entities=total_scope_entities,
        total_covered_entities=total_covered_entities,
        scope_coverage_percent=scope_coverage_percent,
        stories_fully_covered_percent=stories_fully_covered_percent,
        args=args,
    )


def _analyze_from_index(
    story_index: list[dict[str, Any]],
    app_spec: Any,
    project_root: Path,
    args: dict[str, Any],
    progress: Any,
) -> str:
    """Scope fidelity analysis from lightweight story index dicts."""

    processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []
    from dazzle.core.process_persistence import load_processes as load_persisted_processes

    persisted = load_persisted_processes(project_root)
    dsl_names = {p.name for p in processes}
    for p in persisted:
        if p.name not in dsl_names:
            processes.append(p)

    implements_map: dict[str, list[str]] = {}
    for proc in processes:
        for story_id in proc.implements:
            implements_map.setdefault(story_id, []).append(proc.name)

    results: list[StoryScopeFidelity] = []
    full_count = 0
    partial_count = 0
    no_scope_count = 0
    no_process_count = 0
    total_scope_entities = 0
    total_covered_entities = 0
    rejected_count = 0

    active_stories = []
    for item in story_index:
        if item.get("status") == "rejected":
            rejected_count += 1
        else:
            active_stories.append(item)

    progress.log_sync(f"Analyzing scope fidelity for {len(active_stories)} stories (from index)...")

    for item in active_stories:
        sid = item["story_id"]
        title = item["title"]
        scope = item.get("scope", [])
        implementing = implements_map.get(sid, [])

        if not scope:
            no_scope_count += 1
            results.append(
                StoryScopeFidelity(
                    story_id=sid,
                    title=title,
                    scope=[],
                    status="no_scope",
                    covered_entities=[],
                    missing_entities=[],
                    implementing_processes=implementing,
                    gaps=[],
                )
            )
            continue

        total_scope_entities += len(scope)

        if not implementing:
            no_process_count += 1
            results.append(
                StoryScopeFidelity(
                    story_id=sid,
                    title=title,
                    scope=scope,
                    status="no_process",
                    covered_entities=[],
                    missing_entities=list(scope),
                    implementing_processes=[],
                    gaps=[ScopeGap(entity=e, hint="No implementing process found") for e in scope],
                )
            )
            continue

        all_tokens: set[str] = set()
        for proc_name in implementing:
            matched_proc = next((p for p in processes if p.name == proc_name), None)
            if matched_proc:
                all_tokens.update(_collect_process_entity_tokens(matched_proc))

        covered = [e for e in scope if _entity_matches_tokens(e, all_tokens)]
        missing = [e for e in scope if not _entity_matches_tokens(e, all_tokens)]
        total_covered_entities += len(covered)

        gaps = [
            ScopeGap(
                entity=e,
                hint=f"Add a .list, .read, or context-loading step for {e}",
            )
            for e in missing
        ]

        if missing:
            partial_count += 1
            fidelity_status: Literal["full", "partial", "no_scope", "no_process"] = "partial"
        else:
            full_count += 1
            fidelity_status = "full"

        results.append(
            StoryScopeFidelity(
                story_id=sid,
                title=title,
                scope=scope,
                status=fidelity_status,
                covered_entities=covered,
                missing_entities=missing,
                implementing_processes=implementing,
                gaps=gaps,
            )
        )

    scope_coverage_percent = (
        round(total_covered_entities / total_scope_entities * 100, 1)
        if total_scope_entities > 0
        else 100.0
    )
    stories_with_scope = full_count + partial_count + no_process_count
    stories_fully_covered_percent = (
        round(full_count / stories_with_scope * 100, 1) if stories_with_scope > 0 else 100.0
    )

    return _build_response(
        results=results,
        full_count=full_count,
        partial_count=partial_count,
        no_scope_count=no_scope_count,
        no_process_count=no_process_count,
        rejected_count=rejected_count,
        total_scope_entities=total_scope_entities,
        total_covered_entities=total_covered_entities,
        scope_coverage_percent=scope_coverage_percent,
        stories_fully_covered_percent=stories_fully_covered_percent,
        args=args,
    )


# =============================================================================
# Response builder
# =============================================================================


def _build_response(
    *,
    results: list[StoryScopeFidelity],
    full_count: int,
    partial_count: int,
    no_scope_count: int,
    no_process_count: int,
    rejected_count: int,
    total_scope_entities: int,
    total_covered_entities: int,
    scope_coverage_percent: float,
    stories_fully_covered_percent: float,
    args: dict[str, Any],
) -> str:
    """Build the JSON response with filtering and pagination."""
    # Apply status filter
    status_filter = args.get("status_filter", "all")
    if status_filter == "gaps_only":
        results = [r for r in results if r.status in ("partial", "no_process")]
    elif status_filter != "all":
        results = [r for r in results if r.status == status_filter]

    # Sort: actionable items first
    _priority = {"no_process": 0, "partial": 1, "no_scope": 2, "full": 3}
    results.sort(key=lambda r: _priority.get(r.status, 9))

    # Pagination
    limit = args.get("limit", 50)
    offset = args.get("offset", 0)
    page = results[offset : offset + limit]
    has_more = (offset + limit) < len(results)

    total_stories = full_count + partial_count + no_scope_count + no_process_count
    total_scope_gaps = sum(len(r.gaps) for r in results)

    response: dict[str, Any] = {
        "total_stories": total_stories,
        "stories_with_scope": full_count + partial_count + no_process_count,
        "full": full_count,
        "partial": partial_count,
        "no_scope": no_scope_count,
        "no_process": no_process_count,
        "rejected_excluded": rejected_count,
        "total_scope_entities": total_scope_entities,
        "total_covered_entities": total_covered_entities,
        "total_scope_gaps": total_scope_gaps,
        "scope_coverage_percent": scope_coverage_percent,
        "stories_fully_covered_percent": stories_fully_covered_percent,
        "showing": len(page),
        "offset": offset,
        "has_more": has_more,
        "stories": [asdict(s) for s in page],
    }

    if has_more:
        next_offset = offset + limit
        response["guidance"] = (
            f"Showing {len(page)} of {len(results)} stories. "
            f"Use story(operation='scope_fidelity', offset={next_offset}) "
            f"for the next page."
        )

    if total_scope_gaps > 0:
        response["recommendation"] = (
            f"{total_scope_gaps} scope gaps across {partial_count + no_process_count} stories. "
            "Add .list, .read, or context-loading steps to implementing processes "
            "to close these gaps."
        )

    return json.dumps(response, indent=2)
