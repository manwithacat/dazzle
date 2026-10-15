"""Issue #1015 (v0.67.13): regression tests for the
`task_inbox_config:` DSL block parser.

Mirrors the cohort_strip_config_parser shape but with nested
`sources:` block + `as_task:` template + condition-expression
filters + as_task/count_as mutex.
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config

_ITEM = """
entity Item "Item":
  id: uuid pk
  state: str(50)
  name: str(100)
"""


def parse_inbox(body: str) -> Any:
    return region_config(entity=_ITEM, display="task_inbox", body=body)


def test_parses_minimal_config_with_count_as_source() -> None:
    cfg = parse_inbox('sources:\n  - source: Item\n    count_as: "items pending"\n')
    assert [(s.count_as, s.as_task) for s in cfg.sources] == [("items pending", None)]
    assert cfg.empty_state == "All caught up."  # default
    assert cfg.order == ["urgency", "deadline"]  # default


def test_parses_as_task_source_with_filter() -> None:
    cfg = parse_inbox(
        """
        sources:
          - source: Item
            filter: state = "pending"
            as_task:
              icon: register
              title: "Process {name}"
              meta: "{state}"
        """
    )
    src = cfg.sources[0]
    assert (src.as_task.icon, src.as_task.title, src.as_task.meta) == (
        "register",
        "Process {name}",
        "{state}",
    )
    assert src.filter is not None  # ConditionExpr


def test_parses_quoted_icon_for_hyphenated_lucide_names() -> None:
    cfg = parse_inbox(
        'sources:\n  - source: Item\n    as_task:\n      icon: "alert-triangle"\n      title: "x"\n'
    )
    assert cfg.sources[0].as_task.icon == "alert-triangle"


def test_parses_custom_empty_state_and_order() -> None:
    cfg = parse_inbox(
        'empty_state: "Nothing to do."\norder: [deadline, urgency]\n'
        'sources:\n  - source: Item\n    count_as: "x"\n'
    )
    assert cfg.empty_state == "Nothing to do."
    assert cfg.order == ["deadline", "urgency"]


def test_parses_multiple_heterogeneous_sources() -> None:
    cfg = parse_inbox(
        """
        sources:
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


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param('empty_state: "x"\n', "at least one source", id="missing-sources"),
        pytest.param(
            'sources:\n  - source: Item\n    filter: state = "x"\n',
            "exactly one",
            id="neither-as-task-nor-count-as",
        ),
        pytest.param(
            'sources:\n  - source: Item\n    count_as: "x"\n'
            '    as_task:\n      icon: x\n      title: "y"\n',
            "mutually exclusive",
            id="both-as-task-and-count-as",
        ),
        pytest.param(
            'bogus: 1\nsources:\n  - source: Item\n    count_as: "x"\n',
            "Unknown task_inbox_config key",
            id="unknown-top-level-key",
        ),
        pytest.param(
            'sources:\n  - source: Item\n    weird: 1\n    count_as: "x"\n',
            "Unknown sources entry key",
            id="unknown-source-entry-key",
        ),
        pytest.param(
            'sources:\n  - source: Item\n    as_task:\n      title: "x"\n',
            "icon",
            id="as-task-missing-icon",
        ),
        pytest.param(
            "sources:\n  - source: Item\n    as_task:\n      icon: x\n",
            "title",
            id="as-task-missing-title",
        ),
    ],
)
def test_rejects_invalid_config(body: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        parse_inbox(body)
