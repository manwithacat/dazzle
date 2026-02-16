"""
Story coverage analysis — how well processes cover user stories.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ..common import extract_progress, wrap_handler_errors
from . import _helpers

if TYPE_CHECKING:
    from dazzle.core.ir.process import ProcessSpec
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Constants
# =============================================================================

# Minimum word length for meaningful coverage matching
MIN_MEANINGFUL_WORD_LENGTH = 3

# Simple CRUD outcome patterns — stories matching these don't need a process
CRUD_OUTCOME_PATTERNS = {
    "saved",
    "created",
    "updated",
    "deleted",
    "displayed",
    "listed",
}

# UI feedback patterns — these don't indicate non-trivial behavior
UI_FEEDBACK_PATTERNS = {
    "confirmation",
    "message",
    "success",
    "toast",
    "notification",
    "sees",
    "shown",
    "redirected",
    "navigated",
    "refreshed",
}

# Patterns that can be inferred from CRUD service bindings
_CRUD_SATISFACTION_PATTERNS: dict[str, list[str]] = {
    "create": ["created", "saved", "stored", "persisted", "added", "recorded"],
    "update": ["updated", "modified", "changed", "saved", "stored"],
    "delete": ["deleted", "removed", "archived"],
}

# Patterns for status transition inference
_STATUS_TRANSITION_PATTERNS = [
    "status",
    "transition",
    "changed",
    "moved",
    "set to",
    "becomes",
    "timestamp",
    "recorded",
    "logged",
    "tracked",
]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class StoryCoverage:
    """Coverage status for a single story."""

    story_id: str
    title: str
    status: Literal["covered", "partial", "uncovered"]
    implementing_processes: list[str]
    missing_aspects: list[str]


@dataclass
class CoverageReport:
    """Full coverage analysis."""

    total_stories: int
    covered: int
    partial: int
    uncovered: int
    coverage_percent: float
    stories: list[StoryCoverage]


# =============================================================================
# Coverage Handler
# =============================================================================


@wrap_handler_errors
def stories_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze story coverage by processes.

    Supports pagination to keep context usage manageable for large projects.

    Args (via args dict):
        status_filter: "all" | "covered" | "partial" | "uncovered" (default: "all")
        limit: Max stories to return (default: 50)
        offset: Number of stories to skip (default: 0)
    """
    progress = extract_progress(args)
    try:
        progress.log_sync("Loading app spec for coverage analysis...")
        app_spec = _helpers.load_app_spec(project_root)

        # Use lightweight index when stories aren't in the AppSpec
        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
        used_index = False

        if not stories:
            from dazzle.core.stories_persistence import load_story_index

            story_index = load_story_index(project_root)
            used_index = bool(story_index)

            if not used_index:
                return json.dumps(
                    {
                        "error": "No stories found in project",
                        "hint": (
                            "Use propose_stories_from_dsl to generate "
                            "stories, or define them in DSL."
                        ),
                    }
                )

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
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

        coverage_results: list[StoryCoverage] = []
        covered_count = 0
        partial_count = 0
        uncovered_count = 0

        # Iterate using lightweight index or full stories
        story_index_list: list[dict[str, Any]] = (
            story_index if used_index else []  # noqa: F821
        )
        items: list[Any] = stories if stories else story_index_list

        # Exclude rejected stories from coverage calculations
        rejected_count = 0
        filtered_items: list[Any] = []
        for item in items:
            item_status = item["status"] if used_index else getattr(item, "status", "draft")
            if item_status == "rejected":
                rejected_count += 1
            else:
                filtered_items.append(item)
        items = filtered_items

        progress.log_sync(
            f"Analyzing coverage for {len(items)} stories against {len(processes)} processes..."
        )
        for item in items:
            if used_index:
                sid = item["story_id"]
                title = item["title"]
            else:
                sid = item.story_id
                title = item.title

            implementing = implements_map.get(sid, [])

            if not implementing:
                status: Literal["covered", "partial", "uncovered"] = "uncovered"
                uncovered_count += 1
                missing = ["No implementing process"]
            else:
                if used_index:
                    missing = _find_missing_aspects_from_index(item, processes, implementing)
                else:
                    missing = _find_missing_aspects(item, processes, implementing)
                if missing:
                    status = "partial"
                    partial_count += 1
                else:
                    status = "covered"
                    covered_count += 1

            coverage_results.append(
                StoryCoverage(
                    story_id=sid,
                    title=title,
                    status=status,
                    implementing_processes=implementing,
                    missing_aspects=missing,
                )
            )

        total = len(items)
        coverage_percent = (covered_count / total * 100) if total > 0 else 0.0
        progress.log_sync(
            f"Coverage: {covered_count} covered, {partial_count} partial, {uncovered_count} uncovered"
        )

        # Apply status filter
        status_filter = args.get("status_filter", "all")
        if status_filter != "all":
            coverage_results = [r for r in coverage_results if r.status == status_filter]

        # Sort so actionable items (uncovered, partial) appear first
        _status_priority = {"uncovered": 0, "partial": 1, "covered": 2}
        coverage_results.sort(key=lambda r: _status_priority.get(r.status, 9))

        # Apply pagination
        limit = args.get("limit", 50)
        offset = args.get("offset", 0)
        page = coverage_results[offset : offset + limit]
        has_more = (offset + limit) < len(coverage_results)

        has_process = covered_count + partial_count
        has_process_percent = round(has_process / total * 100, 1) if total > 0 else 0.0
        effective_coverage_percent = (
            round((covered_count + partial_count * 0.5) / total * 100, 1) if total > 0 else 0.0
        )

        result: dict[str, Any] = {
            "total_stories": total,
            "covered": covered_count,
            "partial": partial_count,
            "uncovered": uncovered_count,
            "rejected_excluded": rejected_count,
            "coverage_percent": round(coverage_percent, 1),
            "effective_coverage_percent": effective_coverage_percent,
            "has_process": has_process,
            "has_process_percent": has_process_percent,
            "showing": len(page),
            "offset": offset,
            "has_more": has_more,
            "stories": [asdict(s) for s in page],
        }

        if has_more:
            next_offset = offset + limit
            result["guidance"] = (
                f"Showing {len(page)} of {len(coverage_results)} stories "
                f"(filter: {status_filter}). "
                f"Use process(operation='coverage', offset={next_offset}) "
                f"for the next page."
            )

        if uncovered_count > 0:
            result["discovery_hint"] = (
                f"{uncovered_count} stories have no implementing process. "
                "Use discovery(operation='run', mode='workflow_coherence') "
                "to analyze process/story integrity and find workflow gaps."
            )

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Coverage Analysis Helpers
# =============================================================================


