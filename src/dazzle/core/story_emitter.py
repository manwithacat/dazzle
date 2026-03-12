"""
DSL emitter for story specifications.

Converts StorySpec IR objects to DSL text for writing to .dsl files.
Used by MCP handlers (story propose, story save) and CLI commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir.stories import StorySpec


def emit_story_dsl(story: StorySpec) -> str:
    """Serialize a StorySpec to DSL text.

    Rules:
    - Omit ``status: draft`` (it's the default) to keep proposed stories clean
    - Only emit non-empty sections (skip ``given:`` if empty)
    - Strings with special characters are quoted
    """
    from dazzle.core.ir.stories import StoryStatus

    lines: list[str] = []

    # Header: story ST-001 "Title":
    lines.append(f'story {story.story_id} "{story.title}":')

    # Description (docstring-style)
    if story.description:
        lines.append(f'  "{story.description}"')

    # Status (omit if draft — it's the default)
    if story.status and story.status != StoryStatus.DRAFT:
        lines.append(f"  status: {story.status.value}")

    # Actor
    lines.append(f"  actor: {story.actor}")

    # Trigger
    lines.append(f"  trigger: {story.trigger.value}")

    # Scope
    if story.scope:
        scope_str = ", ".join(story.scope)
        lines.append(f"  scope: [{scope_str}]")

    # Given
    if story.given:
        lines.append("  given:")
        for condition in story.given:
            lines.append(f'    - "{condition.expression}"')

    # When
    if story.when:
        lines.append("  when:")
        for condition in story.when:
            lines.append(f'    - "{condition.expression}"')

    # Then
    if story.then:
        lines.append("  then:")
        for condition in story.then:
            lines.append(f'    - "{condition.expression}"')

    # Unless
    if story.unless:
        lines.append("  unless:")
        for exc in story.unless:
            lines.append(f'    - "{exc.condition}":')
            for outcome in exc.then_outcomes:
                lines.append(f'        then: "{outcome}"')

    return "\n".join(lines)


def get_next_story_id_from_appspec(stories: list[StorySpec]) -> str:
    """Determine the next story ID from an appspec's story list.

    Scans existing story IDs (e.g. ST-001, ST-002) and returns the next
    sequential ID.  Returns ``ST-001`` if no stories exist.
    """
    max_num = 0
    for story in stories:
        sid = story.story_id
        if sid.startswith("ST-"):
            try:
                num = int(sid[3:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"ST-{max_num + 1:03d}"


def append_stories_to_dsl(project_root: Path, stories: list[StorySpec]) -> Path:
    """Append story DSL blocks to ``dsl/stories.dsl``.

    Creates the file (and parent directory) if it doesn't exist.
    Returns the path to the stories DSL file.
    """
    dsl_dir = project_root / "dsl"
    dsl_dir.mkdir(parents=True, exist_ok=True)

    stories_file = dsl_dir / "stories.dsl"

    blocks = [emit_story_dsl(s) for s in stories]
    new_text = "\n\n".join(blocks) + "\n"

    if stories_file.exists():
        existing = stories_file.read_text()
        if existing and not existing.endswith("\n"):
            existing += "\n"
        stories_file.write_text(existing + "\n" + new_text)
    else:
        stories_file.write_text(new_text)

    return stories_file
