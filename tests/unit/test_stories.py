"""
Unit tests for DAZZLE Behaviour Layer stories.

Tests the Story IR types, persistence layer, and stub generation.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Pre-mock the mcp SDK package so dazzle.mcp.server can be imported
# without the mcp package being installed.
for _mod in ("mcp", "mcp.server", "mcp.server.fastmcp", "mcp.server.stdio", "mcp.types"):
    sys.modules.setdefault(_mod, MagicMock(pytest_plugins=[]))

from dazzle.core.ir.stories import (  # noqa: E402
    StoriesContainer,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.stories_persistence import (  # noqa: E402
    add_stories,
    get_next_story_id,
    get_stories_by_status,
    get_stories_file,
    load_stories,
    save_stories,
    update_story_status,
)


class TestStorySpec:
    """Tests for StorySpec IR type."""

    def test_create_minimal_story(self):
        """Test creating a story with minimal required fields."""
        story = StorySpec(
            story_id="ST-001",
            title="User creates a task",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )

        assert story.story_id == "ST-001"
        assert story.title == "User creates a task"
        assert story.actor == "User"
        assert story.trigger == StoryTrigger.FORM_SUBMITTED
        assert story.status == StoryStatus.DRAFT
        assert story.scope == []
        assert story.preconditions == []

    def test_create_full_story(self):
        """Test creating a story with all fields."""
        story = StorySpec(
            story_id="ST-002",
            title="Staff sends an invoice",
            actor="StaffUser",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Invoice", "Client"],
            preconditions=["Invoice.status is 'Draft'"],
            happy_path_outcome=["Invoice.status becomes 'Sent'"],
            side_effects=["send_invoice_email"],
            constraints=["Cannot send if already sent"],
            variants=["Client email missing"],
            status=StoryStatus.ACCEPTED,
            created_at="2025-12-12T00:00:00Z",
            accepted_at="2025-12-12T01:00:00Z",
        )

        assert story.story_id == "ST-002"
        assert story.scope == ["Invoice", "Client"]
        assert len(story.preconditions) == 1
        assert len(story.happy_path_outcome) == 1
        assert len(story.side_effects) == 1
        assert story.status == StoryStatus.ACCEPTED
        assert story.accepted_at == "2025-12-12T01:00:00Z"

    def test_story_is_frozen(self):
        """Test that StorySpec is immutable."""
        from pydantic import ValidationError

        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        with pytest.raises(ValidationError):
            story.title = "Changed"

    def test_story_with_status(self):
        """Test with_status creates new story with updated status."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            status=StoryStatus.DRAFT,
        )

        accepted = story.with_status(StoryStatus.ACCEPTED, "2025-12-12T00:00:00Z")

        assert story.status == StoryStatus.DRAFT  # Original unchanged
        assert accepted.status == StoryStatus.ACCEPTED
        assert accepted.accepted_at == "2025-12-12T00:00:00Z"
        assert accepted.story_id == story.story_id

    def test_all_triggers(self):
        """Test all trigger types are valid."""
        triggers = [
            StoryTrigger.FORM_SUBMITTED,
            StoryTrigger.STATUS_CHANGED,
            StoryTrigger.TIMER_ELAPSED,
            StoryTrigger.EXTERNAL_EVENT,
            StoryTrigger.USER_CLICK,
            StoryTrigger.CRON_DAILY,
            StoryTrigger.CRON_HOURLY,
        ]

        for trigger in triggers:
            story = StorySpec(
                story_id="ST-001",
                title="Test",
                actor="User",
                trigger=trigger,
            )
            assert story.trigger == trigger


