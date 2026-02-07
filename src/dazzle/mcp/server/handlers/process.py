"""
Process and coverage tool handlers for MCP server.

Handles process inspection, story coverage analysis, process proposal generation,
and process run monitoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.process import ProcessSpec, ProcessStepSpec
    from dazzle.core.ir.stories import StorySpec
    from dazzle.core.process.adapter import ProcessAdapter


# =============================================================================
# Constants
# =============================================================================

# Flow control keywords used in step transitions
FLOW_COMPLETE_KEYWORDS = ("complete", "end")
FLOW_FAILURE_KEYWORDS = ("fail", "error")

# Minimum word length for meaningful coverage matching
MIN_MEANINGFUL_WORD_LENGTH = 3


# =============================================================================
# Data Classes for Coverage Results
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


@dataclass
class WorkflowProposal:
    """A workflow-oriented design brief generated from clustered stories."""

    name: str
    title: str
    implements: list[str]
    story_summaries: list[dict[str, Any]]
    entity: str | None  # Entity name — full context in top-level entities dict
    design_questions: list[str]
    recommendation: str  # "compose_process" | "process_not_recommended"
    reason: str


def save_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save composed processes to .dazzle/processes/processes.json.

    Accepts a list of process definitions and persists them. Validates
    that referenced story IDs exist and entity references are valid.

    Args (via args dict):
        processes: List of process dicts (ProcessSpec-compatible)
        overwrite: If True, replace processes with matching names (default: False)
    """
    try:
        from dazzle.core.ir.process import ProcessSpec
        from dazzle.core.process_persistence import add_processes

        raw_processes = args.get("processes")
        if not raw_processes or not isinstance(raw_processes, list):
            return json.dumps({"error": "processes list is required"})

        overwrite = args.get("overwrite", False)

        # Validate and parse processes
        parsed: list[ProcessSpec] = []
        errors: list[str] = []

        for i, raw in enumerate(raw_processes):
            try:
                proc = ProcessSpec.model_validate(raw)
                parsed.append(proc)
            except Exception as e:
                errors.append(f"Process {i}: {e}")

        if errors:
            return json.dumps({"error": "Validation failed", "details": errors})

        # Validate story references exist
        app_spec = _load_app_spec(project_root)
        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []
        if not stories:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)

        story_ids = {s.story_id for s in stories}
        warnings: list[str] = []
        for proc in parsed:
            for sid in proc.implements:
                if sid not in story_ids:
                    warnings.append(f"Process '{proc.name}' references unknown story '{sid}'")

        # Validate entity references
        entity_names = {e.name for e in app_spec.domain.entities}
        for proc in parsed:
            if proc.trigger and proc.trigger.entity_name:
                if proc.trigger.entity_name not in entity_names:
                    warnings.append(
                        f"Process '{proc.name}' trigger references "
                        f"unknown entity '{proc.trigger.entity_name}'"
                    )

        # Save
        all_processes = add_processes(project_root, parsed, overwrite=overwrite)

        result: dict[str, Any] = {
            "saved": len(parsed),
            "total": len(all_processes),
            "process_names": [p.name for p in parsed],
        }
        if warnings:
            result["warnings"] = warnings

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@dataclass
class ProcessRunSummary:
    """Summary of a process run."""

    run_id: str
    process_name: str
    status: str
    current_step: str | None
    started_at: str
    duration_seconds: float | None
    error: str | None


# =============================================================================
# Helper Functions
# =============================================================================


