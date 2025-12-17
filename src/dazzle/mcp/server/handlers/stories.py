"""
Story/behaviour tool handlers.

Handles DSL spec extraction, story proposal, saving, retrieval, and stub generation.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules


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
                        :3
                    ],
                    variants=["Validation error on required field"],
                    status=StoryStatus.DRAFT,
                    created_at=now,
                )
            )

            # Story: State machine transitions
            if entity.state_machine and story_count < max_stories:
                sm = entity.state_machine
                for transition in sm.transitions[:3]:  # Limit transitions
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

        # Convert to JSON-serializable format
        stories_data = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "actor": s.actor,
                "trigger": s.trigger.value,
                "scope": s.scope,
                "preconditions": s.preconditions,
                "happy_path_outcome": s.happy_path_outcome,
                "side_effects": s.side_effects,
                "constraints": s.constraints,
                "variants": s.variants,
                "status": s.status.value,
                "created_at": s.created_at,
            }
            for s in stories
        ]

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

        stories_data = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "actor": s.actor,
                "trigger": s.trigger.value,
                "scope": s.scope,
                "preconditions": s.preconditions,
                "happy_path_outcome": s.happy_path_outcome,
                "side_effects": s.side_effects,
                "constraints": s.constraints,
                "variants": s.variants,
                "status": s.status.value,
                "created_at": s.created_at,
                "accepted_at": s.accepted_at,
            }
            for s in stories
        ]

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
