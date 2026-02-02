"""
Stories persistence layer for DAZZLE Behaviour Layer.

Handles reading and writing story specifications to the .dazzle/stories/
directory. Stories are stored as JSON for easy inspection and editing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ir.stories import StoriesContainer, StorySpec, StoryStatus

STORIES_DIR = ".dazzle/stories"
SEEDS_STORIES_DIR = "dsl/seeds/stories"
STORIES_FILE = "stories.json"


def get_stories_dir(project_root: Path) -> Path:
    """Get the .dazzle/stories/ directory path (runtime location).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the stories directory.
    """
    return project_root / STORIES_DIR


def get_seeds_stories_dir(project_root: Path) -> Path:
    """Get the dsl/seeds/stories/ directory path (checked-in fallback).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the seeds stories directory.
    """
    return project_root / SEEDS_STORIES_DIR


def get_stories_file(project_root: Path) -> Path:
    """Get the stories.json file path (runtime location).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to the stories.json file.
    """
    return get_stories_dir(project_root) / STORIES_FILE


def _find_stories_file(project_root: Path) -> Path | None:
    """Find the stories.json file, checking runtime then seeds.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Path to existing stories.json, or None if not found.
    """
    # Check runtime location first (.dazzle/stories/)
    runtime_file = get_stories_dir(project_root) / STORIES_FILE
    if runtime_file.exists():
        return runtime_file

    # Fall back to seeds location (dsl/seeds/stories/)
    seeds_file = get_seeds_stories_dir(project_root) / STORIES_FILE
    if seeds_file.exists():
        return seeds_file

    return None


def load_story_index(project_root: Path) -> list[dict[str, Any]]:
    """Load lightweight story summaries without full Pydantic validation.

    Returns only the fields needed for coverage analysis and listing,
    avoiding the cost of deserializing all 20+ StorySpec fields.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        List of dicts with keys: story_id, title, actor, scope, status,
        then, unless (raw lists for coverage analysis).
    """
    import logging

    stories_file = _find_stories_file(project_root)
    if stories_file is None:
        return []

    try:
        content = stories_file.read_text(encoding="utf-8")
        data = json.loads(content)
        raw_stories = data.get("stories", [])
        return [
            {
                "story_id": s.get("story_id", ""),
                "title": s.get("title", ""),
                "actor": s.get("actor", ""),
                "scope": s.get("scope", []),
                "status": s.get("status", "draft"),
                "then": s.get("then", []),
                "happy_path_outcome": s.get("happy_path_outcome", []),
                "unless": s.get("unless", []),
            }
            for s in raw_stories
        ]
    except (json.JSONDecodeError, ValueError) as e:
        logging.getLogger(__name__).warning(f"Failed to load story index from {stories_file}: {e}")
        return []


def load_stories(project_root: Path) -> list[StorySpec]:
    """Load all stories from .dazzle/stories/ or dsl/seeds/stories/.

    Checks the runtime location (.dazzle/stories/) first, then falls
    back to the checked-in seeds location (dsl/seeds/stories/).

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        List of story specifications. Returns empty list if file doesn't exist.
    """
    stories_file = _find_stories_file(project_root)

    if stories_file is None:
        return []

    try:
        content = stories_file.read_text(encoding="utf-8")
        data = json.loads(content)
        container = StoriesContainer.model_validate(data)
        return list(container.stories)
    except (json.JSONDecodeError, ValueError) as e:
        # Log error but return empty list to avoid breaking workflows
        import logging

        logging.getLogger(__name__).warning(f"Failed to load stories from {stories_file}: {e}")
        return []


def save_stories(
    project_root: Path,
    stories: list[StorySpec],
    *,
    version: str = "1.0",
) -> Path:
    """Save stories to .dazzle/stories/stories.json.

    Args:
        project_root: Root directory of the DAZZLE project.
        stories: List of story specifications to save.
        version: Schema version string.

    Returns:
        Path to the saved stories.json file.
    """
    stories_dir = get_stories_dir(project_root)
    stories_dir.mkdir(parents=True, exist_ok=True)

    container = StoriesContainer(version=version, stories=stories)

    stories_file = get_stories_file(project_root)
    stories_file.write_text(
        json.dumps(
            container.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return stories_file


def get_next_story_id(project_root: Path) -> str:
    """Generate the next story ID (ST-001, ST-002, etc.).

    Examines existing stories to find the highest ID and returns
    the next sequential ID.

    Args:
        project_root: Root directory of the DAZZLE project.

    Returns:
        Next story ID in format ST-XXX.
    """
    existing = load_stories(project_root)

    if not existing:
        return "ST-001"

    # Extract numeric parts from story IDs
    max_num = 0
    for story in existing:
        if story.story_id.startswith("ST-"):
            try:
                num = int(story.story_id[3:])
                max_num = max(max_num, num)
            except ValueError:
                continue

    return f"ST-{max_num + 1:03d}"


def get_stories_by_status(
    project_root: Path,
    status: StoryStatus | None = None,
) -> list[StorySpec]:
    """Get stories filtered by status.

    Args:
        project_root: Root directory of the DAZZLE project.
        status: Filter by this status. None returns all stories.

    Returns:
        List of matching stories.
    """
    stories = load_stories(project_root)

    if status is None:
        return stories

    return [s for s in stories if s.status == status]


def update_story_status(
    project_root: Path,
    story_id: str,
    new_status: StoryStatus,
) -> StorySpec | None:
    """Update the status of a story.

    Args:
        project_root: Root directory of the DAZZLE project.
        story_id: ID of the story to update.
        new_status: New status to set.

    Returns:
        Updated story spec, or None if story not found.
    """
    stories = load_stories(project_root)

    updated_stories = []
    updated_story = None

    for story in stories:
        if story.story_id == story_id:
            accepted_at = None
            if new_status == StoryStatus.ACCEPTED:
                accepted_at = datetime.now(UTC).isoformat()

            updated_story = story.with_status(new_status, accepted_at=accepted_at)
            updated_stories.append(updated_story)
        else:
            updated_stories.append(story)

    if updated_story is not None:
        save_stories(project_root, updated_stories)

    return updated_story


def add_stories(
    project_root: Path,
    new_stories: list[StorySpec],
    *,
    overwrite: bool = False,
) -> list[StorySpec]:
    """Add new stories, optionally overwriting existing ones.

    Args:
        project_root: Root directory of the DAZZLE project.
        new_stories: Stories to add.
        overwrite: If True, replace stories with matching IDs.
            If False, skip stories that already exist.

    Returns:
        List of all stories after the operation.
    """
    existing = load_stories(project_root)
    existing_ids = {s.story_id for s in existing}

    if overwrite:
        # Remove existing stories that will be replaced
        new_ids = {s.story_id for s in new_stories}
        existing = [s for s in existing if s.story_id not in new_ids]
        existing.extend(new_stories)
    else:
        # Only add stories that don't already exist
        for story in new_stories:
            if story.story_id not in existing_ids:
                existing.append(story)
                existing_ids.add(story.story_id)

    save_stories(project_root, existing)
    return existing