class TestStoriesContainer:
    """Tests for StoriesContainer."""

    def test_empty_container(self):
        """Test creating an empty container."""
        container = StoriesContainer()

        assert container.version == "1.0"
        assert container.stories == []

    def test_container_with_stories(self):
        """Test container with stories."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        container = StoriesContainer(stories=[story])

        assert len(container.stories) == 1
        assert container.stories[0].story_id == "ST-001"


class TestStoriesPersistence:
    """Tests for stories persistence layer."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_load_nonexistent_stories(self, temp_project):
        """Test loading from a project with no stories file."""
        stories = load_stories(temp_project)
        assert stories == []

    def test_save_and_load_stories(self, temp_project):
        """Test saving and loading stories."""
        story = StorySpec(
            story_id="ST-001",
            title="Test story",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task"],
            status=StoryStatus.DRAFT,
        )

        # Save
        save_stories(temp_project, [story])

        # Verify file exists
        stories_file = get_stories_file(temp_project)
        assert stories_file.exists()

        # Load and verify
        loaded = load_stories(temp_project)
        assert len(loaded) == 1
        assert loaded[0].story_id == "ST-001"
        assert loaded[0].title == "Test story"
        assert loaded[0].scope == ["Task"]

    def test_save_multiple_stories(self, temp_project):
        """Test saving multiple stories."""
        stories = [
            StorySpec(
                story_id=f"ST-{i:03d}",
                title=f"Story {i}",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
            )
            for i in range(1, 6)
        ]

        save_stories(temp_project, stories)
        loaded = load_stories(temp_project)

        assert len(loaded) == 5
        assert loaded[0].story_id == "ST-001"
        assert loaded[4].story_id == "ST-005"

    def test_get_next_story_id_empty(self, temp_project):
        """Test getting next story ID with no existing stories."""
        next_id = get_next_story_id(temp_project)
        assert next_id == "ST-001"

    def test_get_next_story_id_with_existing(self, temp_project):
        """Test getting next story ID with existing stories."""
        stories = [
            StorySpec(
                story_id="ST-003",
                title="Story 3",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
            ),
            StorySpec(
                story_id="ST-007",
                title="Story 7",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
            ),
        ]
        save_stories(temp_project, stories)

        next_id = get_next_story_id(temp_project)
        assert next_id == "ST-008"

    def test_get_stories_by_status(self, temp_project):
        """Test filtering stories by status."""
        stories = [
            StorySpec(
                story_id="ST-001",
                title="Draft",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
                status=StoryStatus.DRAFT,
            ),
            StorySpec(
                story_id="ST-002",
                title="Accepted",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
                status=StoryStatus.ACCEPTED,
            ),
            StorySpec(
                story_id="ST-003",
                title="Rejected",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
                status=StoryStatus.REJECTED,
            ),
        ]
        save_stories(temp_project, stories)

        drafts = get_stories_by_status(temp_project, StoryStatus.DRAFT)
        assert len(drafts) == 1
        assert drafts[0].story_id == "ST-001"

        accepted = get_stories_by_status(temp_project, StoryStatus.ACCEPTED)
        assert len(accepted) == 1
        assert accepted[0].story_id == "ST-002"

        all_stories = get_stories_by_status(temp_project, None)
        assert len(all_stories) == 3

    def test_update_story_status(self, temp_project):
        """Test updating story status."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            status=StoryStatus.DRAFT,
        )
        save_stories(temp_project, [story])

        # Update to accepted
        updated = update_story_status(temp_project, "ST-001", StoryStatus.ACCEPTED)

        assert updated is not None
        assert updated.status == StoryStatus.ACCEPTED
        assert updated.accepted_at is not None

        # Verify persisted
        loaded = load_stories(temp_project)
        assert loaded[0].status == StoryStatus.ACCEPTED

    def test_update_nonexistent_story(self, temp_project):
        """Test updating a story that doesn't exist."""
        result = update_story_status(temp_project, "ST-999", StoryStatus.ACCEPTED)
        assert result is None

    def test_add_stories_no_overwrite(self, temp_project):
        """Test adding stories without overwriting."""
        story1 = StorySpec(
            story_id="ST-001",
            title="Original",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )
        save_stories(temp_project, [story1])

        story2 = StorySpec(
            story_id="ST-001",
            title="Duplicate",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )
        story3 = StorySpec(
            story_id="ST-002",
            title="New",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        result = add_stories(temp_project, [story2, story3], overwrite=False)

        assert len(result) == 2
        # Original should be kept
        assert result[0].title == "Original"
        assert result[1].title == "New"

    def test_add_stories_with_overwrite(self, temp_project):
        """Test adding stories with overwrite."""
        story1 = StorySpec(
            story_id="ST-001",
            title="Original",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )
        save_stories(temp_project, [story1])

        story2 = StorySpec(
            story_id="ST-001",
            title="Updated",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        result = add_stories(temp_project, [story2], overwrite=True)

        assert len(result) == 1
        assert result[0].title == "Updated"

    def test_stories_json_format(self, temp_project):
        """Test that stories are saved in correct JSON format."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
            status=StoryStatus.ACCEPTED,
        )
        save_stories(temp_project, [story])

        stories_file = get_stories_file(temp_project)
        content = json.loads(stories_file.read_text())

        assert content["version"] == "1.0"
        assert len(content["stories"]) == 1
        assert content["stories"][0]["story_id"] == "ST-001"
        assert content["stories"][0]["trigger"] == "form_submitted"
        assert content["stories"][0]["status"] == "accepted"


class TestGenerateTestsFromStories:
    """Tests for story-to-test generation."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_generate_tests_no_stories(self, temp_project):
        """Test generating tests with no stories."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        result = generate_tests_from_stories_handler(temp_project, {})
        data = json.loads(result)

        assert data["status"] == "no_stories"

    def test_generate_tests_from_accepted_story(self, temp_project):
        """Test generating tests from an accepted story."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        # Create an accepted story
        story = StorySpec(
            story_id="ST-001",
            title="User creates a task",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task"],
            preconditions=["User is logged in"],
            happy_path_outcome=["Task is saved", "User sees confirmation"],
            status=StoryStatus.ACCEPTED,
        )
        save_stories(temp_project, [story])

        result = generate_tests_from_stories_handler(temp_project, {})
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["count"] == 1
        assert len(data["test_designs"]) == 1

        test = data["test_designs"][0]
        assert test["test_id"] == "TD-001"  # ST -> TD conversion
        assert test["persona"] == "User"
        assert test["status"] == "proposed"
        # Summaries don't include full fields like steps/entities
        assert "steps" not in test

    def test_generate_tests_filters_draft(self, temp_project):
        """Test that draft stories are excluded by default."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        # Create one accepted and one draft story
        stories = [
            StorySpec(
                story_id="ST-001",
                title="Accepted story",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
                status=StoryStatus.ACCEPTED,
            ),
            StorySpec(
                story_id="ST-002",
                title="Draft story",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
                status=StoryStatus.DRAFT,
            ),
        ]
        save_stories(temp_project, stories)

        result = generate_tests_from_stories_handler(temp_project, {})
        data = json.loads(result)

        assert data["count"] == 1
        assert data["test_designs"][0]["test_id"] == "TD-001"

    def test_generate_tests_include_draft(self, temp_project):
        """Test including draft stories."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        stories = [
            StorySpec(
                story_id="ST-001",
                title="Accepted story",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
                status=StoryStatus.ACCEPTED,
            ),
            StorySpec(
                story_id="ST-002",
                title="Draft story",
                actor="Admin",
                trigger=StoryTrigger.USER_CLICK,
                status=StoryStatus.DRAFT,
            ),
        ]
        save_stories(temp_project, stories)

        result = generate_tests_from_stories_handler(temp_project, {"include_draft": True})
        data = json.loads(result)

        assert data["count"] == 2
        test_ids = [t["test_id"] for t in data["test_designs"]]
        assert "TD-001" in test_ids
        assert "TD-002" in test_ids

    def test_generate_tests_filter_by_story_ids(self, temp_project):
        """Test filtering by specific story IDs."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        stories = [
            StorySpec(
                story_id="ST-001",
                title="Story 1",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
                status=StoryStatus.ACCEPTED,
            ),
            StorySpec(
                story_id="ST-002",
                title="Story 2",
                actor="Admin",
                trigger=StoryTrigger.STATUS_CHANGED,
                status=StoryStatus.ACCEPTED,
            ),
            StorySpec(
                story_id="ST-003",
                title="Story 3",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
                status=StoryStatus.ACCEPTED,
            ),
        ]
        save_stories(temp_project, stories)

        result = generate_tests_from_stories_handler(
            temp_project, {"story_ids": ["ST-001", "ST-003"]}
        )
        data = json.loads(result)

        assert data["count"] == 2
        test_ids = [t["test_id"] for t in data["test_designs"]]
        assert "TD-001" in test_ids
        assert "TD-003" in test_ids
        assert "TD-002" not in test_ids

    def test_generate_tests_returns_summaries(self, temp_project):
        """Test that generate_tests returns compact summaries, not full objects."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler

        story = StorySpec(
            story_id="ST-001",
            title="User completes a task",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Task"],
            preconditions=["Task.status is 'pending'"],
            happy_path_outcome=["Task.status becomes 'completed'"],
            status=StoryStatus.ACCEPTED,
        )
        save_stories(temp_project, [story])

        result = generate_tests_from_stories_handler(temp_project, {})
        data = json.loads(result)

        assert data["count"] == 1
        test = data["test_designs"][0]
        # Summary fields present
        assert test["test_id"] == "TD-001"
        assert test["persona"] == "User"
        assert test["status"] == "proposed"
        # Full fields absent in summary
        assert "steps" not in test
        assert "expected_outcomes" not in test

    def test_generate_tests_auto_saves(self, temp_project):
        """Test that generate_tests auto-saves designs to persistence."""
        from dazzle.mcp.server.handlers.stories import generate_tests_from_stories_handler
        from dazzle.testing.test_design_persistence import get_test_designs_by_status

        story = StorySpec(
            story_id="ST-001",
            title="Admin creates a user",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
            status=StoryStatus.ACCEPTED,
        )
        save_stories(temp_project, [story])

        generate_tests_from_stories_handler(temp_project, {})

        # Verify designs were persisted
        designs = get_test_designs_by_status(temp_project, None)
        assert len(designs) >= 1
        assert designs[0].test_id == "TD-001"
