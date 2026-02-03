"""Tests for workflow-oriented process proposal (design briefs)."""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

from dazzle.core.ir.stories import StorySpec, StoryTrigger
from dazzle.mcp.server.handlers.process import (
    WorkflowProposal,
    _build_entity_context,
    _build_review_checklist,
    _cluster_stories_into_workflows,
    _generate_design_questions,
    _is_crud_story,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_story(
    story_id: str = "ST-001",
    title: str = "Test story",
    actor: str = "User",
    trigger: StoryTrigger = StoryTrigger.FORM_SUBMITTED,
    scope: list[str] | None = None,
    happy_path_outcome: list[str] | None = None,
    unless: list | None = None,
    constraints: list[str] | None = None,
    side_effects: list[str] | None = None,
) -> StorySpec:
    """Create a StorySpec for testing."""
    return StorySpec(
        story_id=story_id,
        title=title,
        actor=actor,
        trigger=trigger,
        scope=scope or [],
        happy_path_outcome=happy_path_outcome or [],
        unless=unless or [],
        constraints=constraints or [],
        side_effects=side_effects or [],
    )


def _make_app_spec(entities: list | None = None) -> MagicMock:
    """Create a minimal mock AppSpec."""
    spec = MagicMock()
    spec.domain.entities = entities or []
    spec.stories = []
    spec.processes = []
    return spec


def _make_entity(
    name: str,
    fields: list | None = None,
    state_machine: MagicMock | None = None,
) -> MagicMock:
    """Create a mock entity."""
    entity = MagicMock()
    entity.name = name
    entity.fields = fields or []
    entity.state_machine = state_machine
    return entity


# =============================================================================
# CRUD Detection
# =============================================================================


class TestCrudDetection:
    """Tests for _is_crud_story."""

    def test_simple_create_is_crud(self):
        story = _make_story(
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task"],
            happy_path_outcome=["New Task is saved"],
        )
        assert _is_crud_story(story) is True

    def test_status_changed_is_not_crud(self):
        story = _make_story(
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Task"],
            happy_path_outcome=["Task becomes completed"],
        )
        assert _is_crud_story(story) is False

    def test_crud_with_unless_is_not_crud(self):
        from dazzle.core.ir.stories import StoryException

        story = _make_story(
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task"],
            happy_path_outcome=["Task is saved"],
            unless=[StoryException(condition="Title is empty", then_outcomes=["Error shown"])],
        )
        assert _is_crud_story(story) is False

    def test_multi_entity_scope_is_not_crud(self):
        story = _make_story(
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task", "Project"],
            happy_path_outcome=["Task is saved"],
        )
        assert _is_crud_story(story) is False

    def test_non_crud_outcome_is_not_crud(self):
        story = _make_story(
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Task"],
            happy_path_outcome=["Email notification is sent to manager"],
        )
        assert _is_crud_story(story) is False

    def test_cron_trigger_is_not_crud(self):
        story = _make_story(
            trigger=StoryTrigger.CRON_DAILY,
            scope=["Report"],
            happy_path_outcome=["Report is created"],
        )
        assert _is_crud_story(story) is False


# =============================================================================
# Story Clustering
# =============================================================================


class TestStoryClustering:
    """Tests for _cluster_stories_into_workflows."""

    def test_crud_stories_grouped_as_not_recommended(self):
        stories = [
            _make_story(
                "ST-001",
                "Create task",
                scope=["Task"],
                happy_path_outcome=["Task is saved"],
                trigger=StoryTrigger.FORM_SUBMITTED,
            ),
            _make_story(
                "ST-002",
                "Delete task",
                scope=["Task"],
                happy_path_outcome=["Task is deleted"],
                trigger=StoryTrigger.USER_CLICK,
            ),
        ]
        app_spec = _make_app_spec()

        proposals = _cluster_stories_into_workflows(stories, app_spec)

        crud_proposals = [p for p in proposals if p.recommendation == "process_not_recommended"]
        assert len(crud_proposals) == 1
        assert set(crud_proposals[0].implements) == {"ST-001", "ST-002"}

    def test_lifecycle_stories_clustered(self):
        stories = [
            _make_story(
                "ST-001", "Submit task", scope=["Task"], trigger=StoryTrigger.STATUS_CHANGED
            ),
            _make_story(
                "ST-002", "Complete task", scope=["Task"], trigger=StoryTrigger.STATUS_CHANGED
            ),
        ]
        app_spec = _make_app_spec()

        proposals = _cluster_stories_into_workflows(stories, app_spec)

        lifecycle = [p for p in proposals if "lifecycle" in p.name]
        assert len(lifecycle) == 1
        assert lifecycle[0].recommendation == "compose_process"
        assert set(lifecycle[0].implements) == {"ST-001", "ST-002"}

    def test_cron_stories_clustered(self):
        stories = [
            _make_story(
                "ST-001", "Daily report", scope=["Report"], trigger=StoryTrigger.CRON_DAILY
            ),
            _make_story(
                "ST-002", "Hourly check", scope=["Report"], trigger=StoryTrigger.CRON_HOURLY
            ),
        ]
        app_spec = _make_app_spec()

        proposals = _cluster_stories_into_workflows(stories, app_spec)

        scheduled = [p for p in proposals if "scheduled" in p.name]
        assert len(scheduled) == 1
        assert scheduled[0].recommendation == "compose_process"

    def test_mixed_entities_create_separate_clusters(self):
        stories = [
            _make_story(
                "ST-001", "Submit task", scope=["Task"], trigger=StoryTrigger.STATUS_CHANGED
            ),
            _make_story(
                "ST-002", "File invoice", scope=["Invoice"], trigger=StoryTrigger.STATUS_CHANGED
            ),
        ]
        app_spec = _make_app_spec()

        proposals = _cluster_stories_into_workflows(stories, app_spec)

        assert len(proposals) == 2
        names = {p.name for p in proposals}
        assert "task_lifecycle" in names or any("task" in n for n in names)

    def test_unscoped_stories_grouped(self):
        stories = [
            _make_story("ST-001", "System cleanup", scope=[], trigger=StoryTrigger.CRON_DAILY),
        ]
        app_spec = _make_app_spec()

        proposals = _cluster_stories_into_workflows(stories, app_spec)

        assert len(proposals) == 1
        assert proposals[0].name == "unscoped_workflow"


# =============================================================================
# Design Questions
# =============================================================================


class TestDesignQuestions:
    """Tests for _generate_design_questions."""

    def test_automated_trigger_question(self):
        stories = [_make_story(trigger=StoryTrigger.CRON_DAILY, scope=["Task"])]
        questions = _generate_design_questions(stories, "Task", _make_app_spec())
        assert any("trigger" in q.lower() for q in questions)

    def test_multiple_actors_question(self):
        stories = [
            _make_story("ST-001", actor="Admin", scope=["Task"]),
            _make_story("ST-002", actor="User", scope=["Task"]),
        ]
        questions = _generate_design_questions(stories, "Task", _make_app_spec())
        assert any("actors" in q.lower() or "handoff" in q.lower() for q in questions)

    def test_state_machine_question(self):
        sm = MagicMock()
        sm.states = ["draft", "submitted", "approved"]
        entity = _make_entity("Task", state_machine=sm)
        app_spec = _make_app_spec(entities=[entity])

        stories = [_make_story(scope=["Task"], trigger=StoryTrigger.STATUS_CHANGED)]
        questions = _generate_design_questions(stories, "Task", app_spec)
        assert any("states" in q.lower() for q in questions)

    def test_exception_path_question(self):
        from dazzle.core.ir.stories import StoryException

        stories = [
            _make_story(
                scope=["Task"],
                unless=[StoryException(condition="Task is locked", then_outcomes=["Error"])],
            ),
        ]
        questions = _generate_design_questions(stories, "Task", _make_app_spec())
        assert any("compensation" in q.lower() or "exception" in q.lower() for q in questions)

    def test_multi_entity_scope_question(self):
        stories = [
            _make_story("ST-001", scope=["Task", "Project"]),
        ]
        questions = _generate_design_questions(stories, "Task", _make_app_spec())
        assert any("failure" in q.lower() or "retry" in q.lower() for q in questions)

    def test_constraint_question(self):
        stories = [
            _make_story(
                "ST-001",
                scope=["Invoice"],
                trigger=StoryTrigger.STATUS_CHANGED,
                constraints=["Cannot send twice"],
            ),
        ]
        questions = _generate_design_questions(stories, "Invoice", _make_app_spec())
        assert any("cannot send twice" in q.lower() for q in questions)

    def test_side_effect_question(self):
        stories = [
            _make_story(
                "ST-001",
                scope=["Task"],
                trigger=StoryTrigger.STATUS_CHANGED,
                side_effects=["send_email_notification"],
            ),
        ]
        questions = _generate_design_questions(stories, "Task", _make_app_spec())
        assert any("send_email_notification" in q for q in questions)

    def test_integration_title_question(self):
        stories = [
            _make_story(
                "ST-001",
                title="File VAT return to HMRC via API",
                scope=["VATReturn"],
                trigger=StoryTrigger.STATUS_CHANGED,
            ),
        ]
        questions = _generate_design_questions(stories, "VATReturn", _make_app_spec())
        assert any("integration" in q.lower() for q in questions)


# =============================================================================
# Review Checklist
# =============================================================================


class TestReviewChecklist:
    """Tests for _build_review_checklist."""

    def test_empty_for_no_obligations(self):
        stories = [_make_story()]
        assert _build_review_checklist(stories) == []

    def test_constraint_items(self):
        stories = [
            _make_story("ST-001", constraints=["Cannot send twice", "Amount > 0"]),
        ]
        checklist = _build_review_checklist(stories)
        assert len(checklist) == 2
        assert checklist[0]["type"] == "constraint"
        assert checklist[0]["obligation"] == "Cannot send twice"
        assert "ST-001" == checklist[0]["story_id"]

    def test_side_effect_items(self):
        stories = [
            _make_story("ST-001", side_effects=["send_confirmation_email"]),
        ]
        checklist = _build_review_checklist(stories)
        assert len(checklist) == 1
        assert checklist[0]["type"] == "side_effect"
        assert "send_confirmation_email" in checklist[0]["verify"]

    def test_exception_items(self):
        from dazzle.core.ir.stories import StoryException

        stories = [
            _make_story(
                "ST-001",
                unless=[
                    StoryException(
                        condition="HMRC API returns error",
                        then_outcomes=["Error is logged", "Retry scheduled"],
                    )
                ],
            ),
        ]
        checklist = _build_review_checklist(stories)
        assert len(checklist) == 1
        assert checklist[0]["type"] == "exception"
        assert "HMRC API returns error" in checklist[0]["verify"]
        assert "Retry scheduled" in checklist[0]["verify"]

    def test_mixed_obligations(self):
        from dazzle.core.ir.stories import StoryException

        stories = [
            _make_story(
                "ST-001",
                constraints=["Four-eye rule"],
                side_effects=["audit_log"],
                unless=[StoryException(condition="Timeout", then_outcomes=["Retry"])],
            ),
        ]
        checklist = _build_review_checklist(stories)
        types = {item["type"] for item in checklist}
        assert types == {"constraint", "side_effect", "exception"}


# =============================================================================
# Entity Context
# =============================================================================


class TestEntityContext:
    """Tests for _build_entity_context."""

    def test_missing_entity(self):
        app_spec = _make_app_spec()
        ctx = _build_entity_context("Missing", app_spec)
        assert ctx["entity"] == "Missing"
        assert "note" in ctx

    def test_entity_with_fields(self):
        field = MagicMock()
        field.name = "title"
        field.type.kind.value = "str"
        field.type.ref_entity = None
        # Make the `in` check fail for relationship kinds
        from dazzle.core.ir.fields import FieldTypeKind

        field.type.kind = FieldTypeKind.STR

        entity = _make_entity("Task", fields=[field])
        app_spec = _make_app_spec(entities=[entity])

        ctx = _build_entity_context("Task", app_spec)
        assert ctx["entity"] == "Task"
        assert "title" in ctx["fields"]
        assert "relationships" not in ctx

    def test_entity_with_state_machine(self):
        sm = MagicMock()
        sm.status_field = "status"
        sm.states = ["draft", "done"]
        sm.transitions = []

        entity = _make_entity("Task", fields=[], state_machine=sm)
        app_spec = _make_app_spec(entities=[entity])

        ctx = _build_entity_context("Task", app_spec)
        assert ctx["state_machine"]["status_field"] == "status"
        assert ctx["state_machine"]["states"] == ["draft", "done"]


# =============================================================================
# WorkflowProposal serialization
# =============================================================================


class TestWorkflowProposal:
    """Tests for WorkflowProposal dataclass."""

    def test_asdict(self):
        p = WorkflowProposal(
            name="test",
            title="Test",
            implements=["ST-001"],
            story_summaries=[
                {"story_id": "ST-001", "title": "T", "trigger": "form_submitted", "actor": "User"}
            ],
            entity=None,
            design_questions=["Q1?"],
            recommendation="compose_process",
            reason="Test reason",
        )
        d = asdict(p)
        assert d["name"] == "test"
        assert d["recommendation"] == "compose_process"
        assert len(d["design_questions"]) == 1