def _collect_process_match_pool(
    processes: list[ProcessSpec],
    implementing: list[str],
) -> tuple[list[str], set[str], list[ProcessSpec]]:
    """Collect the full text pool and explicit satisfies refs from implementing processes.

    Returns:
        match_pool: lowered text fragments to match against
        satisfies_outcomes: set of outcome texts explicitly declared as satisfied
        impl_procs: the resolved ProcessSpec objects
    """
    match_pool: list[str] = []
    satisfies_outcomes: set[str] = set()
    impl_procs: list[ProcessSpec] = []

    for proc_name in implementing:
        proc = next((p for p in processes if p.name == proc_name), None)
        if not proc:
            continue
        impl_procs.append(proc)

        for step in proc.steps:
            match_pool.append(step.name.lower())
            if step.service:
                match_pool.append(step.service.lower())
            for ps in step.parallel_steps:
                match_pool.append(ps.name.lower())
                if ps.service:
                    match_pool.append(ps.service.lower())
            for ref in step.satisfies:
                satisfies_outcomes.add(ref.outcome.lower())
            for ps in step.parallel_steps:
                for ref in ps.satisfies:
                    satisfies_outcomes.add(ref.outcome.lower())

        for comp in proc.compensations:
            match_pool.append(comp.name.lower())

        for out in proc.outputs:
            match_pool.append(out.name.lower())
            if out.description:
                match_pool.append(out.description.lower())
            for ref in out.satisfies:
                satisfies_outcomes.add(ref.outcome.lower())

    return match_pool, satisfies_outcomes, impl_procs


