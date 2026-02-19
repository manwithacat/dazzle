"""
Story CLI commands for autonomous test generation workflow.

Commands:
- story propose: Propose stories from DSL with optional auto-accept
- story save: Save stories with status update
- story list: List stories by status
- story generate-tests: Generate test designs from accepted stories
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.cli.utils import load_project_appspec
from dazzle.core.errors import DazzleError, ParseError

story_app = typer.Typer(
    help="Story-driven test generation. Propose stories from DSL, "
    "accept them, and generate test designs.",
    no_args_is_help=True,
)


@story_app.command("propose")
def propose_stories(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    max_stories: int = typer.Option(30, "--max", help="Maximum number of stories to propose"),
    entities: str = typer.Option(
        None, "--entities", "-e", help="Comma-separated list of entities to focus on"
    ),
    auto_accept: bool = typer.Option(
        False,
        "--auto-accept",
        "-a",
        help="Automatically accept all proposed stories (for LLM agent workflows)",
    ),
    save: bool = typer.Option(
        True,
        "--save/--no-save",
        help="Save stories to dsl/stories/ (default: True)",
    ),
    output: str = typer.Option(
        None, "--output", "-o", help="Output JSON file (in addition to saving)"
    ),
) -> None:
    """
    Propose behavioural user stories from DSL.

    Analyzes DSL entities and proposes stories for:
    - Entity creation via forms
    - State machine transitions
    - CRUD operations

    Examples:
        dazzle story propose                      # Propose stories interactively
        dazzle story propose --auto-accept        # Auto-accept all (for LLM agents)
        dazzle story propose -e Task,Project      # Focus on specific entities
        dazzle story propose --max 50             # Propose up to 50 stories
    """
    from datetime import UTC, datetime

    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.stories_persistence import add_stories, get_next_story_id

    manifest_path = Path(manifest).resolve()

    try:
        root = manifest_path.parent
        appspec = load_project_appspec(root)
    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Parse entity filter
    entity_filter = None
    if entities:
        entity_filter = [e.strip() for e in entities.split(",")]

    typer.echo(f"Proposing stories for '{appspec.name}'...")

    # Get starting story ID
    base_id = get_next_story_id(root)
    base_num = int(base_id[3:])
    story_count = 0

    def next_id() -> str:
        nonlocal story_count
        result = f"ST-{base_num + story_count:03d}"
        story_count += 1
        return result

    now = datetime.now(UTC).isoformat()

    # Default persona
    default_actor = "User"
    if appspec.personas:
        default_actor = appspec.personas[0].label or appspec.personas[0].id

    stories: list[StorySpec] = []

    # Generate stories from entities
    for entity in appspec.domain.entities:
        if entity_filter and entity.name not in entity_filter:
            continue

        if story_count >= max_stories:
            break

        actor = default_actor

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
                constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][:3],
                variants=["Validation error on required field"],
                status=StoryStatus.ACCEPTED if auto_accept else StoryStatus.DRAFT,
                created_at=now,
                accepted_at=now if auto_accept else None,
            )
        )

        # Story: State machine transitions
        if entity.state_machine and story_count < max_stories:
            sm = entity.state_machine
            for transition in sm.transitions[:3]:
                if story_count >= max_stories:
                    break

                stories.append(
                    StorySpec(
                        story_id=next_id(),
                        title=(
                            f"{actor} changes {entity.name} "
                            f"from {transition.from_state} to {transition.to_state}"
                        ),
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
                        status=StoryStatus.ACCEPTED if auto_accept else StoryStatus.DRAFT,
                        created_at=now,
                        accepted_at=now if auto_accept else None,
                    )
                )

    # Display results
    typer.echo()
    typer.secho(f"Proposed {len(stories)} stories:", bold=True)

    for story in stories[:10]:
        status_color = (
            typer.colors.GREEN if story.status == StoryStatus.ACCEPTED else typer.colors.YELLOW
        )
        typer.echo(f"  {story.story_id}: {story.title}")
        typer.secho(f"    Status: {story.status.value}", fg=status_color)

    if len(stories) > 10:
        typer.echo(f"  ... and {len(stories) - 10} more")

    # Save stories
    if save:
        all_stories = add_stories(root, stories, overwrite=False)
        typer.echo()
        typer.secho(f"Saved {len(stories)} stories to dsl/stories/", fg=typer.colors.GREEN)
        typer.echo(f"Total stories in project: {len(all_stories)}")

    # Output JSON if requested
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        stories_data = [
            {
                "story_id": s.story_id,
                "title": s.title,
                "actor": s.actor,
                "trigger": s.trigger.value,
                "scope": s.scope,
                "preconditions": s.preconditions,
                "happy_path_outcome": s.happy_path_outcome,
                "status": s.status.value,
            }
            for s in stories
        ]

        output_path.write_text(json.dumps({"stories": stories_data}, indent=2))
        typer.echo(f"JSON output saved to {output_path}")

    # Guidance for next steps
    typer.echo()
    if auto_accept:
        typer.echo("Next steps:")
        typer.echo("  1. dazzle story generate-tests    # Generate test designs from stories")
        typer.echo("  2. dazzle test dsl-run            # Run generated tests")
    else:
        typer.echo("Next steps:")
        typer.echo("  1. Review stories in dsl/stories/stories.json")
        typer.echo("  2. Change status to 'accepted' for stories you want to test")
        typer.echo("  3. dazzle story generate-tests    # Generate test designs")


@story_app.command("list")
def list_stories(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    status: str = typer.Option(
        "all",
        "--status",
        "-s",
        help="Filter by status: all, draft, accepted, rejected",
    ),
) -> None:
    """
    List stories by status.

    Examples:
        dazzle story list                    # List all stories
        dazzle story list --status accepted  # List accepted stories only
    """
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    # Parse status filter
    status_filter = None
    if status != "all":
        try:
            status_filter = StoryStatus(status)
        except ValueError:
            typer.echo(f"Invalid status: {status}", err=True)
            typer.echo("Valid statuses: draft, accepted, rejected", err=True)
            raise typer.Exit(code=1)

    stories = get_stories_by_status(root, status_filter)

    if not stories:
        typer.echo(f"No stories found (filter: {status})")
        return

    typer.secho(f"Stories ({len(stories)} total):", bold=True)
    typer.echo()

    status_colors = {
        "draft": typer.colors.YELLOW,
        "accepted": typer.colors.GREEN,
        "rejected": typer.colors.RED,
    }

    for story in stories:
        color = status_colors.get(story.status.value, typer.colors.WHITE)
        typer.echo(f"  {story.story_id}: {story.title}")
        typer.secho(f"    Status: {story.status.value}", fg=color)
        typer.echo(f"    Scope: {', '.join(story.scope)}")


@story_app.command("generate-tests")
def generate_tests(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    include_draft: bool = typer.Option(
        False,
        "--include-draft",
        help="Include draft stories (not just accepted)",
    ),
    save: bool = typer.Option(
        True,
        "--save/--no-save",
        help="Save test designs to dsl/tests/",
    ),
    output: str = typer.Option(None, "--output", "-o", help="Output JSON file"),
) -> None:
    """
    Generate test designs from accepted stories.

    Converts behavioural stories into executable test designs that can be
    run with `dazzle test dsl-run`.

    Examples:
        dazzle story generate-tests                 # From accepted stories
        dazzle story generate-tests --include-draft # Include drafts too
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
    from dazzle.testing.test_design_persistence import add_test_designs

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    # Get stories to convert
    stories = get_stories_by_status(root, StoryStatus.ACCEPTED)

    if include_draft:
        draft_stories = get_stories_by_status(root, StoryStatus.DRAFT)
        stories = list(stories) + list(draft_stories)

    if not stories:
        typer.echo("No stories found to convert.")
        typer.echo("Use 'dazzle story propose --auto-accept' to create stories.")
        return

    typer.echo(f"Generating test designs from {len(stories)} stories...")

    # Trigger mapping
    trigger_map = {
        StoryTrigger.FORM_SUBMITTED: TestDesignTrigger.FORM_SUBMITTED,
        StoryTrigger.STATUS_CHANGED: TestDesignTrigger.STATUS_CHANGED,
        StoryTrigger.USER_CLICK: TestDesignTrigger.USER_CLICK,
    }

    test_designs: list[TestDesignSpec] = []

    for story in stories:
        test_id = story.story_id.replace("ST-", "TD-")

        steps: list[TestDesignStep] = []

        # Step 1: Login as the actor
        steps.append(
            TestDesignStep(
                action=TestDesignAction.LOGIN_AS,
                target=story.actor,
                rationale=f"Test from {story.actor}'s perspective",
            )
        )

        # Step 2: Infer action from trigger
        if story.trigger == StoryTrigger.FORM_SUBMITTED:
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

        test_designs.append(
            TestDesignSpec(
                test_id=test_id,
                title=f"Verify: {story.title}",
                description=f"Test generated from story {story.story_id}",
                persona=story.actor,
                trigger=trigger_map.get(story.trigger, TestDesignTrigger.USER_CLICK),
                steps=steps,
                expected_outcomes=story.happy_path_outcome.copy(),
                entities=story.scope.copy(),
                tags=[f"story:{story.story_id}", "auto-generated"],
                status=TestDesignStatus.PROPOSED,
            )
        )

    typer.secho(f"Generated {len(test_designs)} test designs:", bold=True)

    for td in test_designs[:10]:
        typer.echo(f"  {td.test_id}: {td.title}")

    if len(test_designs) > 10:
        typer.echo(f"  ... and {len(test_designs) - 10} more")

    # Save test designs
    if save:
        add_test_designs(root, test_designs, overwrite=False, to_dsl=True)
        typer.echo()
        typer.secho("Test designs saved to dsl/tests/designs.json", fg=typer.colors.GREEN)

    # Output JSON if requested
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        designs_data = [
            {
                "test_id": td.test_id,
                "title": td.title,
                "persona": td.persona,
                "steps": len(td.steps),
                "status": td.status.value,
            }
            for td in test_designs
        ]

        output_path.write_text(json.dumps({"test_designs": designs_data}, indent=2))
        typer.echo(f"JSON output saved to {output_path}")

    typer.echo()
    typer.echo("Next steps:")
    typer.echo("  dazzle test dsl-run    # Run the generated tests")
