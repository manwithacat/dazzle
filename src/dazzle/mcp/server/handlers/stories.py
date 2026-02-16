"""
Story/behaviour tool handlers.

Handles DSL spec extraction, story proposal, saving, and retrieval.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .common import extract_progress, load_project_appspec, wrap_handler_errors
from .serializers import (
    serialize_entity_detail,
    serialize_entity_summary,
    serialize_story,
    serialize_story_summary,
    serialize_surface_detail,
    serialize_surface_summary,
    serialize_test_design_summary,
)

if TYPE_CHECKING:
    from dazzle.core.ir.stories import StorySpec

# =============================================================================
# Constants
# =============================================================================

# Maximum number of constraints to include per story (prevents overwhelming test cases)
MAX_CONSTRAINTS_PER_STORY = 3

# Maximum number of state machine transitions to generate stories for (per entity)
MAX_TRANSITIONS_PER_ENTITY = 3


# =============================================================================
# Trigger Mappings
# =============================================================================

# Lazy-initialized trigger mapping (imports aren't available at module load time)
_TRIGGER_MAP: dict[Any, Any] | None = None


def _get_trigger_map() -> dict[Any, Any]:
    """Get or create the StoryTrigger to TestDesignTrigger mapping.

    Uses lazy initialization since the IR types aren't available at module load.
    """
    global _TRIGGER_MAP
    if _TRIGGER_MAP is None:
        from dazzle.core.ir.stories import StoryTrigger
        from dazzle.core.ir.test_design import TestDesignTrigger

        _TRIGGER_MAP = {
            StoryTrigger.FORM_SUBMITTED: TestDesignTrigger.FORM_SUBMITTED,
            StoryTrigger.STATUS_CHANGED: TestDesignTrigger.STATUS_CHANGED,
            StoryTrigger.TIMER_ELAPSED: TestDesignTrigger.TIMER_ELAPSED,
            StoryTrigger.EXTERNAL_EVENT: TestDesignTrigger.EXTERNAL_EVENT,
            StoryTrigger.USER_CLICK: TestDesignTrigger.USER_CLICK,
            StoryTrigger.CRON_DAILY: TestDesignTrigger.CRON_DAILY,
            StoryTrigger.CRON_HOURLY: TestDesignTrigger.CRON_HOURLY,
        }
    return _TRIGGER_MAP


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
def propose_stories_from_dsl_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze DSL and propose behavioural user stories."""
    from datetime import datetime

    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import get_next_story_id

    progress = extract_progress(args)
    progress.log_sync("Parsing DSL and building app spec...")
    app_spec = load_project_appspec(project_root)

    max_stories = args.get("max_stories", 30)
    filter_entities = args.get("entities")

    stories: list[StorySpec] = []
    story_count = 0

    # Get starting story ID
    base_id = get_next_story_id(project_root)
    base_num = int(base_id[3:])

    def next_id() -> str:
        nonlocal story_count
        result = f"ST-{base_num + story_count:03d}"
        story_count += 1
        return result

    now = datetime.now(UTC).isoformat()

    # Default persona
    default_actor = "User"
    if app_spec.personas:
        default_actor = app_spec.personas[0].label or app_spec.personas[0].id

    progress.log_sync("Generating stories from entities...")
    # Generate stories from entities
    for entity in app_spec.domain.entities:
        if filter_entities and entity.name not in filter_entities:
            continue

        if story_count >= max_stories:
            break

        # Find persona for this entity (from workspace regions or UX variants)
        actor = default_actor
        for ws in app_spec.workspaces:
            if any(
                r.name == entity.name or entity.name.lower() in r.name.lower() for r in ws.regions
            ):
                # Workspace doesn't have persona directly, use default
                break

        # Story: Create entity via form
        stories.append(
            StorySpec(
                story_id=next_id(),
                title=f"{actor} creates a new {entity.title or entity.name}",
                actor=actor,
                trigger=StoryTrigger.FORM_SUBMITTED,
                scope=[entity.name],
                preconditions=[f"{actor} has permission to create {entity.name}"],
                happy_path_outcome=[
                    f"New {entity.name} is saved to database",
                    f"{actor} sees confirmation message",
                ],
                side_effects=[],
                constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][
                    :MAX_CONSTRAINTS_PER_STORY
                ],
                variants=["Validation error on required field"],
                status=StoryStatus.DRAFT,
                created_at=now,
            )
        )

        # Story: State machine transitions
        if entity.state_machine and story_count < max_stories:
            sm = entity.state_machine
            for transition in sm.transitions[:MAX_TRANSITIONS_PER_ENTITY]:
                if story_count >= max_stories:
                    break

                stories.append(
                    StorySpec(
                        story_id=next_id(),
                        title=f"{actor} changes {entity.name} from {transition.from_state} to {transition.to_state}",
                        actor=actor,
                        trigger=StoryTrigger.STATUS_CHANGED,
                        scope=[entity.name],
                        preconditions=[
                            f"{entity.name}.{sm.status_field} is '{transition.from_state}'"
                        ],
                        happy_path_outcome=[
                            f"{entity.name}.{sm.status_field} becomes '{transition.to_state}'",
                            "Timestamp is recorded",
                        ],
                        side_effects=[],
                        constraints=[f"Transition only allowed from '{transition.from_state}'"],
                        variants=[],
                        status=StoryStatus.DRAFT,
                        created_at=now,
                    )
                )

    # Auto-save draft stories to avoid requiring a separate save call
    # (which would force full content through context twice)
    from dazzle.core.stories_persistence import add_stories

    progress.log_sync(f"Saving {len(stories)} draft stories...")
    add_stories(project_root, stories, overwrite=False)

    # Return summaries only — the LLM just generated these and knows
    # the content; full details can be fetched on demand.
    return json.dumps(
        {
            "proposed_count": len(stories),
            "max_stories": max_stories,
            "note": "Draft stories saved. Use story(operation='get', story_ids=['ST-001']) for full details.",
            "stories": [serialize_story_summary(s) for s in stories],
        },
        indent=2,
    )


