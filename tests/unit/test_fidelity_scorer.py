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

from unittest.mock import MagicMock

from dazzle.core.fidelity_scorer import (
    _check_form_structure,
    _check_story_embodiment,
    _expand_field_names,
    _load_stories_for_scoring,
    _match_stories_to_surfaces,
    parse_html,
    score_surface_fidelity,
)
from dazzle.core.ir.fidelity import FidelityGapCategory
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
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

    def test_given_cross_entity_skipped(self) -> None:
        """Given-condition on a different entity should not flag the surface (#481)."""
        surface = _make_surface(
            name="checklist_list", entity_ref="Checklist", field_names=["title"]
        )
        story = _make_story(
            given=[StoryCondition(expression="Contact.phone populated", field_path="Contact.phone")]
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

    def test_outcome_cross_entity_skipped(self) -> None:
        """Outcome on a different entity should not flag the surface (#481)."""
        surface = _make_surface(
            name="checklist_create", entity_ref="Checklist", field_names=["title"]
        )
        story = _make_story(
            then=[
                StoryCondition(
                    expression="Contact.phone populated from form",
                    field_path="Contact.phone",
                )
            ]
        )
        root = parse_html("<div><button>Save</button></div>")

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

    def test_empty_stories_returns_empty(self) -> None:
        appspec = MagicMock()
        appspec.stories = []

        result = _load_stories_for_scoring(appspec)
        assert len(result) == 0

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


def _make_entity(fields: list[FieldSpec]) -> MagicMock:
    """Create a mock EntitySpec with real FieldSpec objects."""
    entity = MagicMock()
    entity.fields = fields
    return entity


class TestMoneyFieldExpansion:
    """Tests for money field expansion to _minor/_currency in fidelity checks."""

    def test_expand_field_names_helper(self) -> None:
        """Direct test of _expand_field_names: money fields expand, others don't."""
        entity = _make_entity(
            [
                FieldSpec(
                    name="price", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
            ]
        )
        result = _expand_field_names(["title", "price"], entity)
        assert result == ["title", "price_minor", "price_currency"]

    def test_expand_money_field_in_form(self) -> None:
        """CREATE surface with money widget: hidden _minor/_currency inputs → no gap."""
        surface = _make_surface(
            name="product_create",
            mode=SurfaceMode.CREATE,
            field_names=["title", "price"],
        )
        entity = _make_entity(
            [
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
                FieldSpec(
                    name="price", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
            ]
        )
        html = """
        <form hx-post="/products">
            <input name="title" type="text">
            <div data-dz-money="price" data-dz-currency="GBP" data-dz-scale="2">
                <input type="text" inputmode="decimal" data-dz-money-display>
                <input type="hidden" name="price_minor" data-dz-money-minor>
                <input type="hidden" name="price_currency" data-dz-money-currency value="GBP">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        root = parse_html(html)
        gaps = _check_form_structure(surface, entity, root)
        missing = [g for g in gaps if g.category == FidelityGapCategory.MISSING_FIELD]
        assert missing == []

    def test_money_widget_data_attribute_match(self) -> None:
        """data-dz-money attribute alone satisfies the field check."""
        surface = _make_surface(
            name="product_create",
            mode=SurfaceMode.CREATE,
            field_names=["price"],
        )
        entity = _make_entity(
            [
                FieldSpec(
                    name="price", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
            ]
        )
        # Widget with data-dz-money but no named inputs (edge case)
        html = """
        <form hx-post="/products">
            <div data-dz-money="price" data-dz-currency="GBP" data-dz-scale="2">
                <input type="text" inputmode="decimal" data-dz-money-display>
            </div>
            <button type="submit">Save</button>
        </form>
        """
        root = parse_html(html)
        gaps = _check_form_structure(surface, entity, root)
        missing = [g for g in gaps if g.category == FidelityGapCategory.MISSING_FIELD]
        assert missing == []

    def test_no_expansion_without_entity(self) -> None:
        """entity=None: money field name not in inputs → gap reported."""
        result = _expand_field_names(["price", "title"], None)
        assert result == ["price", "title"]

    def test_non_money_fields_unchanged(self) -> None:
        """str/int fields pass through without expansion."""
        entity = _make_entity(
            [
                FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
                FieldSpec(name="count", type=FieldType(kind=FieldTypeKind.INT)),
            ]
        )
        result = _expand_field_names(["title", "count"], entity)
        assert result == ["title", "count"]

    def test_mixed_money_and_regular_fields(self) -> None:
        """Surface with both money and regular fields: money widgets satisfy checks."""
        surface = _make_surface(
            name="invoice_create",
            mode=SurfaceMode.CREATE,
            field_names=["description", "amount", "tax"],
        )
        entity = _make_entity(
            [
                FieldSpec(
                    name="description", type=FieldType(kind=FieldTypeKind.STR, max_length=500)
                ),
                FieldSpec(
                    name="amount", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
                FieldSpec(
                    name="tax", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
            ]
        )
        html = """
        <form hx-post="/invoices">
            <input name="description" type="text">
            <div data-dz-money="amount" data-dz-currency="GBP" data-dz-scale="2">
                <input type="text" inputmode="decimal" data-dz-money-display>
                <input type="hidden" name="amount_minor" data-dz-money-minor>
                <input type="hidden" name="amount_currency" data-dz-money-currency value="GBP">
            </div>
            <div data-dz-money="tax" data-dz-currency="GBP" data-dz-scale="2">
                <input type="text" inputmode="decimal" data-dz-money-display>
                <input type="hidden" name="tax_minor" data-dz-money-minor>
                <input type="hidden" name="tax_currency" data-dz-money-currency value="GBP">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        root = parse_html(html)
        gaps = _check_form_structure(surface, entity, root)
        missing = [g for g in gaps if g.category == FidelityGapCategory.MISSING_FIELD]
        assert missing == []

    def test_money_field_input_type_check_no_false_positive(self) -> None:
        """Input type check doesn't false-positive on money widget hidden inputs."""
        surface = _make_surface(
            name="product_create",
            mode=SurfaceMode.CREATE,
            field_names=["price"],
        )
        entity = _make_entity(
            [
                FieldSpec(
                    name="price", type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP")
                ),
            ]
        )
        html = """
        <form hx-post="/products">
            <div data-dz-money="price" data-dz-currency="GBP" data-dz-scale="2">
                <input type="text" inputmode="decimal" data-dz-money-display>
                <input type="hidden" name="price_minor" data-dz-money-minor>
                <input type="hidden" name="price_currency" data-dz-money-currency value="GBP">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_float_field_renders_as_number(self) -> None:
        """FLOAT fields render as <input type="number"> (same mapping as
        INT/DECIMAL/MONEY). Regression guard for #825: before the fix,
        FLOAT was absent from FIELD_TYPE_TO_INPUT and fell through to
        DEFAULT_INPUT_TYPE="text", producing a spurious
        INCORRECT_INPUT_TYPE gap on every float surface."""
        surface = _make_surface(
            name="reading_create",
            mode=SurfaceMode.CREATE,
            field_names=["temperature"],
        )
        entity = _make_entity(
            [
                FieldSpec(name="temperature", type=FieldType(kind=FieldTypeKind.FLOAT)),
            ]
        )
        html = """
        <form hx-post="/readings">
            <input type="number" name="temperature">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == [], f"Unexpected input-type gaps: {type_gaps}"

    def test_file_field_input_type_no_false_positive(self) -> None:
        """File fields with type='file' should not be flagged as incorrect."""
        surface = _make_surface(
            name="manuscript_create",
            mode=SurfaceMode.CREATE,
            field_names=["file_url"],
        )
        entity = _make_entity(
            [FieldSpec(name="file_url", type=FieldType(kind=FieldTypeKind.FILE))],
        )
        html = """
        <form hx-post="/manuscripts">
            <input type="file" name="file_url">
            <button type="submit">Upload</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_file_field_skipped_in_type_check(self) -> None:
        """File fields should be skipped in input type checks (#579).

        File uploads often use custom widgets (dropzones, etc.) so comparing
        against <input> type attributes produces false positives.
        """
        surface = _make_surface(
            name="manuscript_create",
            mode=SurfaceMode.CREATE,
            field_names=["file_url"],
        )
        entity = _make_entity(
            [FieldSpec(name="file_url", type=FieldType(kind=FieldTypeKind.FILE))],
        )
        html = """
        <form hx-post="/manuscripts">
            <input type="text" name="file_url">
            <button type="submit">Upload</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert len(type_gaps) == 0


class TestWidgetRenderedInputTypes:
    """Widget-rendered input types satisfy the expected DSL type (#779)."""

    def test_datepicker_on_date_field(self) -> None:
        """Flatpickr datepicker: type='text' + data-dz-widget='datepicker' satisfies date."""
        surface = _make_surface(
            name="event_create",
            mode=SurfaceMode.CREATE,
            field_names=["starts_on"],
        )
        entity = _make_entity(
            [FieldSpec(name="starts_on", type=FieldType(kind=FieldTypeKind.DATE))],
        )
        html = """
        <form hx-post="/events">
            <input name="starts_on" type="text" data-dz-widget="datepicker">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_datepicker_on_datetime_field(self) -> None:
        """Flatpickr datepicker with enableTime: satisfies datetime field."""
        surface = _make_surface(
            name="event_create",
            mode=SurfaceMode.CREATE,
            field_names=["starts_at"],
        )
        entity = _make_entity(
            [FieldSpec(name="starts_at", type=FieldType(kind=FieldTypeKind.DATETIME))],
        )
        html = """
        <form hx-post="/events">
            <input name="starts_at" type="text" data-dz-widget="datepicker">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_range_slider_on_int_field(self) -> None:
        """Range slider: type='range' satisfies int/number field."""
        surface = _make_surface(
            name="settings_edit",
            mode=SurfaceMode.EDIT,
            field_names=["volume"],
        )
        entity = _make_entity(
            [FieldSpec(name="volume", type=FieldType(kind=FieldTypeKind.INT))],
        )
        html = """
        <form hx-put="/settings">
            <div data-dz-widget="range-tooltip">
                <input name="volume" type="range" min="0" max="100">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_range_slider_on_decimal_field(self) -> None:
        """Range slider satisfies decimal fields as well."""
        surface = _make_surface(
            name="settings_edit",
            mode=SurfaceMode.EDIT,
            field_names=["opacity"],
        )
        entity = _make_entity(
            [FieldSpec(name="opacity", type=FieldType(kind=FieldTypeKind.DECIMAL))],
        )
        html = """
        <form hx-put="/settings">
            <input name="opacity" type="range" min="0" max="1" step="0.01">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_richtext_hidden_input_on_str_field(self) -> None:
        """Rich text widget: hidden input inside data-dz-widget='richtext' satisfies str."""
        surface = _make_surface(
            name="post_create",
            mode=SurfaceMode.CREATE,
            field_names=["body"],
        )
        entity = _make_entity(
            [FieldSpec(name="body", type=FieldType(kind=FieldTypeKind.STR, max_length=5000))],
        )
        html = """
        <form hx-post="/posts">
            <div data-dz-widget="richtext">
                <div class="quill-editor"></div>
                <input type="hidden" name="body">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_richtext_hidden_input_on_enum_field(self) -> None:
        """Rich text widget on enum: hidden input satisfies select expectation."""
        surface = _make_surface(
            name="post_create",
            mode=SurfaceMode.CREATE,
            field_names=["category"],
        )
        entity = _make_entity(
            [FieldSpec(name="category", type=FieldType(kind=FieldTypeKind.ENUM))],
        )
        html = """
        <form hx-post="/posts">
            <div data-dz-widget="richtext">
                <input type="hidden" name="category">
            </div>
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_unknown_widget_still_flags_mismatch(self) -> None:
        """Unknown widget name doesn't silently bypass the type check."""
        surface = _make_surface(
            name="event_create",
            mode=SurfaceMode.CREATE,
            field_names=["starts_on"],
        )
        entity = _make_entity(
            [FieldSpec(name="starts_on", type=FieldType(kind=FieldTypeKind.DATE))],
        )
        html = """
        <form hx-post="/events">
            <input name="starts_on" type="text" data-dz-widget="mysterywidget">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert len(type_gaps) == 1

    def test_plain_mismatch_without_widget_still_flags(self) -> None:
        """Type mismatch with no widget context still produces a gap."""
        surface = _make_surface(
            name="event_create",
            mode=SurfaceMode.CREATE,
            field_names=["starts_on"],
        )
        entity = _make_entity(
            [FieldSpec(name="starts_on", type=FieldType(kind=FieldTypeKind.DATE))],
        )
        html = """
        <form hx-post="/events">
            <input name="starts_on" type="text">
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert len(type_gaps) == 1

    def test_search_select_widget_satisfies_str_field(self) -> None:
        """Closes #878: search_select renders the str value as an
        ``<input type="hidden">`` form-submission carrier alongside a visible
        ``<input type="text">`` search box. The hidden input is intentional;
        a str field rendered through this widget must NOT generate an
        INCORRECT_INPUT_TYPE gap. Equivalence depends on the wrapper div
        carrying ``data-dz-widget="search_select"`` (cf. the actual fragment
        at ``src/dazzle_ui/templates/fragments/search_select.html``)."""
        surface = _make_surface(
            name="device_create",
            mode=SurfaceMode.CREATE,
            field_names=["manufacturer"],
        )
        entity = _make_entity(
            [
                FieldSpec(
                    name="manufacturer",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                )
            ],
        )
        html = """
        <form hx-post="/devices">
            <div class="relative w-full" x-data="{ open: false }" data-dz-widget="search_select">
                <input type="hidden" name="manufacturer" id="field-manufacturer" />
                <input type="text" id="search-input-manufacturer" role="combobox" />
            </div>
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert type_gaps == []

    def test_search_select_without_widget_marker_still_flags(self) -> None:
        """Counter-test: a str field rendered as <input type="hidden"> with no
        widget marker remains a real defect — equivalence is gated on the
        ``data-dz-widget="search_select"`` decorator on the wrapper. If the
        decorator goes missing during a refactor, the false-positive flag
        returns and surfaces the regression."""
        surface = _make_surface(
            name="device_create",
            mode=SurfaceMode.CREATE,
            field_names=["manufacturer"],
        )
        entity = _make_entity(
            [
                FieldSpec(
                    name="manufacturer",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                )
            ],
        )
        html = """
        <form hx-post="/devices">
            <input type="hidden" name="manufacturer" />
            <button type="submit">Save</button>
        </form>
        """
        score = score_surface_fidelity(surface, entity, html)
        type_gaps = [
            g for g in score.gaps if g.category == FidelityGapCategory.INCORRECT_INPUT_TYPE
        ]
        assert len(type_gaps) == 1


class TestRenderedPagesCompositeKey:
    """Regression guard for #828 — rendered_pages keyed by ``(view_name, entity_ref)``.

    Prior behaviour: rendered_pages was keyed by surface name alone, so two
    surfaces that shared a name but targeted different entities (e.g. an app's
    own ``feedback_create`` vs. the framework's auto-synthesised
    ``feedback_create`` on FeedbackReport) would silently collide. The scorer
    then compared the losing surface's fields against the winning surface's
    HTML, producing ghost structural gaps on a surface that actually rendered
    all its inputs correctly.
    """

    def test_colliding_surface_names_scored_independently(self) -> None:
        """Two surfaces with the same name but different entity_ref must score
        against their own HTML, not clobber each other."""
        from dazzle.core.fidelity_scorer import score_appspec_fidelity

        surface_a = _make_surface(
            name="feedback_create",
            entity_ref="ManuscriptFeedback",
            mode=SurfaceMode.CREATE,
            field_names=["manuscript", "summary"],
        )
        surface_b = _make_surface(
            name="feedback_create",
            entity_ref="FeedbackReport",
            mode=SurfaceMode.CREATE,
            field_names=["category", "severity"],
        )

        entity_a = MagicMock()
        entity_a.name = "ManuscriptFeedback"
        entity_a.fields = [
            FieldSpec(name="manuscript", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="summary", type=FieldType(kind=FieldTypeKind.STR)),
        ]
        entity_b = MagicMock()
        entity_b.name = "FeedbackReport"
        entity_b.fields = [
            FieldSpec(name="category", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="severity", type=FieldType(kind=FieldTypeKind.STR)),
        ]

        appspec = MagicMock()
        appspec.surfaces = [surface_a, surface_b]
        appspec.stories = []
        appspec.get_entity = lambda ref: entity_a if ref == "ManuscriptFeedback" else entity_b

        html_a = """
        <form>
            <input name="manuscript"><input name="summary">
            <button type="submit">Save</button>
        </form>
        """
        html_b = """
        <form>
            <input name="category"><input name="severity">
            <button type="submit">Save</button>
        </form>
        """

        rendered = {
            ("feedback_create", "ManuscriptFeedback"): html_a,
            ("feedback_create", "FeedbackReport"): html_b,
        }

        report = score_appspec_fidelity(appspec, rendered)

        # Both surfaces must be scored — no silent drop from key collision.
        assert len(report.surface_scores) == 2

    def test_missing_entity_ref_uses_empty_string_key(self) -> None:
        """Surface with no entity_ref looks up by ``(name, "")``."""
        from dazzle.core.fidelity_scorer import score_appspec_fidelity

        surface = _make_surface(
            name="dashboard",
            entity_ref=None,
            mode=SurfaceMode.LIST,
            field_names=["title"],
        )
        appspec = MagicMock()
        appspec.surfaces = [surface]
        appspec.stories = []
        appspec.get_entity = lambda ref: None

        rendered = {
            ("dashboard", ""): "<div>stub</div>",
        }

        report = score_appspec_fidelity(appspec, rendered)
        assert len(report.surface_scores) == 1


class TestSearchSelectErrorHandlerCheck:
    """Regression guard: the search_select interaction-fidelity error-handler
    check accepts the design-token / ARIA wiring used by the post-DaisyUI
    template, not just the legacy ``text-error`` class. Surfaced cycle 105
    via contract_audit on widget-search-select.md."""

    def _make_search_select_surface(self):
        return _make_surface(
            name="contact_create",
            entity_ref="Contact",
            mode=SurfaceMode.CREATE,
            field_names=["company"],
        )

    def _make_search_select_html(self, error_marker: str) -> str:
        # Mirrors the real fragments/search_select.html shape — the only
        # variable bit is which error-marker class/attribute is present.
        return f"""
        <div class="relative w-full" x-data="{{{{ open: false }}}}">
          <input type="hidden" name="company" id="field-company" {error_marker} />
          <input type="text" id="search-input-company" role="combobox"
                 hx-get="/api/_fragments/search"
                 hx-trigger="keyup changed delay:400ms"
                 hx-target="#search-results-company"
                 hx-indicator="#search-spinner-company" />
          <div id="search-results-company" role="listbox">
            Type at least 3 characters to search...
          </div>
        </div>
        """

    def _error_handler_gaps(self, html: str) -> list:
        from dazzle.core.fidelity_scorer import _check_interaction_fidelity, parse_html

        root = parse_html(html)
        gaps = _check_interaction_fidelity(self._make_search_select_surface(), root, html)
        return [g for g in gaps if g.category == FidelityGapCategory.MISSING_ERROR_HANDLER]

    def test_aria_invalid_satisfies_error_handler_check(self) -> None:
        html = self._make_search_select_html('aria-invalid="true"')
        assert self._error_handler_gaps(html) == []

    def test_destructive_token_satisfies_error_handler_check(self) -> None:
        html = self._make_search_select_html('class="border-[hsl(var(--destructive))]"')
        assert self._error_handler_gaps(html) == []

    def test_legacy_text_error_class_still_satisfies_check(self) -> None:
        # Backwards compat — apps not yet migrated off DaisyUI keep passing.
        html = self._make_search_select_html('class="text-error"')
        assert self._error_handler_gaps(html) == []

    def test_no_error_marker_still_flagged(self) -> None:
        html = self._make_search_select_html("")
        gaps = self._error_handler_gaps(html)
        assert len(gaps) == 1
        assert gaps[0].severity == "minor"


class TestCreateModeStoryGapSuppression:
    """Regression guard: mode:create surfaces don't generate story-precondition
    gaps when the entity field default satisfies the precondition value, and
    don't generate then-outcome gaps for transition-verb outcomes ('becomes X',
    'changes to Y', 'transitions through Z'). Surfaced cycle 106 as Option B
    fix to #877. The complementary Option A (transition-trigger exclusion)
    remains a separate human-triage concern."""

    def _make_task_entity(self, status_default: str = "todo"):
        from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind

        ent = MagicMock()
        ent.name = "Task"
        ent.fields = [
            FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(
                name="status",
                type=FieldType(kind=FieldTypeKind.ENUM),
                default=status_default,
            ),
        ]
        return ent

    def _make_story(self, story_id: str, given: list[str] = (), then: list[str] = ()) -> StorySpec:
        # Use USER_CLICK so Option A's status_changed pre-filter (in
        # `_match_stories_to_surfaces`) doesn't suppress the story before
        # Option B's default-aware / transition-verb logic gets a chance to
        # run. Option A and Option B are independent suppressions; this test
        # class exercises Option B specifically.
        return StorySpec(
            story_id=story_id,
            title=f"Story {story_id}",
            actor="admin",
            scope=["Task"],
            status=StoryStatus.ACCEPTED,
            trigger=StoryTrigger.USER_CLICK,
            given=[StoryCondition(expression=g, field_path="Task.status") for g in given],
            when=[],
            then=[StoryCondition(expression=t, field_path="Task.status") for t in then],
            unless=[],
        )

    def _gaps_for(self, surface, entity, stories):
        return _check_story_embodiment(
            surface,
            entity,
            parse_html("<form><input name='title'></form>"),
            None,
            stories,
        )

    def test_create_skips_precondition_when_default_matches(self) -> None:
        """Task.status defaults to 'todo' → precondition 'is todo' satisfied implicitly."""
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        entity = self._make_task_entity(status_default="todo")
        story = self._make_story("ST-001", given=["Task.status is 'todo'"])
        gaps = self._gaps_for(surface, entity, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert precond_gaps == []

    def test_create_still_flags_precondition_when_default_differs(self) -> None:
        """Task.status defaults to 'todo' → precondition 'is in_progress' is NOT satisfied."""
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        entity = self._make_task_entity(status_default="todo")
        story = self._make_story("ST-009", given=["Task.status is 'in_progress'"])
        gaps = self._gaps_for(surface, entity, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert len(precond_gaps) == 1

    def test_edit_still_flags_precondition_even_when_default_matches(self) -> None:
        """Edit surfaces show current entity state — defaults don't apply, so
        the gap is real if the field is missing from the surface."""
        surface = _make_surface(
            name="task_edit",
            entity_ref="Task",
            mode=SurfaceMode.EDIT,
            field_names=["title"],
        )
        entity = self._make_task_entity(status_default="todo")
        story = self._make_story("ST-001", given=["Task.status is 'todo'"])
        gaps = self._gaps_for(surface, entity, [story])
        precond_gaps = [
            g for g in gaps if g.category == FidelityGapCategory.STORY_PRECONDITION_MISSING
        ]
        assert len(precond_gaps) == 1

    def test_create_skips_outcome_for_becomes_transition(self) -> None:
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        entity = self._make_task_entity()
        story = self._make_story("ST-008", then=["Task.status becomes 'in_progress'"])
        gaps = self._gaps_for(surface, entity, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert outcome_gaps == []

    def test_create_skips_outcome_for_transitions_through_phrase(self) -> None:
        """Catches the simple_task ST-019 wording 'transitions through declared state machine'."""
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        entity = self._make_task_entity()
        story = self._make_story(
            "ST-019", then=["Task.status transitions through declared state machine"]
        )
        gaps = self._gaps_for(surface, entity, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert outcome_gaps == []

    def test_edit_still_flags_transition_outcome(self) -> None:
        """Edit surfaces ARE where transitions fire — outcome gap is real if
        the surface doesn't render the field that gets updated."""
        surface = _make_surface(
            name="task_edit",
            entity_ref="Task",
            mode=SurfaceMode.EDIT,
            field_names=["title"],
        )
        entity = self._make_task_entity()
        story = self._make_story("ST-008", then=["Task.status becomes 'in_progress'"])
        gaps = self._gaps_for(surface, entity, [story])
        outcome_gaps = [g for g in gaps if g.category == FidelityGapCategory.STORY_OUTCOME_MISSING]
        assert len(outcome_gaps) == 1


class TestStatusChangedTriggerExclusion:
    """Closes #877 Option A: stories with `trigger: status_changed` describe
    state transitions and cannot fire from a `mode: create` surface (the
    entity is being created, not transitioned). `_match_stories_to_surfaces`
    filters such stories out of create-surface matches so the precondition /
    outcome checks never see them.

    Edit / detail / list surfaces continue to match status_changed stories
    so the lifecycle is visible somewhere in the fidelity report — the bug
    is the create-surface attribution specifically."""

    def _story(self, story_id: str, trigger: StoryTrigger, *, scope=None) -> StorySpec:
        return StorySpec(
            story_id=story_id,
            title=f"Story {story_id}",
            actor="admin",
            scope=scope or ["Task"],
            status=StoryStatus.ACCEPTED,
            trigger=trigger,
            given=[StoryCondition(expression="Task.status is 'todo'", field_path="Task.status")],
            when=[],
            then=[
                StoryCondition(
                    expression="Task.status becomes 'in_progress'", field_path="Task.status"
                )
            ],
            unless=[],
        )

    def test_status_changed_excluded_from_create(self) -> None:
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        story = self._story("ST-008", StoryTrigger.STATUS_CHANGED)
        matched = _match_stories_to_surfaces(surface, [story])
        assert matched == []

    def test_user_click_still_matches_create(self) -> None:
        """user_click stories DO apply to create surfaces (e.g. 'user
        clicks Save to create Task'). Trigger filter is narrow."""
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        story = self._story("ST-100", StoryTrigger.USER_CLICK)
        matched = _match_stories_to_surfaces(surface, [story])
        assert matched == [story]

    def test_form_submitted_still_matches_create(self) -> None:
        """form_submitted is THE creation trigger — must continue to match."""
        surface = _make_surface(
            name="task_create",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            field_names=["title"],
        )
        story = self._story("ST-101", StoryTrigger.FORM_SUBMITTED)
        matched = _match_stories_to_surfaces(surface, [story])
        assert matched == [story]

    def test_status_changed_still_matches_edit(self) -> None:
        """Edit surfaces are exactly where transitions fire — they must
        continue to match status_changed stories so missing-field gaps on
        the edit form are still surfaced."""
        surface = _make_surface(
            name="task_edit",
            entity_ref="Task",
            mode=SurfaceMode.EDIT,
            field_names=["title"],
        )
        story = self._story("ST-008", StoryTrigger.STATUS_CHANGED)
        matched = _match_stories_to_surfaces(surface, [story])
        assert matched == [story]

    def test_status_changed_still_matches_list_and_detail(self) -> None:
        """List and detail surfaces continue to match — they show transition
        OUTCOMES (the new state) which is part of the lifecycle reading
        even though they don't fire the transition themselves."""
        for mode in (SurfaceMode.LIST, SurfaceMode.VIEW):
            surface = _make_surface(
                name=f"task_{mode.value}",
                entity_ref="Task",
                mode=mode,
                field_names=["title", "status"],
            )
            story = self._story("ST-008", StoryTrigger.STATUS_CHANGED)
            matched = _match_stories_to_surfaces(surface, [story])
            assert matched == [story], f"mode={mode} should still match"