def _load_app_spec(project_root: Path) -> AppSpec:
    """Load and build AppSpec from project."""
    manifest = load_manifest(project_root / "dazzle.toml")
    dsl_files = discover_dsl_files(project_root, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def _get_process_adapter(project_root: Path) -> ProcessAdapter:
    """Get process adapter for project."""
    from dazzle.core.process import LiteProcessAdapter

    db_path = project_root / ".dazzle" / "processes.db"
    return LiteProcessAdapter(db_path=db_path)


def _slugify(text: str) -> str:
    """Convert text to snake_case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:30]


# =============================================================================
# Story Coverage Handler
# =============================================================================


def stories_coverage_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze story coverage by processes.

    Supports pagination to keep context usage manageable for large projects.

    Args (via args dict):
        status_filter: "all" | "covered" | "partial" | "uncovered" (default: "all")
        limit: Max stories to return (default: 50)
        offset: Number of stories to skip (default: 0)
    """
    try:
        app_spec = _load_app_spec(project_root)

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

        # Apply status filter
        status_filter = args.get("status_filter", "all")
        if status_filter != "all":
            coverage_results = [r for r in coverage_results if r.status == status_filter]

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
        if outcome_words & _UI_FEEDBACK_PATTERNS:
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


# =============================================================================
# Process Proposal Handler
# =============================================================================


def propose_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate workflow design briefs from uncovered stories.

    Clusters stories into workflow-oriented groups and returns design briefs
    that guide the agent in composing processes, rather than generating
    ready-made DSL stubs.
    """
    try:
        app_spec = _load_app_spec(project_root)
        story_ids = args.get("story_ids")

        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []

        # Fall back to persisted stories from .dazzle/stories/stories.json
        if not stories:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        if not stories:
            return json.dumps(
                {
                    "error": "No stories found",
                    "hint": "Use propose_stories_from_dsl first.",
                }
            )

        # Build implements mapping
        implements_map: dict[str, list[str]] = {}
        for proc in processes:
            for sid in proc.implements:
                implements_map.setdefault(sid, []).append(proc.name)

        # Find target stories
        if story_ids:
            target_stories = [s for s in stories if s.story_id in story_ids]
        else:
            # Find uncovered or partial stories
            target_stories = [
                s
                for s in stories
                if s.story_id not in implements_map
                or _find_missing_aspects(s, processes, implements_map.get(s.story_id, []))
            ]

        if not target_stories:
            return json.dumps(
                {
                    "status": "all_covered",
                    "message": "All stories are fully covered by processes.",
                }
            )

        # Cluster stories into workflows and build design briefs
        proposals = _cluster_stories_into_workflows(target_stories, app_spec)

        # Build deduplicated output: entity contexts emitted once,
        # process_not_recommended collapsed to a summary list
        entities: dict[str, dict[str, Any]] = {}
        workflows: list[dict[str, Any]] = []
        skipped_crud: list[str] = []

        include_crud = args.get("include_crud", False)

        for proposal in proposals:
            if proposal.entity and proposal.entity not in entities:
                entities[proposal.entity] = _build_entity_context(proposal.entity, app_spec)

            if proposal.recommendation == "process_not_recommended" and not include_crud:
                # Collapse to just the entity name — agent doesn't need details
                if proposal.entity and proposal.entity not in skipped_crud:
                    skipped_crud.append(proposal.entity)
                continue

            # When include_crud is True, upgrade CRUD proposals
            rec = proposal.recommendation
            if include_crud and rec == "process_not_recommended":
                rec = "compose_process"

            workflow_dict: dict[str, Any] = {
                "name": proposal.name,
                "title": proposal.title,
                "implements": proposal.implements,
                "story_summaries": proposal.story_summaries,
                "entity": proposal.entity,
                "design_questions": proposal.design_questions,
                "recommendation": rec,
                "reason": proposal.reason,
            }

            # Build review checklist from story contracts
            proposal_stories = [s for s in target_stories if s.story_id in proposal.implements]
            checklist = _build_review_checklist(proposal_stories)
            if checklist:
                workflow_dict["review_checklist"] = checklist

            workflows.append(workflow_dict)

        result: dict[str, Any] = {
            "workflow_count": len(workflows),
            "workflows": workflows,
        }

        # Only include entities referenced by compose_process workflows
        workflow_entities = {w["entity"] for w in workflows if w["entity"]}
        if workflow_entities:
            result["entities"] = {
                name: ctx for name, ctx in entities.items() if name in workflow_entities
            }

        if skipped_crud:
            result["skipped_crud"] = skipped_crud
            result["skipped_crud_count"] = len(skipped_crud)

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Workflow Clustering & Design Brief Generation
# =============================================================================

# Simple CRUD outcome patterns — stories matching these don't need a process
_CRUD_OUTCOME_PATTERNS = {
    "saved",
    "created",
    "updated",
    "deleted",
    "displayed",
    "listed",
}

# UI feedback patterns — these don't indicate non-trivial behavior
_UI_FEEDBACK_PATTERNS = {
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


def _is_crud_story(story: StorySpec) -> bool:
    """Detect if a story is simple CRUD handled by surface handlers."""
    from dazzle.core.ir.stories import StoryTrigger

    # Must be user-initiated
    if story.trigger not in (StoryTrigger.FORM_SUBMITTED, StoryTrigger.USER_CLICK):
        return False

    # Must not have exception branches
    if story.unless:
        return False

    # Must have single entity in scope
    if len(story.scope) != 1:
        return False

    # At least one outcome must be a CRUD action, and the rest must be
    # either CRUD actions or simple UI feedback (confirmation messages etc.)
    outcomes = story.effective_then
    if not outcomes:
        return False

    has_crud_outcome = False
    for outcome in outcomes:
        words = set(outcome.lower().split())
        if words & _CRUD_OUTCOME_PATTERNS:
            has_crud_outcome = True
        elif not (words & _UI_FEEDBACK_PATTERNS):
            # Outcome is neither CRUD nor UI feedback — not simple CRUD
            return False

    return has_crud_outcome


def _cluster_stories_into_workflows(
    stories: list[StorySpec], app_spec: AppSpec
) -> list[WorkflowProposal]:
    """Cluster stories into workflow-oriented design briefs.

    Algorithm:
    1. Group by shared primary entity (scope[0])
    2. Within each group, detect lifecycle chains (STATUS_CHANGED triggers)
    3. Flag CRUD stories as process_not_recommended
    4. Group remaining by trigger affinity (CRON, EXTERNAL_EVENT)
    """
    from dazzle.core.ir.stories import StoryTrigger

    proposals: list[WorkflowProposal] = []

    # Step 1: Group by primary entity
    entity_groups: dict[str, list[StorySpec]] = {}
    ungrouped: list[StorySpec] = []

    for story in stories:
        if story.scope:
            key = story.scope[0]
            entity_groups.setdefault(key, []).append(story)
        else:
            ungrouped.append(story)

    for entity_name, group in entity_groups.items():
        # Step 2: Separate CRUD vs lifecycle vs other
        crud_stories: list[StorySpec] = []
        lifecycle_stories: list[StorySpec] = []
        cron_stories: list[StorySpec] = []
        event_stories: list[StorySpec] = []
        other_stories: list[StorySpec] = []

        for story in group:
            if _is_crud_story(story):
                crud_stories.append(story)
            elif story.trigger == StoryTrigger.STATUS_CHANGED:
                lifecycle_stories.append(story)
            elif story.trigger in (StoryTrigger.CRON_DAILY, StoryTrigger.CRON_HOURLY):
                cron_stories.append(story)
            elif story.trigger in (StoryTrigger.EXTERNAL_EVENT, StoryTrigger.TIMER_ELAPSED):
                event_stories.append(story)
            else:
                other_stories.append(story)

        # Step 3: CRUD stories → process_not_recommended
        if crud_stories:
            proposals.append(
                _build_proposal(
                    workflow_name=f"{_slugify(entity_name)}_crud",
                    title=f"{entity_name} CRUD Operations",
                    stories=crud_stories,
                    entity_name=entity_name,
                    app_spec=app_spec,
                    recommendation="process_not_recommended",
                    reason=(
                        "These stories describe standard create/read/update/delete operations "
                        "that are handled by surface CRUD handlers. No process needed."
                    ),
                )
            )

        # Step 4: Lifecycle stories → compose_process
        if lifecycle_stories:
            proposals.append(
                _build_proposal(
                    workflow_name=f"{_slugify(entity_name)}_lifecycle",
                    title=f"{entity_name} Lifecycle",
                    stories=lifecycle_stories,
                    entity_name=entity_name,
                    app_spec=app_spec,
                    recommendation="compose_process",
                    reason=(
                        f"Stories drive status transitions on {entity_name}. "
                        "Compose a process that orchestrates this lifecycle."
                    ),
                )
            )

        # Cron stories → compose_process
        if cron_stories:
            proposals.append(
                _build_proposal(
                    workflow_name=f"{_slugify(entity_name)}_scheduled",
                    title=f"{entity_name} Scheduled Tasks",
                    stories=cron_stories,
                    entity_name=entity_name,
                    app_spec=app_spec,
                    recommendation="compose_process",
                    reason=f"Scheduled operations on {entity_name}.",
                )
            )

        # External event stories → compose_process
        if event_stories:
            proposals.append(
                _build_proposal(
                    workflow_name=f"{_slugify(entity_name)}_events",
                    title=f"{entity_name} Event Handling",
                    stories=event_stories,
                    entity_name=entity_name,
                    app_spec=app_spec,
                    recommendation="compose_process",
                    reason=f"External event-driven operations on {entity_name}.",
                )
            )

        # Other stories that aren't CRUD but aren't lifecycle/cron/event
        if other_stories:
            proposals.append(
                _build_proposal(
                    workflow_name=f"{_slugify(entity_name)}_workflow",
                    title=f"{entity_name} Workflow",
                    stories=other_stories,
                    entity_name=entity_name,
                    app_spec=app_spec,
                    recommendation="compose_process",
                    reason=f"Non-CRUD operations on {entity_name} that need orchestration.",
                )
            )

    # Ungrouped stories (no scope entity)
    if ungrouped:
        proposals.append(
            _build_proposal(
                workflow_name="unscoped_workflow",
                title="Unscoped Workflow",
                stories=ungrouped,
                entity_name=None,
                app_spec=app_spec,
                recommendation="compose_process",
                reason="Stories without a primary entity scope.",
            )
        )

    return proposals


def _build_proposal(
    *,
    workflow_name: str,
    title: str,
    stories: list[StorySpec],
    entity_name: str | None,
    app_spec: AppSpec,
    recommendation: str,
    reason: str,
) -> WorkflowProposal:
    """Build a WorkflowProposal with entity context and design questions."""
    story_summaries = [
        {
            "story_id": s.story_id,
            "title": s.title,
            "trigger": s.trigger.value,
            "actor": s.actor,
        }
        for s in stories
    ]

    design_questions = (
        _generate_design_questions(stories, entity_name, app_spec)
        if recommendation == "compose_process"
        else []
    )

    return WorkflowProposal(
        name=workflow_name,
        title=title,
        implements=[s.story_id for s in stories],
        story_summaries=story_summaries,
        entity=entity_name,
        design_questions=design_questions,
        recommendation=recommendation,
        reason=reason,
    )


def _build_entity_context(entity_name: str, app_spec: AppSpec) -> dict[str, Any]:
    """Build inline entity context for a design brief."""
    from dazzle.core.ir.fields import FieldTypeKind

    entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
    if not entity:
        return {"entity": entity_name, "note": "Entity not found in AppSpec"}

    context: dict[str, Any] = {
        "entity": entity_name,
        "fields": [f.name for f in entity.fields],
    }

    # State machine
    if entity.state_machine:
        sm = entity.state_machine
        context["state_machine"] = {
            "status_field": sm.status_field,
            "states": sm.states,
            "transitions": [
                {
                    "from": t.from_state,
                    "to": t.to_state,
                    "guards": [str(g) for g in t.guards] if t.guards else None,
                }
                for t in sm.transitions
            ],
        }

    # Relationships (from field types)
    relationships: list[dict[str, str]] = []
    for field in entity.fields:
        if (
            field.type.kind
            in (
                FieldTypeKind.REF,
                FieldTypeKind.HAS_MANY,
                FieldTypeKind.HAS_ONE,
                FieldTypeKind.BELONGS_TO,
            )
            and field.type.ref_entity
        ):
            relationships.append({"type": field.type.kind.value, "target": field.type.ref_entity})
    if relationships:
        context["relationships"] = relationships

    return context


def _generate_design_questions(
    stories: list[StorySpec], entity_name: str | None, app_spec: AppSpec
) -> list[str]:
    """Generate design questions based on story patterns."""
    from dazzle.core.ir.stories import StoryTrigger

    questions: list[str] = []

    triggers = {s.trigger for s in stories}
    actors = {s.actor for s in stories}

    # No user trigger (automated)
    automated_triggers = {
        StoryTrigger.CRON_DAILY,
        StoryTrigger.CRON_HOURLY,
        StoryTrigger.EXTERNAL_EVENT,
        StoryTrigger.TIMER_ELAPSED,
    }
    if triggers & automated_triggers:
        questions.append(
            "What triggers this workflow? Consider: scheduled job, webhook, "
            "or event from another process."
        )

    # Multiple actors
    if len(actors) > 1:
        actor_list = ", ".join(sorted(actors))
        questions.append(
            f"Multiple actors involved ({actor_list}). How are handoffs between them managed?"
        )

    # Entity has state machine
    if entity_name:
        entity = next((e for e in app_spec.domain.entities if e.name == entity_name), None)
        if entity and entity.state_machine:
            states = ", ".join(entity.state_machine.states)
            questions.append(
                f"Entity has states: {states}. Which transitions does this workflow drive?"
            )

    # Exception paths
    has_unless = any(s.unless for s in stories)
    if has_unless:
        questions.append("Exception paths exist. Are compensations needed if a step fails?")

    # External service references (heuristic: scope mentions multiple entities)
    all_scopes: set[str] = set()
    for s in stories:
        all_scopes.update(s.scope)
    if len(all_scopes) > 1:
        questions.append(
            "Multiple entities in scope. What's the failure/retry strategy "
            "for cross-entity operations?"
        )

    # Constraints that imply business rules
    _GUARD_KEYWORDS = {"only", "must", "cannot", "requires", "four-eye", "reviewer", "approval"}
    for story in stories:
        for constraint in story.constraints:
            words = set(constraint.lower().split())
            if words & _GUARD_KEYWORDS:
                questions.append(
                    f'{story.story_id} constraint: "{constraint}". '
                    "How is this enforced in the process?"
                )
                break  # One question per story max

    # Side effects that need explicit steps
    for story in stories:
        for effect in story.side_effects:
            effect_lower = effect.lower()
            if any(
                kw in effect_lower
                for kw in ("email", "notification", "webhook", "api", "sync", "log")
            ):
                questions.append(
                    f'{story.story_id} declares side effect: "{effect}". Which step emits this?'
                )
                break

    # Integration-hinting language in titles
    _INTEGRATION_KEYWORDS = {"api", "hmrc", "xero", "sync", "file", "pull", "submit", "webhook"}
    integration_stories = [
        s for s in stories if set(s.title.lower().split()) & _INTEGRATION_KEYWORDS
    ]
    if integration_stories:
        titles = ", ".join(s.story_id for s in integration_stories[:3])
        questions.append(
            f"Stories reference external integrations ({titles}). "
            "What is the failure/retry/compensation strategy for API calls?"
        )

    return questions


def _build_review_checklist(stories: list[StorySpec]) -> list[dict[str, Any]]:
    """Build a review checklist from story contract obligations.

    Extracts constraints, side effects, and exception branches that the
    implementing process must handle. Each item maps a story obligation
    to a verification question.
    """
    checklist: list[dict[str, Any]] = []

    for story in stories:
        # Constraints → guard/invariant checks
        for constraint in story.constraints:
            checklist.append(
                {
                    "story_id": story.story_id,
                    "type": "constraint",
                    "obligation": constraint,
                    "verify": f"Process must enforce: {constraint}",
                }
            )

        # Side effects → explicit step or event emission
        for effect in story.side_effects:
            checklist.append(
                {
                    "story_id": story.story_id,
                    "type": "side_effect",
                    "obligation": effect,
                    "verify": f"Process must emit or trigger: {effect}",
                }
            )

        # Unless branches → compensation or error handling
        for exception in story.unless:
            checklist.append(
                {
                    "story_id": story.story_id,
                    "type": "exception",
                    "obligation": exception.condition,
                    "verify": (
                        f"Process must handle: {exception.condition} → "
                        + ", ".join(exception.then_outcomes)
                    ),
                }
            )

    return checklist


# =============================================================================
# Process Runs Handler
# =============================================================================


async def _list_runs_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for listing process runs."""
    from dazzle.core.process.adapter import ProcessStatus

    try:
        adapter = _get_process_adapter(project_root)
        await adapter.initialize()

        process_name = args.get("process_name")
        status_filter = args.get("status")
        limit = args.get("limit", 50)

        status = ProcessStatus(status_filter) if status_filter else None

        runs = await adapter.list_runs(
            process_name=process_name,
            status=status,
            limit=limit,
        )

        summaries: list[ProcessRunSummary] = []
        for run in runs:
            duration = None
            if run.completed_at:
                duration = (run.completed_at - run.started_at).total_seconds()

            summaries.append(
                ProcessRunSummary(
                    run_id=run.run_id,
                    process_name=run.process_name,
                    status=run.status.value,
                    current_step=run.current_step,
                    started_at=run.started_at.isoformat(),
                    duration_seconds=duration,
                    error=run.error,
                )
            )

        return json.dumps(
            {
                "count": len(summaries),
                "runs": [asdict(s) for s in summaries],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def list_process_runs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List process runs with optional filters."""
    import asyncio

    try:
        return asyncio.run(_list_runs_async(project_root, args))
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


async def _get_run_async(project_root: Path, args: dict[str, Any]) -> str:
    """Async implementation for getting a process run."""
    try:
        adapter = _get_process_adapter(project_root)
        await adapter.initialize()

        run_id = args.get("run_id")
        if not run_id:
            return json.dumps({"error": "run_id is required"})

        run = await adapter.get_run(run_id)
        if not run:
            return json.dumps({"error": f"Run '{run_id}' not found"})

        duration = None
        if run.completed_at:
            duration = (run.completed_at - run.started_at).total_seconds()

        return json.dumps(
            {
                "run_id": run.run_id,
                "process_name": run.process_name,
                "process_version": run.process_version,
                "dsl_version": run.dsl_version,
                "status": run.status.value,
                "current_step": run.current_step,
                "inputs": run.inputs,
                "context": run.context,
                "outputs": run.outputs,
                "error": run.error,
                "idempotency_key": run.idempotency_key,
                "started_at": run.started_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "duration_seconds": duration,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_process_run_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get detailed information about a specific process run."""
    import asyncio

    run_id = args.get("run_id") if args else None
    if not run_id:
        return json.dumps({"error": "run_id is required"})

    try:
        return asyncio.run(_get_run_async(project_root, args))
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Process Inspection Handler
# =============================================================================


def inspect_process_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Inspect a process definition."""
    process_name = args.get("process_name") if args else None

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

        stories: list[StorySpec] = list(app_spec.stories) if app_spec.stories else []

        # Fall back to persisted stories from .dazzle/stories/stories.json
        if not stories:
            from dazzle.core.stories_persistence import load_stories

            stories = load_stories(project_root)

        proc = next((p for p in processes if p.name == process_name), None)
        if not proc:
            available = [p.name for p in processes]
            return json.dumps(
                {
                    "error": f"Process '{process_name}' not found",
                    "available_processes": available,
                }
            )

        # Get linked stories
        linked_stories = [
            {"story_id": s.story_id, "title": s.title}
            for s in stories
            if s.story_id in proc.implements
        ]

        # Format trigger
        trigger_info = None
        if proc.trigger:
            trigger_info = {
                "kind": proc.trigger.kind.value,
                "entity_name": proc.trigger.entity_name,
                "event_type": proc.trigger.event_type,
                "from_status": proc.trigger.from_status,
                "to_status": proc.trigger.to_status,
                "cron": proc.trigger.cron,
                "interval_seconds": proc.trigger.interval_seconds,
            }

        # Format steps
        formatted_steps = [_format_step(s) for s in proc.steps]

        return json.dumps(
            {
                "name": proc.name,
                "title": proc.title,
                "description": proc.description,
                "implements": proc.implements,
                "linked_stories": linked_stories,
                "trigger": trigger_info,
                "inputs": [
                    {
                        "name": i.name,
                        "type": i.type,
                        "required": i.required,
                        "default": i.default,
                        "description": i.description,
                    }
                    for i in proc.inputs
                ],
                "outputs": [
                    {"name": o.name, "type": o.type, "description": o.description}
                    for o in proc.outputs
                ],
                "steps": formatted_steps,
                "compensations": [
                    {"name": c.name, "service": c.service, "timeout_seconds": c.timeout_seconds}
                    for c in proc.compensations
                ],
                "timeout_seconds": proc.timeout_seconds,
                "overlap_policy": proc.overlap_policy.value,
                "events": {
                    "on_start": proc.events.on_start,
                    "on_complete": proc.events.on_complete,
                    "on_failure": proc.events.on_failure,
                },
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _format_step(step: ProcessStepSpec) -> dict[str, Any]:
    """Format a process step for JSON output."""
    from dazzle.core.ir.process import StepKind

    result: dict[str, Any] = {
        "name": step.name,
        "kind": step.kind.value,
        "timeout_seconds": step.timeout_seconds,
    }

    if step.kind == StepKind.SERVICE:
        result["service"] = step.service
    elif step.kind == StepKind.SEND:
        result["channel"] = step.channel
        result["message"] = step.message
    elif step.kind == StepKind.WAIT:
        result["wait_duration_seconds"] = step.wait_duration_seconds
        result["wait_for_signal"] = step.wait_for_signal
    elif step.kind == StepKind.HUMAN_TASK and step.human_task:
        result["surface"] = step.human_task.surface
        result["assignee_role"] = step.human_task.assignee_role
        result["outcomes"] = [
            {"name": o.name, "label": o.label, "goto": o.goto} for o in step.human_task.outcomes
        ]
    elif step.kind == StepKind.SUBPROCESS:
        result["subprocess"] = step.subprocess
    elif step.kind == StepKind.PARALLEL:
        result["parallel_steps"] = [_format_step(s) for s in step.parallel_steps]
        result["parallel_policy"] = step.parallel_policy.value

    if step.condition:
        result["condition"] = step.condition

    if step.retry:
        result["retry"] = {
            "max_attempts": step.retry.max_attempts,
            "backoff": step.retry.backoff.value,
        }

    if step.on_success:
        result["on_success"] = step.on_success
    if step.on_failure:
        result["on_failure"] = step.on_failure
    if step.compensate_with:
        result["compensate_with"] = step.compensate_with

    return result


# =============================================================================
# List Processes Handler
# =============================================================================


def list_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all processes in the project."""
    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

        process_list = []
        for proc in processes:
            process_list.append(
                {
                    "name": proc.name,
                    "title": proc.title,
                    "description": proc.description,
                    "implements": proc.implements,
                    "trigger_kind": proc.trigger.kind.value if proc.trigger else None,
                    "step_count": len(proc.steps),
                    "timeout_seconds": proc.timeout_seconds,
                }
            )

        return json.dumps(
            {
                "count": len(process_list),
                "processes": process_list,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# =============================================================================
# Process Diagram Handler
# =============================================================================


def get_process_diagram_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate a Mermaid diagram for a process.

    Produces a flowchart showing:
    - Process trigger (start node)
    - Steps as nodes with kind-specific shapes
    - Flow control edges (on_success, on_failure)
    - Human task outcome branches
    - Parallel step groupings
    - Compensation handlers (optional)
    """
    process_name = args.get("process_name") if args else None
    include_compensations = args.get("include_compensations", False) if args else False
    diagram_type = args.get("type", "flowchart") if args else "flowchart"

    if not process_name:
        return json.dumps({"error": "process_name is required"})

    try:
        app_spec = _load_app_spec(project_root)

        processes: list[ProcessSpec] = list(app_spec.processes) if app_spec.processes else []

        # Merge with persisted processes
        from dazzle.core.process_persistence import load_processes as load_persisted_processes

        persisted = load_persisted_processes(project_root)
        dsl_names = {p.name for p in processes}
        for p in persisted:
            if p.name not in dsl_names:
                processes.append(p)

        proc = next((p for p in processes if p.name == process_name), None)
        if not proc:
            available = [p.name for p in processes]
            return json.dumps(
                {
                    "error": f"Process '{process_name}' not found",
                    "available_processes": available,
                }
            )

        # Generate diagram
        mermaid_code = _generate_process_mermaid(proc, include_compensations, diagram_type)

        return json.dumps(
            {
                "process_name": proc.name,
                "title": proc.title,
                "type": diagram_type,
                "diagram": mermaid_code,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _generate_process_mermaid(
    proc: ProcessSpec,
    include_compensations: bool = False,
    diagram_type: str = "flowchart",
) -> str:
    """Generate Mermaid diagram code for a process."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []

    if diagram_type == "stateDiagram":
        return _generate_state_diagram(proc, include_compensations)

    # Use flowchart TD (top-down)
    lines.append("flowchart TD")
    lines.append(f"    %% Process: {proc.name}")
    if proc.title:
        lines.append(f"    %% Title: {proc.title}")
    lines.append("")

    # Start node (trigger)
    trigger_label = _get_trigger_label(proc)
    lines.append(f"    START([{trigger_label}])")
    lines.append("")

    # Steps subgraph
    lines.append("    subgraph steps [Process Steps]")

    step_count = len(proc.steps)
    for i, step in enumerate(proc.steps):
        step_lines = _step_to_mermaid(step, i, step_count)
        lines.extend(step_lines)

    lines.append("    end")
    lines.append("")

    # End node
    lines.append("    COMPLETE([Complete])")
    lines.append("    FAILED([Failed])")
    lines.append("")

    # Flow edges
    lines.append("    %% Flow")
    if proc.steps:
        lines.append(f"    START --> {proc.steps[0].name}")

    for i, step in enumerate(proc.steps):
        step_edges = _step_edges(step, i, proc.steps)
        lines.extend(step_edges)

    lines.append("")

    # Compensation handlers (optional)
    if include_compensations and proc.compensations:
        lines.append("    subgraph compensations [Compensations]")
        for comp in proc.compensations:
            lines.append(f"        {comp.name}[/{comp.name}/]")
        lines.append("    end")
        lines.append("")
        lines.append("    FAILED -.-> compensations")

    # Styling
    lines.append("")
    lines.append("    %% Styling")
    lines.append("    classDef startEnd fill:#f9f,stroke:#333,stroke-width:2px")
    lines.append("    classDef serviceStep fill:#bbf,stroke:#333")
    lines.append("    classDef humanTask fill:#fbb,stroke:#333")
    lines.append("    classDef waitStep fill:#bfb,stroke:#333")
    lines.append("    class START,COMPLETE,FAILED startEnd")

    # Apply styling to steps
    for step in proc.steps:
        if step.kind == StepKind.SERVICE:
            lines.append(f"    class {step.name} serviceStep")
        elif step.kind == StepKind.HUMAN_TASK:
            lines.append(f"    class {step.name} humanTask")
        elif step.kind == StepKind.WAIT:
            lines.append(f"    class {step.name} waitStep")

    return "\n".join(lines)


def _generate_state_diagram(proc: ProcessSpec, include_compensations: bool) -> str:
    """Generate state diagram variant."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    lines.append("stateDiagram-v2")
    lines.append(f"    %% Process: {proc.name}")
    lines.append("")

    # State declarations
    lines.append("    [*] --> " + (proc.steps[0].name if proc.steps else "[*]"))
    lines.append("")

    for step in proc.steps:
        label = _get_step_label(step)
        lines.append(f"    {step.name}: {label}")

    lines.append("")

    # Transitions
    for i, step in enumerate(proc.steps):
        next_step = proc.steps[i + 1].name if i + 1 < len(proc.steps) else "[*]"

        if step.on_success:
            if step.on_success in FLOW_COMPLETE_KEYWORDS:
                lines.append(f"    {step.name} --> [*]: success")
            else:
                lines.append(f"    {step.name} --> {step.on_success}: success")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        if step.on_failure:
            if step.on_failure in FLOW_FAILURE_KEYWORDS:
                lines.append(f"    {step.name} --> [*]: failure")
            else:
                lines.append(f"    {step.name} --> {step.on_failure}: failure")

        # Human task outcomes
        if step.kind == StepKind.HUMAN_TASK and step.human_task:
            for outcome in step.human_task.outcomes:
                if outcome.goto:
                    if outcome.goto in FLOW_COMPLETE_KEYWORDS:
                        lines.append(f"    {step.name} --> [*]: {outcome.name}")
                    else:
                        lines.append(f"    {step.name} --> {outcome.goto}: {outcome.name}")

    return "\n".join(lines)


def _get_trigger_label(proc: ProcessSpec) -> str:
    """Get human-readable label for process trigger."""
    if not proc.trigger:
        return "Manual Start"

    from dazzle.core.ir.process import ProcessTriggerKind

    kind = proc.trigger.kind
    if kind == ProcessTriggerKind.ENTITY_EVENT:
        event = proc.trigger.event_type or "event"
        entity = proc.trigger.entity_name or "entity"
        return f"{entity}.{event}"
    elif kind == ProcessTriggerKind.ENTITY_STATUS_TRANSITION:
        entity = proc.trigger.entity_name or "entity"
        from_s = proc.trigger.from_status or "*"
        to_s = proc.trigger.to_status or "*"
        return f"{entity}: {from_s} → {to_s}"
    elif kind == ProcessTriggerKind.SCHEDULE_CRON:
        return f"cron: {proc.trigger.cron}"
    elif kind == ProcessTriggerKind.SCHEDULE_INTERVAL:
        return f"every {proc.trigger.interval_seconds}s"
    elif kind == ProcessTriggerKind.SIGNAL:
        return "External Signal"
    elif kind == ProcessTriggerKind.PROCESS_COMPLETED:
        return f"after: {proc.trigger.process_name}"
    else:
        return "Manual"


def _get_step_label(step: ProcessStepSpec) -> str:
    """Get human-readable label for a step."""
    from dazzle.core.ir.process import StepKind

    if step.kind == StepKind.SERVICE:
        return step.service or step.name
    elif step.kind == StepKind.SEND:
        return f"Send: {step.message or step.channel}"
    elif step.kind == StepKind.WAIT:
        if step.wait_for_signal:
            return f"Wait for: {step.wait_for_signal}"
        elif step.wait_duration_seconds:
            return f"Wait: {step.wait_duration_seconds}s"
        else:
            return "Wait"
    elif step.kind == StepKind.HUMAN_TASK:
        if step.human_task:
            return f"👤 {step.human_task.surface or step.name}"
        return f"👤 {step.name}"
    elif step.kind == StepKind.SUBPROCESS:
        return f"→ {step.subprocess}"
    elif step.kind == StepKind.PARALLEL:
        return f"Parallel ({len(step.parallel_steps)})"
    elif step.kind == StepKind.CONDITION:
        return f"? {step.condition or step.name}"
    else:
        return step.name


def _step_to_mermaid(step: ProcessStepSpec, index: int, total: int) -> list[str]:
    """Convert a step to Mermaid node definition."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    label = _get_step_label(step)

    # Use different shapes for different step kinds
    if step.kind == StepKind.SERVICE:
        lines.append(f"        {step.name}[{label}]")
    elif step.kind == StepKind.SEND:
        lines.append(f"        {step.name}>{label}]")  # Asymmetric shape
    elif step.kind == StepKind.WAIT:
        lines.append(f"        {step.name}{{{{{label}}}}}")  # Hexagon
    elif step.kind == StepKind.HUMAN_TASK:
        lines.append(f"        {step.name}[/{label}\\]")  # Trapezoid
    elif step.kind == StepKind.SUBPROCESS:
        lines.append(f'        {step.name}[["{label}"]]')  # Subroutine
    elif step.kind == StepKind.PARALLEL:
        lines.append(f"        subgraph {step.name} [{label}]")
        lines.append("            direction LR")
        for i, ps in enumerate(step.parallel_steps):
            ps_lines = _step_to_mermaid(ps, i, len(step.parallel_steps))
            lines.extend(ps_lines)
        lines.append("        end")
    elif step.kind == StepKind.CONDITION:
        lines.append(f"        {step.name}{{{label}}}")  # Diamond/rhombus
    else:
        lines.append(f"        {step.name}[{label}]")

    return lines


def _step_edges(step: ProcessStepSpec, index: int, steps: list[ProcessStepSpec]) -> list[str]:
    """Generate edges for a step."""
    from dazzle.core.ir.process import StepKind

    lines: list[str] = []
    next_step = steps[index + 1].name if index + 1 < len(steps) else "COMPLETE"

    if step.kind == StepKind.CONDITION:
        # Conditional branching
        true_target = step.on_true or next_step
        false_target = step.on_false or "FAILED"
        if true_target in FLOW_COMPLETE_KEYWORDS:
            true_target = "COMPLETE"
        if false_target in FLOW_FAILURE_KEYWORDS:
            false_target = "FAILED"
        lines.append(f"    {step.name} -->|Yes| {true_target}")
        lines.append(f"    {step.name} -->|No| {false_target}")
    elif step.kind == StepKind.HUMAN_TASK and step.human_task and step.human_task.outcomes:
        # Human task outcomes as branches
        for outcome in step.human_task.outcomes:
            target = outcome.goto or next_step
            if target in FLOW_COMPLETE_KEYWORDS:
                target = "COMPLETE"
            elif target in FLOW_FAILURE_KEYWORDS:
                target = "FAILED"
            label = outcome.label or outcome.name
            lines.append(f"    {step.name} -->|{label}| {target}")
    else:
        # Normal flow
        if step.on_success:
            target = step.on_success
            if target in FLOW_COMPLETE_KEYWORDS:
                target = "COMPLETE"
            lines.append(f"    {step.name} --> {target}")
        else:
            lines.append(f"    {step.name} --> {next_step}")

        # Error flow
        if step.on_failure:
            target = step.on_failure
            if target in FLOW_FAILURE_KEYWORDS:
                target = "FAILED"
            lines.append(f"    {step.name} -.->|error| {target}")

    return lines