@wrap_handler_errors
def save_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save stories to .dazzle/stories/stories.json."""
    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import add_stories, get_stories_file

    progress = extract_progress(args)
    stories_data = args.get("stories", [])
    overwrite = args.get("overwrite", False)

    if not stories_data:
        return json.dumps({"error": "No stories provided"})

    progress.log_sync("Validating stories...")
    # Convert to StorySpec objects with validation
    stories: list[StorySpec] = []
    for s in stories_data:
        story = StorySpec(
            story_id=s["story_id"],
            title=s["title"],
            actor=s["actor"],
            trigger=StoryTrigger(s["trigger"]),
            scope=s.get("scope", []),
            preconditions=s.get("preconditions", []),
            happy_path_outcome=s.get("happy_path_outcome", []),
            side_effects=s.get("side_effects", []),
            constraints=s.get("constraints", []),
            variants=s.get("variants", []),
            status=StoryStatus(s.get("status", "draft")),
            created_at=s.get("created_at"),
            accepted_at=s.get("accepted_at"),
        )
        stories.append(story)

    progress.log_sync(f"Saving {len(stories)} stories...")
    # Save stories
    all_stories = add_stories(project_root, stories, overwrite=overwrite)
    stories_file = get_stories_file(project_root)

    return json.dumps(
        {
            "status": "saved",
            "file": str(stories_file),
            "saved_count": len(stories),
            "total_count": len(all_stories),
            "overwrite": overwrite,
        },
        indent=2,
    )


@wrap_handler_errors
def get_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve stories filtered by status.

    Returns compact summaries by default. When ``story_ids`` is provided,
    returns full content for those specific stories only, keeping context
    usage proportional to what the caller actually needs.
    """
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status, get_stories_file

    progress = extract_progress(args)
    status_filter = args.get("status_filter", "all")
    story_ids = args.get("story_ids")

    progress.log_sync("Loading stories...")
    status = None
    if status_filter != "all":
        status = StoryStatus(status_filter)

    stories = get_stories_by_status(project_root, status)
    stories_file = get_stories_file(project_root)

    if story_ids:
        # Return full content for requested stories only
        filtered = [s for s in stories if s.story_id in story_ids]
        return json.dumps(
            {
                "file": str(stories_file),
                "filter": status_filter,
                "count": len(filtered),
                "stories": [serialize_story(s) for s in filtered],
            },
            indent=2,
        )

    # Default: return compact summaries
    return json.dumps(
        {
            "file": str(stories_file),
            "filter": status_filter,
            "count": len(stories),
            "stories": [serialize_story_summary(s) for s in stories],
            "guidance": "Use story(operation='get', story_ids=['ST-001']) to fetch full story details.",
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
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status

    from .process import stories_coverage_handler

    progress = extract_progress(args)
    actor_filter_str: str | None = args.get("persona")

    progress.log_sync("Loading stories for wall view...")
    # Get accepted stories (the founder's approved work)
    stories = get_stories_by_status(project_root, StoryStatus.ACCEPTED)
    if not stories:
        # Fall back to all stories
        stories = get_stories_by_status(project_root, None)

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
            if s.actor.lower() == actor_filter_str.lower()
            or actor_filter_str.lower() in s.actor.lower()
        ]

    # Collect unique personas for filter UI
    personas = sorted({s.actor for s in stories if s.actor})

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
    md_lines = ["Story Wall", ""]
    if actor_filter_str:
        md_lines.append(f"Filtered by: {actor_filter_str}")
        md_lines.append("")

    md_lines.append(f"Working ({len(working)})")
    for s in working:
        md_lines.append(f"  [ok] {s['title']}  ({s['actor']})")
    md_lines.append("")
    md_lines.append(f"Needs polish ({len(needs_polish)})")
    for s in needs_polish:
        md_lines.append(f"  [..] {s['title']}  ({s['actor']})")
    md_lines.append("")
    md_lines.append(f"Not started ({len(not_started)})")
    for s in not_started:
        md_lines.append(f"  [  ] {s['title']}  ({s['actor']})")

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
        },
        indent=2,
    )


