"""
Unit tests for the fidelity scorer.

Everything is driven through the public ``score_surface_fidelity`` /
``score_appspec_fidelity`` entry points and asserts the exact gaps emitted.

Story embodiment (scope, given/when/then/unless, create-mode suppression,
trigger filtering) is read off the ``story`` dimension of the score.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.fidelity_scorer import score_appspec_fidelity, score_surface_fidelity
from dazzle.core.ir.fidelity import FidelityGap, FidelityGapCategory
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.stories import (
    StoryCondition,
    StoryException,
    StorySpec,
    StoryStatus,
    StoryTrigger,
)
from dazzle.core.ir.surfaces import SurfaceMode

_CAT = FidelityGapCategory


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
    trigger: StoryTrigger = StoryTrigger.USER_CLICK,
) -> StorySpec:
    return StorySpec(
        story_id=story_id,
        title=title,
        persona="User",
        trigger=trigger,
        entities=scope or ["Task"],
        given=given or [],
        when=when or [],
        then=then or [],
        unless=unless or [],
        status=StoryStatus.ACCEPTED,
    )


def _make_entity(fields: list[FieldSpec]) -> MagicMock:
    """Create a mock EntitySpec with real FieldSpec objects."""
    entity = MagicMock()
    entity.fields = fields
    return entity


def _field(name: str, kind: FieldTypeKind, **type_kwargs: object) -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=kind, **type_kwargs))


def _gaps(
    surface: MagicMock,
    html: str,
    *,
    entity: MagicMock | None = None,
    stories: list[StorySpec] | None = None,
    category: FidelityGapCategory | None = None,
    dimension: str | None = None,
) -> list[FidelityGap]:
    """Gaps from the public scorer, optionally narrowed by category / dimension."""
    score = score_surface_fidelity(surface, entity, html, None, stories)
    return [
        g
        for g in score.gaps
        if (category is None or g.category == category)
        and (dimension is None or g.dimension == dimension)
    ]


def _form(inner: str, *, method: str = "hx-post") -> str:
    return f'<form {method}="/x">{inner}<button type="submit">Save</button></form>'


def _money(name: str, *, hidden: bool = True) -> str:
    carriers = (
        f'<input type="hidden" name="{name}_minor" data-dz-money-minor>'
        f'<input type="hidden" name="{name}_currency" data-dz-money-currency value="GBP">'
        if hidden
        else ""
    )
    return (
        f'<div data-dz-money="{name}" data-dz-currency="GBP" data-dz-scale="2">'
        f'<input type="text" inputmode="decimal" data-dz-money-display>{carriers}</div>'
    )


# ── Story embodiment ──────────────────────────────────────────────────

_STATUS_GIVEN = StoryCondition(expression="Task.status is 'open'", field_path="Task.status")
_STATUS_TODO = StoryCondition(expression="Task.status is 'todo'", field_path="Task.status")
_STATUS_IN_PROGRESS = StoryCondition(
    expression="Task.status is 'in_progress'", field_path="Task.status"
)
_STATUS_BECOMES = StoryCondition(
    expression="Task.status becomes 'in_progress'", field_path="Task.status"
)
_STATUS_TRANSITIONS = StoryCondition(
    expression="Task.status transitions through declared state machine",
    field_path="Task.status",
)
_COMPLETED_AT = StoryCondition(
    expression="Task.completed_at is recorded", field_path="Task.completed_at"
)
_CONTACT_PHONE = StoryCondition(expression="Contact.phone populated", field_path="Contact.phone")
_ASSIGNEE_MISSING = StoryException(
    condition="Task.assignee is missing", then_outcomes=["Error is displayed"]
)
_CLICK_COMPLETE = StoryCondition(expression="user clicks Complete button")

_BUTTON_HTML = "<div><button>Go</button></div>"
_FORM_HTML = "<form><input name='title'></form>"
_PRECOND = (_CAT.STORY_PRECONDITION_MISSING, "given[status]")
_OUTCOME = (_CAT.STORY_OUTCOME_MISSING, "then[status]")
_NO_STORIES = {"__none__": True}


def _task_entity(status_default: str = "todo") -> MagicMock:
    return _make_entity(
        [
            _field("title", FieldTypeKind.STR),
            FieldSpec(
                name="status", type=FieldType(kind=FieldTypeKind.ENUM), default=status_default
            ),
        ]
    )


def _case(
    case_id: str,
    gaps: list[tuple[FidelityGapCategory, str]],
    *,
    surface: dict[str, Any] | None = None,
    story: dict[str, Any] | None = None,
    html: str = _BUTTON_HTML,
    entity: bool = False,
) -> object:
    return pytest.param(surface or {}, story or {}, html, entity, gaps, id=case_id)


@pytest.mark.parametrize(
    ("surface_kwargs", "story_kwargs", "html", "with_entity", "expected"),
    [
        # -- story-to-surface matching (scope, then title fallback) --
        _case(
            "match-by-scope",
            [_PRECOND],
            surface={"field_names": ["title"]},
            story={"scope": ["Task", "User"], "given": [_STATUS_GIVEN]},
        ),
        _case(
            "different-scope-no-match",
            [],
            surface={"field_names": ["title"]},
            story={"scope": ["Order"], "title": "User places order", "given": [_STATUS_GIVEN]},
        ),
        # _make_story turns an empty scope into ["Task"], so an off-entity scope
        # is what forces the title fallback branch.
        _case(
            "title-fallback-match",
            [_PRECOND],
            surface={"field_names": ["title"]},
            story={"scope": ["Project"], "title": "User completes Task", "given": [_STATUS_GIVEN]},
        ),
        _case(
            "no-entity-ref-no-match",
            [],
            surface={"entity_ref": None, "field_names": ["title"]},
            story={"given": [_STATUS_GIVEN]},
        ),
        _case("no-stories-no-gaps", [], story=_NO_STORIES),
        # Multi-entity scope is no longer a fidelity gap.
        _case("scope-mismatch-not-reported", [], story={"scope": ["Task", "Project"]}),
        _case("scope-fully-matched", [], story={"scope": ["Task"]}),
        # -- given conditions --
        _case(
            "given-field-missing",
            [_PRECOND],
            surface={"field_names": ["title"]},
            story={"given": [_STATUS_GIVEN]},
        ),
        _case(
            "given-field-present",
            [],
            surface={"field_names": ["title", "status"]},
            story={"given": [_STATUS_GIVEN]},
        ),
        # Given-condition on a different entity does not flag the surface (#481).
        _case(
            "given-cross-entity-skipped-481",
            [],
            surface={"name": "checklist_list", "entity_ref": "Checklist", "field_names": ["title"]},
            story={"scope": ["Checklist"], "given": [_CONTACT_PHONE]},
        ),
        _case(
            "given-no-field-path-skipped",
            [],
            surface={"field_names": ["title"]},
            story={"given": [StoryCondition(expression="User is logged in", field_path=None)]},
        ),
        # -- when triggers --
        _case(
            "when-no-action-elements",
            [(_CAT.STORY_TRIGGER_MISSING, "when[ST-001]")],
            story={"when": [_CLICK_COMPLETE]},
            html="<div>No buttons here</div>",
        ),
        _case(
            "when-matching-button",
            [],
            story={"when": [_CLICK_COMPLETE]},
            html="<div><button>Complete</button></div>",
        ),
        # -- then outcomes --
        _case(
            "then-field-missing",
            [(_CAT.STORY_OUTCOME_MISSING, "then[completed_at]")],
            surface={"field_names": ["title"]},
            story={"then": [_COMPLETED_AT]},
        ),
        _case(
            "then-field-in-surface",
            [],
            surface={"field_names": ["title", "completed_at"]},
            story={"then": [_COMPLETED_AT]},
        ),
        _case(
            "then-field-in-rendered-text",
            [],
            surface={"field_names": ["title"]},
            story={"then": [_COMPLETED_AT]},
            html="<div>completed_at: 2024-01-01</div>",
        ),
        # Outcome on a different entity does not flag the surface (#481).
        _case(
            "then-cross-entity-skipped-481",
            [],
            surface={
                "name": "checklist_create",
                "entity_ref": "Checklist",
                "field_names": ["title"],
            },
            story={"scope": ["Checklist"], "then": [_CONTACT_PHONE]},
            html="<div><button>Save</button></div>",
        ),
        # -- unless branches --
        _case(
            "unless-missing-handling",
            [(_CAT.MISSING_ACTION_AFFORDANCE, "unless[ST-001]")],
            story={"unless": [_ASSIGNEE_MISSING]},
        ),
        _case(
            "unless-text-present",
            [],
            story={"unless": [_ASSIGNEE_MISSING]},
            html="<div><button>Go</button><span>assignee missing</span></div>",
        ),
        # -- mode:create suppression (#877 Option B) --
        _case(
            "create-skips-precondition-when-default-matches",
            [],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={"given": [_STATUS_TODO]},
            html=_FORM_HTML,
            entity=True,
        ),
        _case(
            "create-flags-precondition-when-default-differs",
            [_PRECOND],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={"given": [_STATUS_IN_PROGRESS]},
            html=_FORM_HTML,
            entity=True,
        ),
        _case(
            "edit-flags-precondition-even-when-default-matches",
            [_PRECOND],
            surface={"mode": SurfaceMode.EDIT, "field_names": ["title"]},
            story={"given": [_STATUS_TODO]},
            html=_FORM_HTML,
            entity=True,
        ),
        _case(
            "create-skips-outcome-for-becomes-transition",
            [],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={"then": [_STATUS_BECOMES]},
            html=_FORM_HTML,
            entity=True,
        ),
        _case(
            "create-skips-outcome-for-transitions-through-phrase",
            [],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={"then": [_STATUS_TRANSITIONS]},
            html=_FORM_HTML,
            entity=True,
        ),
        _case(
            "edit-flags-transition-outcome",
            [_OUTCOME],
            surface={"mode": SurfaceMode.EDIT, "field_names": ["title"]},
            story={"then": [_STATUS_BECOMES]},
            html=_FORM_HTML,
            entity=True,
        ),
        # -- status_changed stories never attach to create surfaces (#877 Option A) --
        _case(
            "status-changed-excluded-from-create",
            [],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={
                "trigger": StoryTrigger.STATUS_CHANGED,
                "given": [_STATUS_TODO],
                "then": [_STATUS_BECOMES],
            },
        ),
        _case(
            "user-click-still-matches-create",
            [_PRECOND],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={
                "trigger": StoryTrigger.USER_CLICK,
                "given": [_STATUS_TODO],
                "then": [_STATUS_BECOMES],
            },
        ),
        _case(
            "form-submitted-still-matches-create",
            [_PRECOND],
            surface={"mode": SurfaceMode.CREATE, "field_names": ["title"]},
            story={
                "trigger": StoryTrigger.FORM_SUBMITTED,
                "given": [_STATUS_TODO],
                "then": [_STATUS_BECOMES],
            },
        ),
        # Edit / list / detail surfaces keep status_changed stories: the lifecycle
        # must stay visible somewhere in the fidelity report.
        *[
            _case(
                f"status-changed-still-matches-{mode.value}",
                [_PRECOND, _OUTCOME],
                surface={"mode": mode, "field_names": ["title"]},
                story={
                    "trigger": StoryTrigger.STATUS_CHANGED,
                    "given": [_STATUS_TODO],
                    "then": [_STATUS_BECOMES],
                },
            )
            for mode in (SurfaceMode.EDIT, SurfaceMode.LIST, SurfaceMode.VIEW)
        ],
    ],
)
def test_story_embodiment_gaps(
    surface_kwargs: dict[str, Any],
    story_kwargs: dict[str, Any],
    html: str,
    with_entity: bool,
    expected: list[tuple[FidelityGapCategory, str]],
) -> None:
    """The story dimension emits exactly the expected (category, target) gaps."""
    surface = _make_surface(**surface_kwargs)
    stories = [] if story_kwargs.get("__none__") else [_make_story(**story_kwargs)]
    entity = _task_entity() if with_entity else None

    gaps = _gaps(surface, html, entity=entity, stories=stories, dimension="story")

    assert [(g.category, g.target) for g in gaps] == expected
    for g in gaps:
        assert g.surface_name == surface.name
        assert g.severity == ("minor" if g.category == _CAT.MISSING_ACTION_AFFORDANCE else "major")


def test_story_gap_message_names_story_and_condition() -> None:
    """A precondition gap names the field, surface, story id and condition."""
    surface = _make_surface(field_names=["title"])
    (gap,) = _gaps(
        surface, _BUTTON_HTML, stories=[_make_story(given=[_STATUS_GIVEN])], dimension="story"
    )
    assert gap.expected == "Field 'status' for precondition"
    assert gap.actual == "field not present on surface"
    assert "task_list" in gap.recommendation
    assert "ST-001" in gap.recommendation
    assert "Task.status is 'open'" in gap.recommendation


@pytest.mark.parametrize("has_story", [True, False], ids=["appspec-stories", "empty-stories"])
def test_appspec_stories_feed_surface_scoring(has_story: bool) -> None:
    """score_appspec_fidelity scores against appspec.stories, with no fallback."""
    surface = _make_surface(field_names=["title"])
    appspec = MagicMock()
    appspec.surfaces = [surface]
    appspec.stories = [_make_story(given=[_STATUS_GIVEN])] if has_story else []
    appspec.get_entity = lambda ref: None

    report = score_appspec_fidelity(appspec, {("task_list", "Task"): _BUTTON_HTML})

    (score,) = report.surface_scores
    story_targets = [g.target for g in score.gaps if g.dimension == "story"]
    assert story_targets == (["given[status]"] if has_story else [])


# ── Form structure: money expansion, input types ──────────────────────

_TITLE = _field("title", FieldTypeKind.STR, max_length=200)
_PRICE = _field("price", FieldTypeKind.MONEY, currency_code="GBP")


@pytest.mark.parametrize(
    ("field_names", "entity_fields", "inner", "missing"),
    [
        pytest.param(
            ["title", "price"],
            [_TITLE, _PRICE],
            '<input name="title" type="text">' + _money("price"),
            [],
            id="money-widget-with-hidden-carriers",
        ),
        # data-dz-money alone satisfies the field check.
        pytest.param(
            ["price"], [_PRICE], _money("price", hidden=False), [], id="money-data-attribute-only"
        ),
        pytest.param(
            ["description", "amount", "tax"],
            [
                _field("description", FieldTypeKind.STR, max_length=500),
                _field("amount", FieldTypeKind.MONEY, currency_code="GBP"),
                _field("tax", FieldTypeKind.MONEY, currency_code="GBP"),
            ],
            '<input name="description" type="text">' + _money("amount") + _money("tax"),
            [],
            id="mixed-money-and-regular-fields",
        ),
        # The entity's money field expands to <name>_minor / <name>_currency inputs.
        pytest.param(
            ["title", "price"],
            [_TITLE, _PRICE],
            '<input name="title"><input name="price_minor"><input name="price_currency">',
            [],
            id="money-expands-to-minor-and-currency-inputs",
        ),
        pytest.param(
            ["title", "price"],
            [_TITLE, _PRICE],
            '<input name="title"><input name="price_minor">',
            ["input[price_currency]"],
            id="money-expansion-missing-currency-input",
        ),
        # entity=None: the money field name is not expanded -> gap reported.
        pytest.param(
            ["price", "title"],
            None,
            '<input name="title"><input name="price_minor"><input name="price_currency">',
            ["input[price]"],
            id="no-entity-no-expansion",
        ),
        pytest.param(
            ["title", "count"],
            [_TITLE, _field("count", FieldTypeKind.INT)],
            '<input name="title"><input name="count">',
            [],
            id="non-money-unchanged",
        ),
    ],
)
def test_form_missing_field_gaps(
    field_names: list[str],
    entity_fields: list[FieldSpec] | None,
    inner: str,
    missing: list[str],
) -> None:
    """MISSING_FIELD gaps for a create form respect money-field expansion."""
    surface = _make_surface(name="p_create", mode=SurfaceMode.CREATE, field_names=field_names)
    entity = _make_entity(entity_fields) if entity_fields is not None else None

    gaps = _gaps(surface, _form(inner), entity=entity, category=_CAT.MISSING_FIELD)

    assert [g.target for g in gaps] == missing


@pytest.mark.parametrize(
    ("mode", "field_name", "field_type", "inner", "mismatched"),
    [
        # -- no INCORRECT_INPUT_TYPE gap --
        pytest.param(
            SurfaceMode.CREATE,
            "price",
            FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"),
            _money("price"),
            False,
            id="money-hidden-inputs-not-false-positive",
        ),
        # Regression guard for #825: FLOAT was absent from FIELD_TYPE_TO_INPUT and
        # fell through to the text default, producing a spurious gap.
        pytest.param(
            SurfaceMode.CREATE,
            "temperature",
            FieldType(kind=FieldTypeKind.FLOAT),
            '<input type="number" name="temperature">',
            False,
            id="float-renders-as-number-825",
        ),
        pytest.param(
            SurfaceMode.CREATE,
            "file_url",
            FieldType(kind=FieldTypeKind.FILE),
            '<input type="file" name="file_url">',
            False,
            id="file-input-type-file",
        ),
        # File fields are skipped in input-type checks (#579): custom widgets.
        pytest.param(
            SurfaceMode.CREATE,
            "file_url",
            FieldType(kind=FieldTypeKind.FILE),
            '<input type="text" name="file_url">',
            False,
            id="file-field-skipped-579",
        ),
        # Widget-rendered inputs satisfy the expected DSL type (#779).
        pytest.param(
            SurfaceMode.EDIT,
            "volume",
            FieldType(kind=FieldTypeKind.INT),
            '<div data-dz-widget="range-tooltip">'
            '<input name="volume" type="range" min="0" max="100"></div>',
            False,
            id="range-slider-on-int-779",
        ),
        pytest.param(
            SurfaceMode.EDIT,
            "opacity",
            FieldType(kind=FieldTypeKind.DECIMAL),
            '<input name="opacity" type="range" min="0" max="1" step="0.01">',
            False,
            id="range-slider-on-decimal-779",
        ),
        pytest.param(
            SurfaceMode.CREATE,
            "body",
            FieldType(kind=FieldTypeKind.STR, max_length=5000),
            '<div data-dz-widget="richtext"><div class="quill-editor"></div>'
            '<input type="hidden" name="body"></div>',
            False,
            id="richtext-hidden-input-on-str-779",
        ),
        pytest.param(
            SurfaceMode.CREATE,
            "category",
            FieldType(kind=FieldTypeKind.ENUM),
            '<div data-dz-widget="richtext"><input type="hidden" name="category"></div>',
            False,
            id="richtext-hidden-input-on-enum-779",
        ),
        # Closes #878: search_select carries the str value in a hidden input next to
        # a visible search box; equivalence depends on the wrapper's data-dz-widget.
        pytest.param(
            SurfaceMode.CREATE,
            "manufacturer",
            FieldType(kind=FieldTypeKind.STR, max_length=200),
            '<div class="relative w-full" data-dz-widget="search_select">'
            '<input type="hidden" name="manufacturer" id="field-manufacturer" />'
            '<input type="text" id="search-input-manufacturer" role="combobox" /></div>',
            False,
            id="search-select-widget-satisfies-str-878",
        ),
        # -- exactly one INCORRECT_INPUT_TYPE gap --
        pytest.param(
            SurfaceMode.CREATE,
            "starts_on",
            FieldType(kind=FieldTypeKind.DATE),
            '<input name="starts_on" type="text" data-dz-widget="mysterywidget">',
            True,
            id="unknown-widget-still-flags-mismatch",
        ),
        pytest.param(
            SurfaceMode.CREATE,
            "starts_on",
            FieldType(kind=FieldTypeKind.DATE),
            '<input name="starts_on" type="text">',
            True,
            id="plain-mismatch-without-widget-flags",
        ),
        # Counter-test: hidden str input with no widget marker is a real defect.
        pytest.param(
            SurfaceMode.CREATE,
            "manufacturer",
            FieldType(kind=FieldTypeKind.STR, max_length=200),
            '<input type="hidden" name="manufacturer" />',
            True,
            id="search-select-without-marker-still-flags",
        ),
    ],
)
def test_form_input_type_gaps(
    mode: SurfaceMode,
    field_name: str,
    field_type: FieldType,
    inner: str,
    mismatched: bool,
) -> None:
    """Input-type mismatches are flagged unless a known-good widget/skip rule applies."""
    surface = _make_surface(name="f_form", mode=mode, field_names=[field_name])
    entity = _make_entity([FieldSpec(name=field_name, type=field_type)])
    method = "hx-put" if mode == SurfaceMode.EDIT else "hx-post"

    gaps = _gaps(
        surface, _form(inner, method=method), entity=entity, category=_CAT.INCORRECT_INPUT_TYPE
    )

    assert [g.target for g in gaps] == ([f"input[{field_name}]"] if mismatched else [])


# ── score_appspec_fidelity: composite rendered_pages key (#828) ───────


def test_colliding_surface_names_scored_independently() -> None:
    """Regression guard for #828: two surfaces sharing a name but targeting
    different entities score against their own HTML, not each other's."""
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
    entities = {
        "ManuscriptFeedback": _make_entity(
            [_field("manuscript", FieldTypeKind.STR), _field("summary", FieldTypeKind.STR)]
        ),
        "FeedbackReport": _make_entity(
            [_field("category", FieldTypeKind.STR), _field("severity", FieldTypeKind.STR)]
        ),
    }
    appspec = MagicMock()
    appspec.surfaces = [surface_a, surface_b]
    appspec.stories = []
    appspec.get_entity = entities.get

    rendered = {
        ("feedback_create", "ManuscriptFeedback"): _form(
            '<input name="manuscript"><input name="summary">'
        ),
        ("feedback_create", "FeedbackReport"): _form(
            '<input name="category"><input name="severity">'
        ),
    }

    report = score_appspec_fidelity(appspec, rendered)

    # Both surfaces scored (no silent drop), and neither sees ghost missing-field gaps.
    assert len(report.surface_scores) == 2
    for score in report.surface_scores:
        assert [g for g in score.gaps if g.category == _CAT.MISSING_FIELD] == []


