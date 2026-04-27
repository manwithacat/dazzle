"""Tests for the v0.61.56 pipeline_steps display mode (#890).

Three layers:
  1. Parser: ``display: pipeline_steps`` + ``stages:`` indented dash-list
     of ``{label, caption, aggregate}`` entries parses into the IR.
     Crucially, the existing legacy ``stages: [a, b, c]`` bracketed
     form for ``progress`` mode still works — the parser shape-detects.
  2. Runtime: each stage's `aggregate_expr` fires via
     `_fetch_count_metric` concurrently. Stages without aggregates
     (or with not-yet-supported `median`/`avg`/etc.) render `None` →
     `—` in the template. Honours the #887 scope-deny gate.
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
        aggregate: count(Manuscript where status = uploaded)
      - label: "Reviewed"
        caption: "human-validated"
        aggregate: count(Manuscript where status = reviewed)
"""


# ───────────────────────── parser ──────────────────────────


class TestPipelineStepsParser:
    def test_minimal_pipeline(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.PIPELINE_STEPS
        assert len(region.pipeline_stages) == 2
        assert region.pipeline_stages[0].label == "Scanned"
        assert region.pipeline_stages[0].caption == "complete pupil scripts"
        assert (
            region.pipeline_stages[0].aggregate_expr
            == "count ( Manuscript where status = uploaded )"
        )

    def test_label_only_stage(self) -> None:
        """Only ``label:`` is required — caption/aggregate default."""
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
        assert s.aggregate_expr == ""

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
        aggregate: count(Manuscript where status = uploaded)
      - label: "Rubric pass"
        caption: "AO-level judgements with evidence snippets"
        aggregate: count(MarkingResult where latest_for_event = true)
      - label: "Moderation"
        caption: "low-confidence results isolated for review"
        aggregate: count(MarkingResult where flagged_for_review = true)
      - label: "Output"
        caption: "median grade"
        aggregate: median(Manuscript.computed_grade)
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.PIPELINE_STEPS
        assert len(region.pipeline_stages) == 4
        assert region.pipeline_stages[3].aggregate_expr.startswith("median")


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


# ───────────────────────── PipelineStageSpec ──────────────────────────


class TestPipelineStageSpec:
    def test_construct_minimal(self) -> None:
        s = PipelineStageSpec(label="X")
        assert s.label == "X"
        assert s.caption == ""
        assert s.aggregate_expr == ""

    def test_construct_full(self) -> None:
        s = PipelineStageSpec(label="Scanned", caption="cap", aggregate_expr="count(M)")
        assert s.caption == "cap"
        assert s.aggregate_expr == "count(M)"


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
            pipeline_stages=[
                {"label": "Scanned", "caption": "scripts", "aggregate_expr": "count(M)"}
            ],
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
