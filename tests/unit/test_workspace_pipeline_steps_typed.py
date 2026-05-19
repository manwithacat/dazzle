"""Pipeline_steps typed-payload tests post-ADR-0024 migration.

Pre-fix: ``PipelineStageSpec.value`` was ``str``; the runtime regex-matched
to discriminate aggregate-vs-literal. Now ``value`` (and ``progress``) is
``AggregateRef | str | None`` — the parser shape-detects at parse time, no
runtime regex.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import AggregateRef
from dazzle.core.ir.workspaces import PipelineStageSpec


def _parse_pipeline(src: str) -> list[PipelineStageSpec]:
    fragment = parse_dsl(src, Path("test.dsl"))[5]
    return list(fragment.workspaces[0].regions[0].pipeline_stages)


_DSL = """module t
app t "Test"
entity Alert:
  id: uuid pk
  status: enum[active,acknowledged,resolved]
workspace dash "Dash":
  pipe:
    display: pipeline_steps
    stages:
      - label: "Active"
        value: count(Alert where status = active)
      - label: "Resolved"
        value: count(Alert where status = resolved)
        progress: count(Alert where status = resolved)
      - label: "Audit"
        value: "Daily 02:00 UTC"
      - label: "Bare number"
        progress: 74
      - label: "Empty"
"""


def test_aggregate_value_parses_to_aggregateref() -> None:
    stages = _parse_pipeline(_DSL)
    s = stages[0]
    assert isinstance(s.value, AggregateRef)
    assert s.value.func == "count"
    assert s.value.entity == "Alert"
    assert s.value.where is not None


def test_aggregate_progress_parses_to_aggregateref() -> None:
    stages = _parse_pipeline(_DSL)
    s = stages[1]
    assert isinstance(s.progress, AggregateRef)
    assert s.progress.func == "count"


def test_quoted_literal_preserves_string() -> None:
    """Descriptive flow-card label like ``"Daily 02:00 UTC"`` stays a str."""
    stages = _parse_pipeline(_DSL)
    s = stages[2]
    assert s.value == "Daily 02:00 UTC"
    assert s.progress is None


def test_bare_token_sequence_preserves_string() -> None:
    """A bare numeric/identifier sequence (no parens, no quotes) is captured
    as a literal string — used for hard-coded ``progress: 74`` values."""
    stages = _parse_pipeline(_DSL)
    s = stages[3]
    assert s.value is None
    assert s.progress == "74"


def test_omitted_payload_is_none() -> None:
    stages = _parse_pipeline(_DSL)
    s = stages[4]
    assert s.value is None
    assert s.progress is None


def test_ir_accepts_typed_aggregate_ref() -> None:
    s = PipelineStageSpec(
        label="X",
        value=AggregateRef(func="count", entity="Task"),
    )
    assert isinstance(s.value, AggregateRef)


def test_ir_accepts_string_literal() -> None:
    s = PipelineStageSpec(label="X", value="Daily 02:00 UTC")
    assert s.value == "Daily 02:00 UTC"


def test_ir_accepts_none() -> None:
    s = PipelineStageSpec(label="X")
    assert s.value is None
    assert s.progress is None
