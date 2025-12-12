"""
Unit tests for DAZZLE Behaviour Layer stories.

Tests the Story IR types, persistence layer, and stub generation.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from dazzle.core.ir.stories import (
    StoriesContainer,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.stories_persistence import (
    add_stories,
    get_next_story_id,
    get_stories_by_status,
    get_stories_file,
    load_stories,
    save_stories,
    update_story_status,
)
from dazzle.stubs.story_stub_generator import (
    generate_story_stub,
    generate_story_stubs_file,
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


class TestStoryStubGenerator:
    """Tests for story stub generation."""

    def test_generate_minimal_stub(self):
        """Test generating a stub for a minimal story."""
        story = StorySpec(
            story_id="ST-001",
            title="User creates a task",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )

        stub = generate_story_stub(story)

        assert "def handle_st_001(context: Context)" in stub
        assert "Story ST-001: User creates a task" in stub
        assert "Actor: User" in stub
        assert "Trigger: form_submitted" in stub
        assert 'raise NotImplementedError("ST-001 not implemented yet")' in stub

    def test_generate_full_stub(self):
        """Test generating a stub with all sections."""
        story = StorySpec(
            story_id="ST-002",
            title="Staff sends invoice",
            actor="StaffUser",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Invoice", "Client"],
            preconditions=["Invoice is Draft"],
            happy_path_outcome=["Invoice becomes Sent"],
            side_effects=["send_email"],
            constraints=["Cannot send twice"],
            variants=["Email missing"],
        )

        stub = generate_story_stub(story)

        assert "Scope: Invoice, Client" in stub
        assert "Preconditions:" in stub
        assert "- Invoice is Draft" in stub
        assert "Happy Path Outcome:" in stub
        assert "- Invoice becomes Sent" in stub
        assert "Side Effects:" in stub
        assert "- send_email" in stub
        assert "Constraints:" in stub
        assert "- Cannot send twice" in stub
        assert "Variants:" in stub
        assert "- Email missing" in stub

    def test_generate_stubs_file(self):
        """Test generating a complete stubs file."""
        stories = [
            StorySpec(
                story_id="ST-001",
                title="Create task",
                actor="User",
                trigger=StoryTrigger.FORM_SUBMITTED,
            ),
            StorySpec(
                story_id="ST-002",
                title="Complete task",
                actor="User",
                trigger=StoryTrigger.STATUS_CHANGED,
            ),
        ]

        code = generate_story_stubs_file(stories)

        # Check header
        assert "Story handlers generated from DAZZLE Behaviour Layer" in code
        assert "AUTO-GENERATED" in code
        assert "from __future__ import annotations" in code
        assert "class Context:" in code

        # Check both stubs
        assert "def handle_st_001" in code
        assert "def handle_st_002" in code

    def test_stub_function_name_format(self):
        """Test that function names are correctly formatted."""
        story = StorySpec(
            story_id="ST-123",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        stub = generate_story_stub(story)

        assert "def handle_st_123(context: Context)" in stub

    def test_stub_is_valid_python(self):
        """Test that generated stubs are valid Python."""
        story = StorySpec(
            story_id="ST-001",
            title="Test with 'quotes' and special chars",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            preconditions=["Condition with 'quotes'"],
        )

        code = generate_story_stubs_file([story])

        # Should compile without errors
        compile(code, "<test>", "exec")
