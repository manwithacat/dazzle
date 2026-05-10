"""Issue #1015 (v0.67.13): regression tests for the
`task_inbox_config:` DSL block parser.

Mirrors the cohort_strip_config_parser shape but with nested
`sources:` block + `as_task:` template + condition-expression
filters + as_task/count_as mutex.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Item "Item":
  id: uuid pk
  state: str(50)
  name: str(100)

workspace dash "Dash":
  inbox:
    source: Item
    display: task_inbox
    task_inbox_config:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    region = fragment.workspaces[0].regions[0]
    return region.task_inbox_config


def test_parses_minimal_config_with_count_as_source() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          count_as: "items pending"
"""
    )
    assert cfg is not None
    assert len(cfg.sources) == 1
    assert cfg.sources[0].count_as == "items pending"
    assert cfg.sources[0].as_task is None
    assert cfg.empty_state == "All caught up."  # default
    assert cfg.order == ["urgency", "deadline"]  # default


def test_parses_as_task_source_with_filter() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          filter: state = "pending"
          as_task:
            icon: register
            title: "Process {name}"
            meta: "{state}"
"""
    )
    assert len(cfg.sources) == 1
    src = cfg.sources[0]
    assert src.as_task is not None
    assert src.as_task.icon == "register"
    assert src.as_task.title == "Process {name}"
    assert src.as_task.meta == "{state}"
    assert src.filter is not None  # ConditionExpr


def test_parses_quoted_icon_for_hyphenated_lucide_names() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          as_task:
            icon: "alert-triangle"
            title: "x"
"""
    )
    assert cfg.sources[0].as_task.icon == "alert-triangle"


def test_parses_custom_empty_state_and_order() -> None:
    cfg = _parse(
        """      empty_state: "Nothing to do."
      order: [deadline, urgency]
      sources:
        - source: Item
          count_as: "x"
"""
    )
    assert cfg.empty_state == "Nothing to do."
    assert cfg.order == ["deadline", "urgency"]


def test_parses_multiple_heterogeneous_sources() -> None:
    cfg = _parse(
        """      sources:
        - source: Item
          filter: state = "active"
          as_task:
            icon: register
            title: "Process {name}"
        - source: Item
          filter: state = "review"
          count_as: "items in review"
"""
    )
    assert len(cfg.sources) == 2
    assert cfg.sources[0].as_task is not None
    assert cfg.sources[1].count_as == "items in review"


def test_rejects_missing_sources_block() -> None:
    with pytest.raises(ParseError, match="at least one source"):
        _parse(
            """      empty_state: "x"
"""
        )


def test_rejects_source_with_neither_as_task_nor_count_as() -> None:
    with pytest.raises(ParseError, match="exactly one"):
        _parse(
            """      sources:
        - source: Item
          filter: state = "x"
"""
        )


def test_rejects_source_with_both_as_task_and_count_as() -> None:
    with pytest.raises(ParseError, match="mutually exclusive"):
        _parse(
            """      sources:
        - source: Item
          count_as: "x"
          as_task:
            icon: x
            title: "y"
"""
        )


def test_rejects_unknown_top_level_key() -> None:
    with pytest.raises(ParseError, match="Unknown task_inbox_config key"):
        _parse(
            """      bogus: 1
      sources:
        - source: Item
          count_as: "x"
"""
        )


def test_rejects_unknown_source_entry_key() -> None:
    with pytest.raises(ParseError, match="Unknown sources entry key"):
        _parse(
            """      sources:
        - source: Item
          weird: 1
          count_as: "x"
"""
        )


def test_rejects_as_task_missing_icon() -> None:
    with pytest.raises(ParseError, match="icon"):
        _parse(
            """      sources:
        - source: Item
          as_task:
            title: "x"
"""
        )


def test_rejects_as_task_missing_title() -> None:
    with pytest.raises(ParseError, match="title"):
        _parse(
            """      sources:
        - source: Item
          as_task:
            icon: x
"""
        )
