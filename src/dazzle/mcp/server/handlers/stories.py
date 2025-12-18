"""
Story/behaviour tool handlers.

Handles DSL spec extraction, story proposal, saving, retrieval, and stub generation.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

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


# =============================================================================
# Serialization Helpers
# =============================================================================


def _serialize_story(story: StorySpec) -> dict[str, Any]:
    """Convert a StorySpec to a JSON-serializable dictionary.

    This is the canonical serialization format for stories used across
    all story-related handlers.
    """
    return {
        "story_id": story.story_id,
        "title": story.title,
        "actor": story.actor,
        "trigger": story.trigger.value,
        "scope": story.scope,
        "preconditions": story.preconditions,
        "happy_path_outcome": story.happy_path_outcome,
        "side_effects": story.side_effects,
        "constraints": story.constraints,
        "variants": story.variants,
        "status": story.status.value,
        "created_at": story.created_at,
        "accepted_at": story.accepted_at,
    }


def _serialize_test_design(td: Any) -> dict[str, Any]:
    """Convert a TestDesignSpec to a JSON-serializable dictionary.

    This is the canonical serialization format for test designs.
    """
    return {
        "test_id": td.test_id,
        "title": td.title,
        "description": td.description,
        "persona": td.persona,
        "trigger": td.trigger.value,
        "steps": [
            {
                "action": step.action.value,
                "target": step.target,
                "data": step.data,
                "rationale": step.rationale,
            }
            for step in td.steps
        ],
        "expected_outcomes": td.expected_outcomes,
        "entities": td.entities,
        "tags": td.tags,
        "status": td.status.value,
    }


# =============================================================================
# Handler Functions
# =============================================================================


def get_dsl_spec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get complete DSL specification for story generation."""
    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

        # Build comprehensive spec
        spec: dict[str, Any] = {
            "project_path": str(project_root),
            "app_name": app_spec.name,
            "entities": [],
            "surfaces": [],
            "personas": [],
            "workspaces": [],
            "state_machines": [],
        }

        # Entities with fields and state machines
        for entity in app_spec.domain.entities:
            entity_info: dict[str, Any] = {
                "name": entity.name,
                "title": entity.title,
                "fields": [
                    {
                        "name": f.name,
                        "type": str(f.type.kind.value) if f.type.kind else str(f.type),
                        "required": f.is_required,
                    }
                    for f in entity.fields
                ],
            }

            # Add state machine if present
            if entity.state_machine:
                sm = entity.state_machine
                entity_info["state_machine"] = {
                    "field": sm.status_field,
                    "states": sm.states,
                    "transitions": [
                        {
                            "from": t.from_state,
                            "to": t.to_state,
                            "trigger": t.trigger.value if t.trigger else None,
                        }
                        for t in sm.transitions
                    ],
                }
                spec["state_machines"].append(
                    {"entity": entity.name, "field": sm.status_field, "states": sm.states}
                )

            spec["entities"].append(entity_info)

        # Surfaces with modes
        for surface in app_spec.surfaces:
            spec["surfaces"].append(
                {
                    "name": surface.name,
                    "title": surface.title,
                    "entity": surface.entity_ref,
                    "mode": surface.mode.value if surface.mode else None,
                }
            )

        # Personas
        for persona in app_spec.personas:
            spec["personas"].append(
                {
                    "id": persona.id,
                    "label": persona.label,
                    "description": persona.description,
                }
            )

        # Workspaces
        for workspace in app_spec.workspaces:
            spec["workspaces"].append(
                {
                    "name": workspace.name,
                    "title": workspace.title,
                    "purpose": workspace.purpose,
                    "regions": [r.name for r in workspace.regions],
                }
            )

        return json.dumps(spec, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def propose_stories_from_dsl_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze DSL and propose behavioural user stories."""
    from datetime import datetime

    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import get_next_story_id

    try:
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        app_spec = build_appspec(modules, manifest.project_root)

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
                    r.name == entity.name or entity.name.lower() in r.name.lower()
                    for r in ws.regions
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

        # Convert to JSON-serializable format using shared helper
        stories_data = [_serialize_story(s) for s in stories]

        return json.dumps(
            {
                "proposed_count": len(stories_data),
                "max_stories": max_stories,
                "note": "These are draft stories. Review and call save_stories with accepted stories.",
                "stories": stories_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def save_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Save stories to .dazzle/stories/stories.json."""
    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import add_stories, get_stories_file

    stories_data = args.get("stories", [])
    overwrite = args.get("overwrite", False)

    if not stories_data:
        return json.dumps({"error": "No stories provided"})

    try:
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
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def get_stories_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Retrieve stories filtered by status."""
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status, get_stories_file

    status_filter = args.get("status_filter", "all")

    try:
        status = None
        if status_filter != "all":
            status = StoryStatus(status_filter)

        stories = get_stories_by_status(project_root, status)
        stories_file = get_stories_file(project_root)

        # Use shared serialization helper
        stories_data = [_serialize_story(s) for s in stories]

        return json.dumps(
            {
                "file": str(stories_file),
                "filter": status_filter,
                "count": len(stories_data),
                "stories": stories_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def generate_story_stubs_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate Python service stubs from accepted stories."""
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status
    from dazzle.stubs.story_stub_generator import generate_story_stubs_file

    story_ids = args.get("story_ids")
    output_dir = args.get("output_dir", "services")

    try:
        # Get accepted stories
        stories = get_stories_by_status(project_root, StoryStatus.ACCEPTED)

        if story_ids:
            stories = [s for s in stories if s.story_id in story_ids]

        if not stories:
            return json.dumps(
                {
                    "status": "no_stories",
                    "message": "No accepted stories found. Use get_stories to see available stories.",
                }
            )

        # Generate stubs
        stubs_code = generate_story_stubs_file(stories)

        # Write to file
        output_path = project_root / output_dir
        output_path.mkdir(parents=True, exist_ok=True)
        stubs_file = output_path / "story_handlers.py"
        stubs_file.write_text(stubs_code, encoding="utf-8")

        return json.dumps(
            {
                "status": "generated",
                "file": str(stubs_file),
                "story_count": len(stories),
                "stories": [s.story_id for s in stories],
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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

    story_ids = args.get("story_ids")
    include_draft = args.get("include_draft", False)

    try:
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

        # Convert all stories to test designs
        test_designs = [story_to_test_design(s, i) for i, s in enumerate(stories)]

        # Use shared serialization helper
        designs_data = [_serialize_test_design(td) for td in test_designs]

        return json.dumps(
            {
                "status": "generated",
                "count": len(designs_data),
                "note": "Review these designs and call save_test_designs to persist them.",
                "test_designs": designs_data,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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