def _infer_structural_satisfaction(
    outcome_lower: str,
    impl_procs: list[ProcessSpec],
) -> bool:
    """Check if outcome is structurally satisfied by CRUD bindings or triggers."""
    from dazzle.core.ir.process import ProcessTriggerKind, StepKind

    for proc in impl_procs:
        # CRUD service binding inference (check both service and step name)
        for step in proc.steps:
            sources: list[str] = []
            if step.kind == StepKind.SERVICE and step.service:
                sources.append(step.service.lower())
            sources.append(step.name.lower())
            for source in sources:
                for crud_op, patterns in _CRUD_SATISFACTION_PATTERNS.items():
                    if crud_op in source:
                        if any(pat in outcome_lower for pat in patterns):
                            return True
                # Also treat "save" in step name as create alias
                if "save" in source:
                    if any(pat in outcome_lower for pat in _CRUD_SATISFACTION_PATTERNS["create"]):
                        return True

        # Status transition trigger inference
        if proc.trigger and proc.trigger.kind == ProcessTriggerKind.ENTITY_STATUS_TRANSITION:
            if any(pat in outcome_lower for pat in _STATUS_TRANSITION_PATTERNS):
                return True

    return False


def _outcome_matches_pool(
    outcome: str,
    match_pool: list[str],
    satisfies_outcomes: set[str],
    impl_procs: list[ProcessSpec],
) -> bool:
    """Check if an outcome is matched by the pool, satisfies refs, or structural inference."""
    outcome_lower = outcome.lower()

    # 1. Explicit satisfies declaration
    if outcome_lower in satisfies_outcomes:
        return True

    # 2. Word overlap with match pool
    outcome_words = set(outcome_lower.split())
    meaningful_words = {w for w in outcome_words if len(w) > MIN_MEANINGFUL_WORD_LENGTH}
    if meaningful_words and any(
        any(word in item for word in meaningful_words) for item in match_pool
    ):
        return True

    # 3. UI-concern outcomes auto-satisfied when a process exists
    if impl_procs:
        outcome_words = outcome_words or set(outcome_lower.split())
        if outcome_words & UI_FEEDBACK_PATTERNS:
            return True

    # 4. Structural inference (CRUD / status transitions)
    if _infer_structural_satisfaction(outcome_lower, impl_procs):
        return True

    return False


def _find_missing_aspects(
    story: StorySpec,
    processes: list[ProcessSpec],
    implementing: list[str],
) -> list[str]:
    """Identify story aspects not covered by implementing processes."""
    missing: list[str] = []
    match_pool, satisfies_outcomes, impl_procs = _collect_process_match_pool(
        processes, implementing
    )

    # Get 'then' outcomes from story (both legacy and Gherkin-style)
    then_outcomes: list[str] = []
    if story.then:
        then_outcomes = [c.expression for c in story.then]
    elif story.happy_path_outcome:
        then_outcomes = story.happy_path_outcome

    for outcome in then_outcomes:
        if not _outcome_matches_pool(outcome, match_pool, satisfies_outcomes, impl_procs):
            missing.append(outcome)

    # Check 'unless' exceptions
    for exception in story.unless:
        if not _outcome_matches_pool(
            exception.condition, match_pool, satisfies_outcomes, impl_procs
        ):
            missing.append(f"Exception: {exception.condition}")

    return missing


def _find_missing_aspects_from_index(
    story_dict: dict[str, Any],
    processes: list[ProcessSpec],
    implementing: list[str],
) -> list[str]:
    """Like _find_missing_aspects but works with lightweight story dicts."""
    missing: list[str] = []
    match_pool, satisfies_outcomes, impl_procs = _collect_process_match_pool(
        processes, implementing
    )

    # Extract then outcomes from raw dict
    then_outcomes: list[str] = []
    raw_then = story_dict.get("then", [])
    if raw_then:
        then_outcomes = [c["expression"] if isinstance(c, dict) else str(c) for c in raw_then]
    elif story_dict.get("happy_path_outcome"):
        then_outcomes = story_dict["happy_path_outcome"]

    for outcome in then_outcomes:
        if not _outcome_matches_pool(outcome, match_pool, satisfies_outcomes, impl_procs):
            missing.append(outcome)

    # Check unless exceptions from raw dict
    for exception in story_dict.get("unless", []):
        condition = exception["condition"] if isinstance(exception, dict) else str(exception)
        if not _outcome_matches_pool(condition, match_pool, satisfies_outcomes, impl_procs):
            missing.append(f"Exception: {condition}")

    return missing
