"""
Unit tests for DAZZLE Behaviour Layer stories.

Tests the Story IR types and DSL story emitter.
"""

import tempfile
from pathlib import Path

import pytest

from dazzle.core.ir.stories import (
    StoryCondition,
    StoryException,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.story_emitter import (
    append_stories_to_dsl,
    emit_story_dsl,
    get_next_story_id_from_appspec,
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
        assert story.given == []

    def test_create_full_story(self):
        """Test creating a story with all Gherkin fields."""
        story = StorySpec(
            story_id="ST-002",
            title="Staff sends an invoice",
            actor="StaffUser",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Invoice", "Client"],
            given=[StoryCondition(expression="Invoice.status is 'Draft'")],
            when=[StoryCondition(expression="Invoice.status changes to 'Sent'")],
            then=[StoryCondition(expression="Invoice.status becomes 'Sent'")],
            unless=[
                StoryException(
                    condition="Client.email is missing",
                    then_outcomes=["FollowupTask is created"],
                )
            ],
            status=StoryStatus.ACCEPTED,
        )

        assert story.story_id == "ST-002"
        assert story.scope == ["Invoice", "Client"]
        assert len(story.given) == 1
        assert len(story.then) == 1
        assert len(story.unless) == 1
        assert story.status == StoryStatus.ACCEPTED

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


class TestStoryCondition:
    """Tests for StoryCondition."""

    def test_expression_only(self):
        """Test condition with expression only."""
        cond = StoryCondition(expression="Task.status is 'pending'")
        assert cond.expression == "Task.status is 'pending'"
        assert cond.field_path is None

    def test_with_field_path(self):
        """Test condition with field_path."""
        cond = StoryCondition(expression="Invoice.status is 'draft'", field_path="Invoice.status")
        assert cond.field_path == "Invoice.status"


class TestStoryException:
    """Tests for StoryException."""

    def test_basic_exception(self):
        """Test basic exception with outcomes."""
        exc = StoryException(
            condition="Client.email is missing",
            then_outcomes=["FollowupTask is created"],
        )
        assert exc.condition == "Client.email is missing"
        assert exc.then_outcomes == ["FollowupTask is created"]


class TestEmitStoryDsl:
    """Tests for emit_story_dsl."""

    def test_minimal_story(self):
        """Test emitting a minimal story."""
        story = StorySpec(
            story_id="ST-001",
            title="User creates a task",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )

        dsl = emit_story_dsl(story)

        assert 'story ST-001 "User creates a task":' in dsl
        assert "  actor: User" in dsl
        assert "  trigger: form_submitted" in dsl
        # Draft status should be omitted
        assert "status:" not in dsl

    def test_accepted_status_emitted(self):
        """Test that non-draft status is emitted."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            status=StoryStatus.ACCEPTED,
        )

        dsl = emit_story_dsl(story)

        assert "  status: accepted" in dsl

    def test_gherkin_fields(self):
        """Test emitting given/when/then."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Task"],
            given=[StoryCondition(expression="Task.status is 'pending'")],
            when=[StoryCondition(expression="Task.status changes to 'done'")],
            then=[StoryCondition(expression="Task is completed")],
        )

        dsl = emit_story_dsl(story)

        assert "  given:" in dsl
        assert "    - \"Task.status is 'pending'\"" in dsl
        assert "  when:" in dsl
        assert "  then:" in dsl

    def test_unless_emitted(self):
        """Test emitting unless blocks."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            unless=[
                StoryException(
                    condition="Client.email is missing",
                    then_outcomes=["FollowupTask is created"],
                )
            ],
        )

        dsl = emit_story_dsl(story)

        assert "  unless:" in dsl
        assert '    - "Client.email is missing":' in dsl
        assert '        then: "FollowupTask is created"' in dsl

    def test_empty_sections_omitted(self):
        """Test that empty given/when/then sections are not emitted."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        dsl = emit_story_dsl(story)

        assert "given:" not in dsl
        assert "when:" not in dsl
        assert "then:" not in dsl
        assert "unless:" not in dsl

    def test_scope_emitted(self):
        """Test scope list is emitted."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
            scope=["Invoice", "Client"],
        )

        dsl = emit_story_dsl(story)

        assert "  scope: [Invoice, Client]" in dsl

    def test_description_emitted(self):
        """Test description is emitted as docstring."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            description="A longer description of this story",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        dsl = emit_story_dsl(story)

        assert '  "A longer description of this story"' in dsl


class TestGetNextStoryIdFromAppspec:
    """Tests for get_next_story_id_from_appspec."""

    def test_empty_list(self):
        """Test with no existing stories."""
        assert get_next_story_id_from_appspec([]) == "ST-001"

    def test_sequential(self):
        """Test with sequential IDs."""
        stories = [
            StorySpec(story_id="ST-001", title="S1", actor="U", trigger=StoryTrigger.USER_CLICK),
            StorySpec(story_id="ST-003", title="S3", actor="U", trigger=StoryTrigger.USER_CLICK),
        ]
        assert get_next_story_id_from_appspec(stories) == "ST-004"

    def test_non_sequential(self):
        """Test with gaps in IDs."""
        stories = [
            StorySpec(story_id="ST-007", title="S7", actor="U", trigger=StoryTrigger.USER_CLICK),
        ]
        assert get_next_story_id_from_appspec(stories) == "ST-008"


class TestAppendStoriesToDsl:
    """Tests for append_stories_to_dsl."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            (project / "dsl").mkdir()
            yield project

    def test_creates_new_file(self, temp_project):
        """Test creating a new stories.dsl file."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        result = append_stories_to_dsl(temp_project, [story])

        assert result.exists()
        content = result.read_text()
        assert 'story ST-001 "Test":' in content

    def test_appends_to_existing(self, temp_project):
        """Test appending to an existing stories.dsl file."""
        stories_file = temp_project / "dsl" / "stories.dsl"
        stories_file.write_text('story ST-001 "First":\n  actor: User\n  trigger: user_click\n')

        story = StorySpec(
            story_id="ST-002",
            title="Second",
            actor="Admin",
            trigger=StoryTrigger.FORM_SUBMITTED,
        )

        result = append_stories_to_dsl(temp_project, [story])

        content = result.read_text()
        assert "ST-001" in content  # Original preserved
        assert "ST-002" in content  # New added

    def test_multiple_stories(self, temp_project):
        """Test appending multiple stories at once."""
        stories = [
            StorySpec(
                story_id=f"ST-{i:03d}",
                title=f"Story {i}",
                actor="User",
                trigger=StoryTrigger.USER_CLICK,
            )
            for i in range(1, 4)
        ]

        result = append_stories_to_dsl(temp_project, stories)

        content = result.read_text()
        assert "ST-001" in content
        assert "ST-002" in content
        assert "ST-003" in content

    def test_creates_dsl_directory(self, tmp_path):
        """Test that dsl/ directory is created if missing."""
        story = StorySpec(
            story_id="ST-001",
            title="Test",
            actor="User",
            trigger=StoryTrigger.USER_CLICK,
        )

        result = append_stories_to_dsl(tmp_path, [story])

        assert result.exists()
        assert (tmp_path / "dsl").is_dir()