@wrap_handler_errors
def generate_tests_from_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate test designs from accepted stories.

    Converts behavioural stories (what should happen) into test designs
    (how to verify it happens). This bridges the gap between story
    acceptance criteria and executable test cases.
    """
    from dazzle.core.ir.stories import StoryStatus, StoryTrigger
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.core.stories_persistence import get_stories_by_status

    progress = extract_progress(args)
    story_ids = args.get("story_ids")
    include_draft = args.get("include_draft", False)

    progress.log_sync("Loading stories for test generation...")
    # Get stories to convert
    stories = get_stories_by_status(project_root, StoryStatus.ACCEPTED)

    # Optionally include draft stories
    if include_draft:
        draft_stories = get_stories_by_status(project_root, StoryStatus.DRAFT)
        stories = stories + draft_stories

    # Filter by specific story IDs if provided
    if story_ids:
        stories = [s for s in stories if s.story_id in story_ids]

    if not stories:
        return json.dumps(
            {
                "status": "no_stories",
                "message": "No stories found. Use propose_stories_from_dsl or save_stories first.",
            }
        )

    # Get trigger mapping (lazily initialized)
    trigger_map = _get_trigger_map()

    def story_to_test_design(story: StorySpec, index: int) -> TestDesignSpec:
        """Convert a single story to a test design."""
        # Convert story ID format: ST-001 -> TD-001
        test_id = story.story_id.replace("ST-", "TD-")

        # Build steps from story structure
        steps: list[TestDesignStep] = []

        # Step 1: Login as the actor
        steps.append(
            TestDesignStep(
                action=TestDesignAction.LOGIN_AS,
                target=story.actor,
                rationale=f"Test from {story.actor}'s perspective",
            )
        )

        # Step 2: Setup steps from given/preconditions
        for condition in story.effective_given:
            # Parse condition to determine appropriate action
            if "is set" in condition.lower() or "exists" in condition.lower():
                # Existence check - create or navigate
                entity = _extract_entity_from_condition(condition, story.scope)
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.ASSERT_VISIBLE,
                        target=entity,
                        rationale=f"Precondition: {condition}",
                    )
                )
            elif "is '" in condition or 'is "' in condition:
                # State check - assert current state
                entity = _extract_entity_from_condition(condition, story.scope)
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.ASSERT_TEXT,
                        target=entity,
                        data={"condition": condition},
                        rationale=f"Precondition: {condition}",
                    )
                )
            else:
                # Generic precondition - navigate to entity
                entity = _extract_entity_from_condition(condition, story.scope)
                if entity:
                    steps.append(
                        TestDesignStep(
                            action=TestDesignAction.NAVIGATE_TO,
                            target=entity,
                            rationale=f"Setup: {condition}",
                        )
                    )

        # Step 3: Action steps from when conditions
        when_conditions = [c.expression for c in story.when] if story.when else []
        for condition in when_conditions:
            if "changes to" in condition.lower():
                # State transition
                entity = _extract_entity_from_condition(condition, story.scope)
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.TRIGGER_TRANSITION,
                        target=entity,
                        data={"transition": condition},
                        rationale=f"Trigger: {condition}",
                    )
                )
            elif "submit" in condition.lower() or "form" in condition.lower():
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CLICK,
                        target="submit_button",
                        rationale=f"Action: {condition}",
                    )
                )
            elif "click" in condition.lower():
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CLICK,
                        target=_extract_target_from_condition(condition),
                        rationale=f"Action: {condition}",
                    )
                )

        # If no when conditions, infer action from trigger
        if not when_conditions:
            if story.trigger == StoryTrigger.FORM_SUBMITTED:
                # Navigate to create form and submit
                entity = story.scope[0] if story.scope else "form"
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.NAVIGATE_TO,
                        target=f"{entity}_create",
                        rationale="Navigate to creation form",
                    )
                )
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.FILL,
                        target="form",
                        data={"fields": "required_fields"},
                        rationale="Fill form with test data",
                    )
                )
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CLICK,
                        target="submit_button",
                        rationale="Submit the form",
                    )
                )
            elif story.trigger == StoryTrigger.STATUS_CHANGED:
                entity = story.scope[0] if story.scope else "entity"
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.TRIGGER_TRANSITION,
                        target=entity,
                        rationale="Trigger status change",
                    )
                )
            elif story.trigger == StoryTrigger.USER_CLICK:
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.CLICK,
                        target="action_button",
                        rationale="Perform user action",
                    )
                )

        # Expected outcomes from then/happy_path_outcome
        expected_outcomes = story.effective_then.copy()

        # Add side effects as outcomes
        for effect in story.side_effects:
            expected_outcomes.append(f"Side effect: {effect}")

        return TestDesignSpec(
            test_id=test_id,
            title=f"Verify: {story.title}",
            description=f"Test generated from story {story.story_id}",
            persona=story.actor,
            trigger=trigger_map.get(story.trigger, TestDesignTrigger.USER_CLICK),
            steps=steps,
            expected_outcomes=expected_outcomes,
            entities=story.scope.copy(),
            tags=[f"story:{story.story_id}"],
            status=TestDesignStatus.PROPOSED,
        )

    progress.log_sync(f"Converting {len(stories)} stories to test designs...")
    # Convert all stories to test designs
    test_designs = [story_to_test_design(s, i) for i, s in enumerate(stories)]

    # Auto-save generated test designs to avoid a separate save round-trip
    from dazzle.testing.test_design_persistence import add_test_designs

    progress.log_sync("Saving test designs...")
    add_test_designs(project_root, test_designs, overwrite=False)

    # Return summaries only to reduce context usage
    return json.dumps(
        {
            "status": "generated",
            "count": len(test_designs),
            "note": "Test designs saved. Use test_design(operation='get', status_filter='proposed') for full details.",
            "test_designs": [serialize_test_design_summary(td) for td in test_designs],
        },
        indent=2,
    )


def _extract_entity_from_condition(condition: str, scope: list[str]) -> str:
    """Extract entity name from a condition string."""
    # Check if any scope entity is mentioned
    for entity in scope:
        if entity.lower() in condition.lower():
            return entity
    # Look for Entity.field pattern
    if "." in condition:
        return condition.split(".")[0].strip()
    # Default to first entity in scope
    return scope[0] if scope else "entity"


def _extract_target_from_condition(condition: str) -> str:
    """Extract target element from a condition like 'click the submit button'."""
    # Simple extraction - look for quoted strings or common patterns
    import re

    # Look for quoted strings
    quoted: list[str] = re.findall(r"['\"]([^'\"]+)['\"]", condition)
    if quoted:
        return quoted[0]
    # Look for "the X" pattern
    the_match = re.search(r"the\s+(\w+)", condition.lower())
    if the_match:
        return the_match.group(1)
    return "button"
