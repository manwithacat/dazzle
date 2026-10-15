"""Issue #1017 (v0.67.13): regression tests for the
`entity_card_config:` DSL block parser.

Mirrors the cohort_strip_config_parser shape with multi-section
configs, mode validation against EntityCardSectionMode enum, and
optional source/filter/limit/fields/actions per section.
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config

_RECORD = """
entity Record "Record":
  id: uuid pk
  name: str(100) required
  status: str(50)
  score: int
"""


def _parse(body: str) -> Any:
    return region_config(entity=_RECORD, display="entity_card", body=body)


def test_parses_minimal_config_with_one_section() -> None:
    cfg = _parse("sections:\n  - name: halo\n    mode: halo\n")
    assert [(s.name, s.mode.value) for s in cfg.sections] == [("halo", "halo")]
    assert cfg.scope_param == "id"  # default


def test_parses_custom_scope_param() -> None:
    cfg = _parse("scope_param: pupil_id\nsections:\n  - name: halo\n    mode: halo\n")
    assert cfg.scope_param == "pupil_id"


def test_parses_section_with_source_filter_limit() -> None:
    cfg = _parse(
        """
        sections:
          - name: history
            mode: stamps
            source: Record
            filter: status = "active"
            limit: 5
        """
    )
    s = cfg.sections[0]
    assert s.source == "Record"
    assert s.filter is not None  # ConditionExpr
    assert s.limit == 5


@pytest.mark.parametrize(
    ("section_keys", "attr", "expected"),
    [
        pytest.param(
            "mode: flags\n    fields: [name, status, score]",
            "fields",
            ["name", "status", "score"],
            id="fields-list",
        ),
        pytest.param(
            "mode: quick_actions\n    actions: [reload, archive]",
            "actions",
            ["reload", "archive"],
            id="actions-list",
        ),
    ],
)
def test_parses_section_list_key(section_keys: str, attr: str, expected: list[str]) -> None:
    cfg = _parse(f"sections:\n  - name: s\n    {section_keys}\n")
    assert getattr(cfg.sections[0], attr) == expected


def test_parses_all_section_modes() -> None:
    modes = ["halo", "flags", "mini_bars", "stamps", "thread_summary", "quick_actions"]
    body = "sections:\n" + "".join(f"  - name: s{i}\n    mode: {m}\n" for i, m in enumerate(modes))
    assert [s.mode.value for s in _parse(body).sections] == modes


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param("scope_param: id\n", "at least one section", id="missing-sections"),
        pytest.param("sections:\n  - name: x\n", "mode", id="section-missing-mode"),
        pytest.param(
            "sections:\n  - name: x\n    mode: weirdo\n", "mode must be one of", id="unknown-mode"
        ),
        pytest.param(
            "bogus: 1\nsections:\n  - name: x\n    mode: halo\n",
            "Unknown entity_card_config key",
            id="unknown-top-level-key",
        ),
        pytest.param(
            "sections:\n  - name: x\n    mode: halo\n    weird: 1\n",
            "Unknown sections entry key",
            id="unknown-section-entry-key",
        ),
        pytest.param("sections:\n  name: x\n", "must start with", id="section-entry-without-dash"),
    ],
)
def test_rejects_invalid_config(body: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        _parse(body)