def test_missing_entity_ref_uses_empty_string_key() -> None:
    """Surface with no entity_ref looks up by ``(name, "")``."""
    surface = _make_surface(
        name="dashboard", entity_ref=None, mode=SurfaceMode.LIST, field_names=["title"]
    )
    appspec = MagicMock()
    appspec.surfaces = [surface]
    appspec.stories = []
    appspec.get_entity = lambda ref: None

    report = score_appspec_fidelity(appspec, {("dashboard", ""): "<div>stub</div>"})

    assert [s.surface_name for s in report.surface_scores] == ["dashboard"]


# ── Interaction fidelity: search_select error handler ─────────────────


@pytest.mark.parametrize(
    ("error_marker", "expect_flagged"),
    [
        pytest.param('aria-invalid="true"', False, id="aria-invalid"),
        pytest.param('class="border-[hsl(var(--destructive))]"', False, id="destructive-token"),
        pytest.param('class="text-error"', False, id="legacy-text-error"),
        pytest.param("", True, id="no-error-marker"),
    ],
)
def test_search_select_error_handler_check(error_marker: str, expect_flagged: bool) -> None:
    """The error-handler check accepts the post-DaisyUI design-token / ARIA wiring,
    not just the legacy ``text-error`` class."""
    # Mirrors the real fragments/search_select.html shape; only the marker varies.
    html = f"""
    <div class="relative w-full">
      <input type="hidden" name="company" id="field-company" {error_marker} />
      <input type="text" id="search-input-company" role="combobox"
             hx-get="/_dazzle/fragments/search"
             hx-trigger="keyup changed delay:400ms"
             hx-target="#search-results-company"
             hx-indicator="#search-spinner-company" />
      <div id="search-results-company" role="listbox">
        Type at least 3 characters to search...
      </div>
    </div>
    """
    surface = _make_surface(
        name="contact_create",
        entity_ref="Contact",
        mode=SurfaceMode.CREATE,
        field_names=["company"],
    )

    gaps = _gaps(surface, html, dimension="interaction")

    if expect_flagged:
        assert [(g.category, g.severity, g.target) for g in gaps] == [
            (_CAT.MISSING_ERROR_HANDLER, "minor", "search_select")
        ]
    else:
        assert gaps == []


