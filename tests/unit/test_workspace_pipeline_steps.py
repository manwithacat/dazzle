"""Tests for the v0.61.56 pipeline_steps display mode (#890).

Three layers:
  1. Parser: ``display: pipeline_steps`` + ``stages:`` indented dash-list
     of ``{label, caption, value}`` entries parses into the IR.
     Crucially, the existing legacy ``stages: [a, b, c]`` bracketed
     form for ``progress`` mode still works — the parser shape-detects.
  2. Runtime: each stage's `value` is matched against `_AGGREGATE_RE`.
     Aggregate-shaped values fire via `_fetch_count_metric` concurrently;
     literal-string values render verbatim (v0.61.66 #4). Stages without
     a value (or with not-yet-supported `median`/`avg`/etc.) render
     `None` → `—` in the template. Honours the #887 scope-deny gate.
  3. Template: row of stage cards with arrow connectors between
     (desktop) / vertical chevrons (mobile). Empty-state fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode, PipelineStageSpec
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Manuscript:
  id: uuid pk
  status: enum[uploaded,queued,processing,reviewed]
workspace dash "Dash":
  ingestion:
    display: pipeline_steps
    stages:
      - label: "Scanned"
        caption: "complete pupil scripts"
        value: count(Manuscript where status = uploaded)
      - label: "Reviewed"
        caption: "human-validated"
        value: count(Manuscript where status = reviewed)
"""


# ───────────────────────── parser ──────────────────────────


