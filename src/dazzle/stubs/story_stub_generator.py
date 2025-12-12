"""
Story stub generator for DAZZLE Behaviour Layer.

Generates Python service stubs from accepted stories. Each stub contains
the story contract as a docstring with preconditions, outcomes, and constraints.
"""

from __future__ import annotations

from textwrap import dedent

from dazzle.core.ir.stories import StorySpec


def generate_story_stub(story: StorySpec) -> str:
    """Generate a Python function stub for a single story.

    The stub includes:
    - Function name derived from story_id
    - Complete docstring with story contract
    - NotImplementedError placeholder

    Args:
        story: The story specification to generate a stub for.

    Returns:
        Python function code as a string.
    """
    # Convert story_id to function name (ST-001 -> handle_st_001)
    func_name = f"handle_{story.story_id.lower().replace('-', '_')}"

    # Build docstring lines
    lines = []

    # Title and basic info
    lines.append(f"Story {story.story_id}: {story.title}")
    lines.append("")
    lines.append(f"Actor: {story.actor}")
    lines.append(f"Trigger: {story.trigger.value}")

    if story.scope:
        lines.append(f"Scope: {', '.join(story.scope)}")

    # Preconditions
    if story.preconditions:
        lines.append("")
        lines.append("Preconditions:")
        for p in story.preconditions:
            lines.append(f"    - {p}")

    # Happy path outcome
    if story.happy_path_outcome:
        lines.append("")
        lines.append("Happy Path Outcome:")
        for o in story.happy_path_outcome:
            lines.append(f"    - {o}")

    # Side effects
    if story.side_effects:
        lines.append("")
        lines.append("Side Effects:")
        for e in story.side_effects:
            lines.append(f"    - {e}")

    # Constraints
    if story.constraints:
        lines.append("")
        lines.append("Constraints:")
        for c in story.constraints:
            lines.append(f"    - {c}")

    # Variants
    if story.variants:
        lines.append("")
        lines.append("Variants:")
        for v in story.variants:
            lines.append(f"    - {v}")

    # Format the docstring with proper indentation
    docstring_body = "\n    ".join(lines)

    # Generate the function
    stub = f'''def {func_name}(context: Context) -> None:
    """
    {docstring_body}
    """
    # TODO: Implement according to the above contract
    raise NotImplementedError("{story.story_id} not implemented yet")
'''

    return stub.strip()


def generate_story_stubs_file(stories: list[StorySpec]) -> str:
    """Generate a complete Python module with all story handlers.

    Args:
        stories: List of story specifications to generate stubs for.

    Returns:
        Complete Python module code as a string.
    """
    header = dedent('''
        """
        Story handlers generated from DAZZLE Behaviour Layer.

        This file contains stub implementations for accepted stories.
        Each function represents a behavioural user story with its
        contract documented in the docstring.

        To implement a story:
        1. Read the docstring to understand the contract
        2. Replace the NotImplementedError with your implementation
        3. Ensure all preconditions are checked
        4. Ensure all outcomes are achieved
        5. Honor all constraints

        AUTO-GENERATED - Edit implementations but don't change function signatures.
        """

        from __future__ import annotations

        from dataclasses import dataclass
        from typing import Any


        @dataclass
        class Context:
            """Execution context for story handlers.

            Attributes:
                actor: The persona executing this story
                entity: Primary entity being operated on
                data: Entity data or form submission data
                trigger_event: The event that triggered this story
                db: Database session or repository
                services: External service dependencies
            """

            actor: str
            entity: str
            data: dict[str, Any]
            trigger_event: str
            db: Any = None
            services: dict[str, Any] | None = None


    ''').strip()

    # Generate all stubs
    stubs = [generate_story_stub(story) for story in stories]

    # Combine into module
    return header + "\n\n\n" + "\n\n\n".join(stubs) + "\n"
