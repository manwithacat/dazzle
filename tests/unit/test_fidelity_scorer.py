"""
Unit tests for the fidelity scorer, focusing on enhanced story embodiment checks.

Tests cover:
- Scope alignment (story scope vs surface entity binding)
- Given-condition field presence
- When-trigger matching against buttons/links
- Then-outcome field visibility
- Unless-branch coverage
- Story loading fallback for score_appspec_fidelity
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dazzle.core.fidelity_scorer import (
    _check_story_embodiment,
    _load_stories_for_scoring,
    _match_stories_to_surfaces,
    parse_html,
)
from dazzle.core.ir.fidelity import FidelityGapCategory
from dazzle.core.ir.stories import (
    StoryCondition,
    StoryException,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.ir.surfaces import SurfaceMode


def _make_surface(
    name: str = "task_list",
    entity_ref: str | None = "Task",
    mode: SurfaceMode = SurfaceMode.LIST,
    field_names: list[str] | None = None,
) -> MagicMock:
    """Create a mock SurfaceSpec."""
    surface = MagicMock()
    surface.name = name
    surface.entity_ref = entity_ref
    surface.mode = mode

    fields = field_names or ["title", "status"]
    elements = []
    for fn in fields:
        elem = MagicMock()
        elem.field_name = fn
        elem.options = {}
        elements.append(elem)

    section = MagicMock()
    section.elements = elements
    surface.sections = [section]
    return surface


def _make_story(
    story_id: str = "ST-001",
    title: str = "User completes task",
    scope: list[str] | None = None,
    given: list[StoryCondition] | None = None,
    when: list[StoryCondition] | None = None,
    then: list[StoryCondition] | None = None,
    unless: list[StoryException] | None = None,
) -> StorySpec:
    return StorySpec(
        story_id=story_id,
        title=title,
        actor="User",
        trigger=StoryTrigger.USER_CLICK,
        scope=scope or ["Task"],
        given=given or [],
        when=when or [],
        then=then or [],
        unless=unless or [],
        status=StoryStatus.ACCEPTED,
    )


class TestMatchStoriesToSurfaces:
    """Tests for _match_stories_to_surfaces."""

    def test_match_by_scope(self) -> None:
        surface = _make_surface(entity_ref="Task")
        story = _make_story(scope=["Task", "User"])
        result = _match_stories_to_surfaces(surface, [story])
        assert len(result) == 1

    def test_no_match_different_scope(self) -> None:
        surface = _make_surface(entity_ref="Task")
        story = _make_story(scope=["Order"], title="User places order")
        result = _match_stories_to_surfaces(surface, [story])
        assert len(result) == 0

    def test_match_by_title_fallback(self) -> None:
        surface = _make_surface(entity_ref="Task")
        story = _make_story(scope=[], title="User completes Task")
        result = _match_stories_to_surfaces(surface, [story])
        assert len(result) == 1

    def test_no_entity_ref_returns_empty(self) -> None:
        surface = _make_surface(entity_ref=None)
        story = _make_story()
        result = _match_stories_to_surfaces(surface, [story])
        assert len(result) == 0


class TestScopeAlignment:
    """Tests for scope alignment — scope mismatches are no longer fidelity gaps."""

    def test_scope_mismatch_not_reported(self) -> None:
        """Multi-entity scope no longer produces fidelity gaps."""
        surface = _make_surface(entity_ref="Task")
        story = _make_story(scope=["Task", "Project"])
        root = parse_html("<div><button>Complete</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        scope_gaps = [g for g in gaps if "scope" in g.target.lower()]
        assert len(scope_gaps) == 0

    def test_scope_fully_matched(self) -> None:
        surface = _make_surface(entity_ref="Task")
        story = _make_story(scope=["Task"])
        root = parse_html("<div><button>Complete</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        scope_gaps = [g for g in gaps if "scope" in g.target.lower()]
        assert len(scope_gaps) == 0


class TestGivenConditionFields:
    """Tests for given-condition field presence."""

    def test_missing_given_field(self) -> None:
        surface = _make_surface(field_names=["title"])
        story = _make_story(
            given=[StoryCondition(expression="Task.status is 'open'", field_path="Task.status")]
        )
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert len(precond_gaps) == 1
        assert "status" in precond_gaps[0].target

    def test_given_field_present(self) -> None:
        surface = _make_surface(field_names=["title", "status"])
        story = _make_story(
            given=[StoryCondition(expression="Task.status is 'open'", field_path="Task.status")]
        )
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert len(precond_gaps) == 0

    def test_given_without_field_path_skipped(self) -> None:
        surface = _make_surface(field_names=["title"])
        story = _make_story(given=[StoryCondition(expression="User is logged in", field_path=None)])
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert len(precond_gaps) == 0


class TestWhenTriggerMatching:
    """Tests for when-trigger matching against buttons/links."""

    def test_no_action_elements_triggers_gap(self) -> None:
        surface = _make_surface()
        story = _make_story(when=[StoryCondition(expression="user clicks Complete button")])
        root = parse_html("<div>No buttons here</div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        trigger_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_TRIGGER_MISSING]
        assert len(trigger_gaps) == 1

    def test_matching_button_present(self) -> None:
        surface = _make_surface()
        story = _make_story(when=[StoryCondition(expression="user clicks Complete button")])
        root = parse_html("<div><button>Complete</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        trigger_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_TRIGGER_MISSING]
        assert len(trigger_gaps) == 0


class TestThenOutcomeVerification:
    """Tests for then-outcome field visibility."""

    def test_missing_outcome_field(self) -> None:
        surface = _make_surface(field_names=["title"])
        story = _make_story(
            then=[
                StoryCondition(
                    expression="Task.completed_at is recorded",
                    field_path="Task.completed_at",
                )
            ]
        )
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert len(outcome_gaps) == 1
        assert "completed_at" in outcome_gaps[0].target

    def test_outcome_field_in_surface(self) -> None:
        surface = _make_surface(field_names=["title", "completed_at"])
        story = _make_story(
            then=[
                StoryCondition(
                    expression="Task.completed_at is recorded",
                    field_path="Task.completed_at",
                )
            ]
        )
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert len(outcome_gaps) == 0

    def test_outcome_field_in_rendered_text(self) -> None:
        surface = _make_surface(field_names=["title"])
        story = _make_story(
            then=[
                StoryCondition(
                    expression="Task.completed_at is recorded",
                    field_path="Task.completed_at",
                )
            ]
        )
        root = parse_html("<div>completed_at: 2024-01-01</div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert len(outcome_gaps) == 0


class TestUnlessBranchCoverage:
    """Tests for unless-branch coverage."""

    def test_missing_exception_handling(self) -> None:
        surface = _make_surface()
        story = _make_story(
            unless=[
                StoryException(
                    condition="Task.assignee is missing",
                    then_outcomes=["Error is displayed"],
                )
            ]
        )
        root = parse_html("<div><button>Go</button></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        unless_gaps = [g for g in gaps if "unless" in g.target]
        assert len(unless_gaps) == 1

    def test_exception_text_present(self) -> None:
        surface = _make_surface()
        story = _make_story(
            unless=[
                StoryException(
                    condition="Task.assignee is missing",
                    then_outcomes=["Error is displayed"],
                )
            ]
        )
        root = parse_html("<div><button>Go</button><span>assignee missing</span></div>")

        gaps = _check_story_embodiment(surface, None, root, None, [story])
        unless_gaps = [g for g in gaps if "unless" in g.target]
        assert len(unless_gaps) == 0


class TestLoadStoriesForScoring:
    """Tests for _load_stories_for_scoring fallback."""

    def test_uses_appspec_stories_when_present(self) -> None:
        appspec = MagicMock()
        story = _make_story()
        appspec.stories = [story]

        result = _load_stories_for_scoring(appspec)
        assert len(result) == 1

    def test_falls_back_to_persisted(self, tmp_path) -> None:
        appspec = MagicMock()
        appspec.stories = []
        persisted = [_make_story()]

        with patch("dazzle.core.stories_persistence.load_stories", return_value=persisted):
            result = _load_stories_for_scoring(appspec, str(tmp_path))

        assert len(result) == 1

    def test_no_fallback_without_project_root(self) -> None:
        appspec = MagicMock()
        appspec.stories = []

        result = _load_stories_for_scoring(appspec)
        assert len(result) == 0


class TestNoStoriesNoEntity:
    """Edge cases where stories or entity are absent."""

    def test_no_stories_returns_empty(self) -> None:
        surface = _make_surface()
        root = parse_html("<div></div>")
        gaps = _check_story_embodiment(surface, None, root, None, [])
        assert len(gaps) == 0

    def test_no_entity_ref_returns_empty(self) -> None:
        surface = _make_surface(entity_ref=None)
        root = parse_html("<div></div>")
        story = _make_story()
        gaps = _check_story_embodiment(surface, None, root, None, [story])
        assert len(gaps) == 0