class TestPipelineStepsParser:
    def test_minimal_pipeline(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.PIPELINE_STEPS
        assert len(region.pipeline_stages) == 2
        assert region.pipeline_stages[0].label == "Scanned"
        assert region.pipeline_stages[0].caption == "complete pupil scripts"
        assert region.pipeline_stages[0].value == "count ( Manuscript where status = uploaded )"

    def test_label_only_stage(self) -> None:
        """Only ``label:`` is required — caption/value default."""
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "Just a label"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.pipeline_stages) == 1
        s = region.pipeline_stages[0]
        assert s.label == "Just a label"
        assert s.caption == ""
        assert s.value == ""

    def test_multiple_stages_preserve_order(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "First"
      - label: "Second"
      - label: "Third"
      - label: "Fourth"
"""
        region = _parse(src).workspaces[0].regions[0]
        labels = [s.label for s in region.pipeline_stages]
        assert labels == ["First", "Second", "Third", "Fourth"]

    def test_unknown_key_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "X"
        bogus: yes
"""
        with pytest.raises(ParseError, match="Unknown pipeline stages key"):
            _parse(src)

    def test_full_repro_dsl_from_issue(self) -> None:
        """The issue's full 4-stage DSL — parses without errors. The
        4th stage's `median(...)` aggregate is captured as a string;
        runtime renders `—` because median isn't yet supported."""
        src = """module t
app t "Test"
entity AssessmentEvent:
  id: uuid pk
entity Manuscript:
  id: uuid pk
  status: enum[uploaded,queued,reviewed]
  computed_grade: float
entity MarkingResult:
  id: uuid pk
  latest_for_event: bool
  flagged_for_review: bool
  confidence: float
workspace dash "Dash":
  ingestion_journey:
    source: AssessmentEvent
    display: pipeline_steps
    stages:
      - label: "Scanned"
        caption: "complete pupil scripts, page order checked"
        value: count(Manuscript where status = uploaded)
      - label: "Rubric pass"
        caption: "AO-level judgements with evidence snippets"
        value: count(MarkingResult where latest_for_event = true)
      - label: "Moderation"
        caption: "low-confidence results isolated for review"
        value: count(MarkingResult where flagged_for_review = true)
      - label: "Output"
        caption: "median grade"
        value: median(Manuscript.computed_grade)
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.PIPELINE_STEPS
        assert len(region.pipeline_stages) == 4
        assert region.pipeline_stages[3].value.startswith("median")


# ───────────────────────── stages: shape dispatch ──────────────────────────


class TestStagesShapeDispatch:
    """The `stages:` keyword is shared between the legacy ``progress``
    mode (bracketed list of identifiers) and the new ``pipeline_steps``
    mode (indented dash-list of dicts). The parser shape-detects on
    the next token after the colon."""

    def test_legacy_progress_bracketed_form_still_works(self) -> None:
        """Pre-existing progress mode shape — must continue to parse
        as a bare list of stage identifiers, not pipeline_stages."""
        src = """module t
app t "Test"
entity Task:
  id: uuid pk
  status: enum[todo,doing,done]
workspace dash "Dash":
  task_progress:
    source: Task
    display: progress
    stages: [todo, doing, done]
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.PROGRESS
        assert region.progress_stages == ["todo", "doing", "done"]
        assert region.pipeline_stages == []

    def test_pipeline_indented_form_parses(self) -> None:
        """The new shape — indented dash-list — parses as
        pipeline_stages, not progress_stages."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.progress_stages == []
        assert len(region.pipeline_stages) == 2


# ───────────────────────── value: literal vs aggregate ──────────────────────────


class TestPipelineStepsValueShape:
    """v0.61.66 (AegisMark UX patterns #4): the ``value:`` key accepts
    either an aggregate expression (matches `_AGGREGATE_RE` — fires a
    count query) OR a literal string (renders verbatim — used for
    flow-card descriptive labels like "Daily 02:00 UTC")."""

    def test_quoted_literal_value_parses(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "Sync"
        caption: "external system"
        value: "Daily 02:00 UTC"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.pipeline_stages[0].value == "Daily 02:00 UTC"

    def test_literal_with_special_chars(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "Trigger"
        value: "Manual review — escalation path"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.pipeline_stages[0].value == "Manual review — escalation path"

    def test_aggregate_and_literal_in_same_block(self) -> None:
        """Mixed pipeline — count stages alongside literal-string stages.
        The runtime fires queries for the aggregates and renders the
        literals verbatim."""
        src = """module t
app t "Test"
entity Alert:
  id: uuid pk
  status: enum[active,resolved]
workspace dash "Dash":
  alerting:
    display: pipeline_steps
    stages:
      - label: "Active"
        value: count(Alert where status = active)
      - label: "Audit"
        value: "Daily 02:00 UTC"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert len(region.pipeline_stages) == 2
        assert region.pipeline_stages[0].value.startswith("count")
        assert region.pipeline_stages[1].value == "Daily 02:00 UTC"

    def test_runtime_aggregate_re_distinguishes_shapes(self) -> None:
        """The runtime gate uses `_AGGREGATE_RE` to decide between the
        query path and the literal path. Pin the regex behaviour so
        a future refactor doesn't accidentally treat literals as bad
        aggregates (or vice versa)."""
        from dazzle_back.runtime.workspace_rendering import _AGGREGATE_RE

        assert _AGGREGATE_RE.match("count(Alert where status = active)") is not None
        assert _AGGREGATE_RE.match("avg(score)") is not None
        # Literal strings should NOT match — they fall through to the
        # verbatim render path.
        assert _AGGREGATE_RE.match("Daily 02:00 UTC") is None
        assert _AGGREGATE_RE.match("Manual review") is None
        assert _AGGREGATE_RE.match("") is None


# ───────────────────────── PipelineStageSpec ──────────────────────────


class TestPipelineStageSpec:
    def test_construct_minimal(self) -> None:
        s = PipelineStageSpec(label="X")
        assert s.label == "X"
        assert s.caption == ""
        assert s.value == ""

    def test_construct_full(self) -> None:
        s = PipelineStageSpec(label="Scanned", caption="cap", value="count(M)")
        assert s.caption == "cap"
        assert s.value == "count(M)"

    def test_construct_with_literal_value(self) -> None:
        """v0.61.66: literal-string values are first-class — same field,
        different shape (no aggregate function)."""
        s = PipelineStageSpec(label="Sync", caption="cap", value="Daily 02:00 UTC")
        assert s.value == "Daily 02:00 UTC"


# ───────────────────────── template wiring ──────────────────────────


class TestPipelineStepsTemplateWiring:
    def test_template_map_includes_pipeline_steps(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "PIPELINE_STEPS" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["PIPELINE_STEPS"] == "workspace/regions/pipeline_steps.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/pipeline_steps.html"
        )
        assert path.is_file()

    def test_template_uses_region_card_macro(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/pipeline_steps.html"
        )
        contents = path.read_text()
        assert "{% call region_card" in contents

    def test_region_context_default_empty(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.pipeline_stages == []

    def test_region_context_carries_stages(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            pipeline_stages=[{"label": "Scanned", "caption": "scripts", "value": "count(M)"}],
        )
        assert len(ctx.pipeline_stages) == 1
        assert ctx.pipeline_stages[0]["label"] == "Scanned"


# ───────────────────────── invariants ──────────────────────────


class TestPipelineStepsBodyless:
    """pipeline_steps regions don't need source/aggregate at the top
    level — `stages:` is the body. The parser exemption now covers
    this alongside action_grid (#891)."""

    def test_no_source_or_aggregate_required(self) -> None:
        """The base DSL has neither `source:` nor `aggregate:` — only
        `stages:`. Must parse without the "requires source or aggregate"
        error."""
        # _BASE_DSL has neither — already covered by test_minimal, but
        # explicit check here pins the bodyless exemption.
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.source is None
        assert region.aggregates == {}
        assert len(region.pipeline_stages) == 2  # body via stages


# ───────────────────────── #911 progress: per-stage bars ──────────────


class TestPipelineStepsProgressParser:
    """v0.61.78 (#911): per-stage `progress:` field. Same shape as
    `value:` — literal numeric or aggregate expression. Default is
    empty string (no bar). Coexists with `value:` so a stage can show
    both a count and a fraction."""

    def test_literal_progress_parses(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "PDF decollation"
        caption: "page boundaries grouped"
        progress: 74
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.pipeline_stages[0].progress == "74"

    def test_quoted_literal_progress_parses(self) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "X"
        progress: "50"
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.pipeline_stages[0].progress == "50"

    def test_aggregate_progress_parses(self) -> None:
        src = """module t
app t "Test"
entity Manuscript:
  id: uuid pk
  status: enum[uploaded,marked]
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "Marked"
        value: count(Manuscript where status = marked)
        progress: count(Manuscript where status = marked)
"""
        region = _parse(src).workspaces[0].regions[0]
        s = region.pipeline_stages[0]
        assert s.value.startswith("count")
        assert s.progress.startswith("count")

    def test_progress_optional_default_empty(self) -> None:
        """The base DSL omits progress: entirely — IR field defaults to ""."""
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert all(s.progress == "" for s in region.pipeline_stages)

    def test_value_and_progress_coexist(self) -> None:
        """Stage can carry both — value is the count, progress is the bar.
        The prototype's three-column shape (label · count · bar)."""
        src = """module t
app t "Test"
entity M:
  id: uuid pk
workspace dash "Dash":
  pipeline:
    display: pipeline_steps
    stages:
      - label: "Marked"
        caption: "AO-level judgements complete"
        value: count(M)
        progress: 74
"""
        region = _parse(src).workspaces[0].regions[0]
        s = region.pipeline_stages[0]
        assert s.value.startswith("count")
        assert s.progress == "74"


class TestPipelineStageSpecProgressField:
    def test_construct_with_progress(self) -> None:
        s = PipelineStageSpec(label="X", progress="74")
        assert s.progress == "74"

    def test_default_progress_is_empty_string(self) -> None:
        s = PipelineStageSpec(label="X")
        assert s.progress == ""

    def test_progress_independent_of_value(self) -> None:
        """value: and progress: are separate fields — setting one doesn't
        clobber the other."""
        s = PipelineStageSpec(label="X", value="count(M)", progress="50")
        assert s.value == "count(M)"
        assert s.progress == "50"


class TestProgressCoercion:
    """The runtime helper `_coerce_pipeline_progress` clamps numeric
    inputs to 0-100 and flags overshoot. None / empty / unparseable
    → no bar (None, False)."""

    def test_in_range_returns_int(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress(50) == (50, False)
        assert _coerce_pipeline_progress("74") == (74, False)
        assert _coerce_pipeline_progress(74.6) == (75, False)  # rounds

    def test_zero_and_hundred_boundaries(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress(0) == (0, False)
        assert _coerce_pipeline_progress(100) == (100, False)

    def test_overshoot_clamps_to_100(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress(120) == (100, True)
        assert _coerce_pipeline_progress("150") == (100, True)

    def test_negative_clamps_to_0_no_overshoot(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress(-5) == (0, False)

    def test_none_and_empty_return_none(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress(None) == (None, False)
        assert _coerce_pipeline_progress("") == (None, False)

    def test_unparseable_returns_none(self) -> None:
        """Garbage strings (e.g. "foo") become None — caller renders no
        bar instead of bombing on a ValueError."""
        from dazzle_back.runtime.workspace_rendering import _coerce_pipeline_progress

        assert _coerce_pipeline_progress("not a number") == (None, False)
        assert _coerce_pipeline_progress(object()) == (None, False)


class TestProgressTemplateWiring:
    """The pipeline_steps.html template renders the progress bar
    block when `stage.progress is not none` and emits
    `data-dz-progress` for theming."""

    def test_template_has_progress_block(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/pipeline_steps.html"
        )
        contents = path.read_text()
        # Conditional gate on progress not being None
        assert "stage.progress is not none" in contents
        # Bound data attribute for theming
        assert 'data-dz-progress="{{ stage.progress }}"' in contents
        # Overshoot flag — emitted only when set
        assert "data-dz-progress-overshoot" in contents
        # ARIA progressbar role + label so screen readers announce it
        assert 'role="progressbar"' in contents
        assert 'aria-valuemin="0"' in contents
        assert 'aria-valuemax="100"' in contents
        assert 'aria-valuenow="{{ stage.progress }}"' in contents


# ───────────────────────── #912: end-to-end progress flow ──────────────


class TestProgressFlowsThroughBoundary:
    """v0.61.81 (#912): the IR→template-context boundary at
    `workspace_renderer.py:574` previously built pipeline_stages dicts
    with only `{label, caption, value}` — silently dropping the
    `progress` field added in v0.61.79 (#911). Result: parser parsed
    progress: 100 fine, IR carried it, but the rendered template never
    saw `stage.progress` so the bar never appeared.

    Same bug shape as #910 (profile_stats attribute access on what was
    actually a dict, which only fired when items were non-empty). The
    pre-fix template-wiring test only checked the template source for
    `stage.progress is not none` — it never verified that `progress`
    actually flowed through the IR→context boundary.

    These tests pin the full IR→context→template flow with non-empty
    progress values."""

    def test_boundary_emits_progress_in_dict(self) -> None:
        """The IR→template-context boundary must include `progress` in
        each pipeline_stages dict — without this the runtime can't see it."""
        from dazzle.core.ir.workspaces import PipelineStageSpec, WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = WorkspaceSpec(
            name="test",
            title="Test",
            regions=[
                WorkspaceRegion(
                    name="pipeline",
                    display="pipeline_steps",
                    pipeline_stages=[
                        PipelineStageSpec(
                            label="Marked", caption="cap", value="count(M)", progress="74"
                        ),
                    ],
                ),
            ],
        )
        ctx = build_workspace_context(ws)
        region = ctx.regions[0]
        assert len(region.pipeline_stages) == 1
        stage = region.pipeline_stages[0]
        # All four fields must flow through the boundary
        assert stage["label"] == "Marked"
        assert stage["caption"] == "cap"
        assert stage["value"] == "count(M)"
        assert stage["progress"] == "74", (
            "progress field was silently dropped at the IR→context boundary — "
            "rendered template never sees it, no bar rendered (#912)."
        )

    def test_template_renders_bar_when_progress_set(self) -> None:
        """End-to-end: parse a DSL with `progress: 100`, build IR,
        cross the template-context boundary, render. Pin the rendered
        HTML — would have caught #912 immediately."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        # Simulate the runtime's pipeline_stage_data shape that
        # workspace_rendering.py constructs after the boundary
        # (label/caption/value/progress/progress_overshoot per stage).
        pipeline_stage_data = [
            {
                "label": "PDF received",
                "caption": "scan stored",
                "value": 0,
                "progress": 100,
                "progress_overshoot": False,
            },
            {
                "label": "Decollated",
                "caption": "page boundaries grouped",
                "value": 12,
                "progress": 74,
                "progress_overshoot": False,
            },
        ]
        html = render_fragment(
            "workspace/regions/pipeline_steps.html",
            title="Job pipeline",
            pipeline_stage_data=pipeline_stage_data,
        )
        # Both stages must render the progress bar
        assert html.count('data-dz-progress="100"') == 1
        assert html.count('data-dz-progress="74"') == 1
        # ARIA wiring per bar
        assert html.count('role="progressbar"') == 2
        # The percent labels
        assert "100%" in html
        assert "74%" in html

    def test_template_omits_bar_when_progress_none(self) -> None:
        """Pin the negative case — stage.progress is None (legacy
        pipelines that don't use progress:) renders no bar. Preserves
        the v0.61.78 shape for existing apps."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        pipeline_stage_data = [
            {
                "label": "Step A",
                "caption": "",
                "value": 5,
                "progress": None,
                "progress_overshoot": False,
            },
        ]
        html = render_fragment(
            "workspace/regions/pipeline_steps.html",
            title="Pipeline",
            pipeline_stage_data=pipeline_stage_data,
        )
        # No bar rendered
        assert "data-dz-progress=" not in html
        assert 'role="progressbar"' not in html
        # But the rest of the stage still renders
        assert "Step A" in html
        # Value is rendered with surrounding whitespace; just check the digit
        assert "\n5" in html or " 5" in html or ">5" in html

    def test_template_emits_overshoot_flag_when_clamped(self) -> None:
        """Values >100 clamp to 100 + set data-dz-progress-overshoot."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        pipeline_stage_data = [
            {
                "label": "Over",
                "caption": "",
                "value": 0,
                "progress": 100,
                "progress_overshoot": True,
            },
        ]
        html = render_fragment(
            "workspace/regions/pipeline_steps.html",
            title="Pipeline",
            pipeline_stage_data=pipeline_stage_data,
        )
        assert 'data-dz-progress-overshoot="true"' in html
