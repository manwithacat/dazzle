"""
Process proposal generation — workflow design briefs from uncovered stories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..common import extract_progress, handler_error_json
from ..utils import slugify as _slugify
from . import _helpers
from .coverage import (
    CRUD_OUTCOME_PATTERNS,
    UI_FEEDBACK_PATTERNS,
    _find_missing_aspects,
)

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.ir.process import ProcessSpec
    from dazzle.core.ir.stories import StorySpec


# =============================================================================
# Data Classes
# =============================================================================


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


# =============================================================================
# Helper Functions
# =============================================================================


# =============================================================================
# Process Proposal Handler
# =============================================================================


@handler_error_json
def propose_processes_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate workflow design briefs from uncovered stories.

    Clusters stories into workflow-oriented groups and returns design briefs
    that guide the agent in composing processes, rather than generating
    ready-made DSL stubs.
    """
    progress = extract_progress(args)
    try:
        progress.log_sync("Loading app spec and stories...")
        app_spec = _helpers.load_app_spec(project_root)
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

        progress.log_sync(f"Clustering {len(target_stories)} stories into workflows...")
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
        if words & CRUD_OUTCOME_PATTERNS:
            has_crud_outcome = True
        elif not (words & UI_FEEDBACK_PATTERNS):
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

        # Step 3: CRUD stories -> process_not_recommended
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

        # Step 4: Lifecycle stories -> compose_process
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

        # Cron stories -> compose_process
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

        # External event stories -> compose_process
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
        # Constraints -> guard/invariant checks
        for constraint in story.constraints:
            checklist.append(
                {
                    "story_id": story.story_id,
                    "type": "constraint",
                    "obligation": constraint,
                    "verify": f"Process must enforce: {constraint}",
                }
            )

        # Side effects -> explicit step or event emission
        for effect in story.side_effects:
            checklist.append(
                {
                    "story_id": story.story_id,
                    "type": "side_effect",
                    "obligation": effect,
                    "verify": f"Process must emit or trigger: {effect}",
                }
            )

        # Unless branches -> compensation or error handling
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