# ── Semantic fidelity: hidden `required` is ignored (2115-2117) ───────

_SEARCH_SELECT = (
    '<div data-dz-widget="search_select">'
    '<input type="hidden" name="company" value="">{visible}</div>'
)


@pytest.mark.parametrize(
    ("field_name", "inner", "flagged"),
    [
        pytest.param(
            "company",
            _SEARCH_SELECT.format(visible='<input type="text" required aria-required="true">'),
            [],
            id="hidden-carrier-without-required-not-a-gap-2115",
        ),
        # The hidden skip must not hide a missing visible `required`.
        pytest.param(
            "company",
            _SEARCH_SELECT.format(visible='<input type="text">'),
            ["input[company]"],
            id="hidden-carrier-without-visible-required-is-a-gap-2117",
        ),
        pytest.param(
            "title",
            '<input type="text" name="title">',
            ["input[title]"],
            id="visible-named-without-required-is-a-gap",
        ),
    ],
)
def test_required_attribute_on_visible_control(
    field_name: str, inner: str, flagged: list[str]
) -> None:
    surface = _make_surface(
        name="ticket_create",
        entity_ref="Ticket",
        mode=SurfaceMode.CREATE,
        field_names=[field_name],
    )
    entity = _make_entity(
        [
            FieldSpec(
                name=field_name,
                type=FieldType(kind=FieldTypeKind.STR, max_length=80),
                modifiers=[FieldModifier.REQUIRED],
            )
        ]
    )

    gaps = _gaps(
        surface,
        f'<form hx-post="/tickets">{inner}</form>',
        entity=entity,
        category=_CAT.MISSING_VALIDATION_ATTRIBUTE,
    )

    assert [g.target for g in gaps] == flagged
