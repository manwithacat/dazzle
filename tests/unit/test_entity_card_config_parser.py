"""Issue #1017 (v0.67.13): regression tests for the
`entity_card_config:` DSL block parser.

Mirrors the cohort_strip_config_parser shape with multi-section
configs, mode validation against EntityCardSectionMode enum, and
optional source/filter/limit/fields/actions per section.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Record "Record":
  id: uuid pk
  name: str(100) required
  status: str(50)
  score: int

workspace dash "Dash":
  card_view:
    source: Record
    display: entity_card
    entity_card_config:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    region = fragment.workspaces[0].regions[0]
    return region.entity_card_config


def test_parses_minimal_config_with_one_section() -> None:
    cfg = _parse(
        """      sections:
        - name: halo
          mode: halo
"""
    )
    assert cfg is not None
    assert len(cfg.sections) == 1
    assert cfg.sections[0].name == "halo"
    assert cfg.sections[0].mode.value == "halo"
    assert cfg.scope_param == "id"  # default


def test_parses_custom_scope_param() -> None:
    cfg = _parse(
        """      scope_param: pupil_id
      sections:
        - name: halo
          mode: halo
"""
    )
    assert cfg.scope_param == "pupil_id"


def test_parses_section_with_source_filter_limit() -> None:
    cfg = _parse(
        """      sections:
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


def test_parses_section_with_fields_list() -> None:
    cfg = _parse(
        """      sections:
        - name: meta
          mode: flags
          fields: [name, status, score]
"""
    )
    assert cfg.sections[0].fields == ["name", "status", "score"]


def test_parses_section_with_actions_list() -> None:
    cfg = _parse(
        """      sections:
        - name: ops
          mode: quick_actions
          actions: [reload, archive]
"""
    )
    assert cfg.sections[0].actions == ["reload", "archive"]


def test_parses_all_section_modes() -> None:
    cfg = _parse(
        """      sections:
        - name: a
          mode: halo
        - name: b
          mode: flags
        - name: c
          mode: mini_bars
        - name: d
          mode: stamps
        - name: e
          mode: thread_summary
        - name: f
          mode: quick_actions
"""
    )
    modes = [s.mode.value for s in cfg.sections]
    assert modes == [
        "halo",
        "flags",
        "mini_bars",
        "stamps",
        "thread_summary",
        "quick_actions",
    ]


def test_rejects_missing_sections() -> None:
    with pytest.raises(ParseError, match="at least one section"):
        _parse(
            """      scope_param: id
"""
        )


def test_rejects_section_missing_mode() -> None:
    with pytest.raises(ParseError, match="mode"):
        _parse(
            """      sections:
        - name: x
"""
        )


def test_rejects_unknown_mode() -> None:
    with pytest.raises(ParseError, match="mode must be one of"):
        _parse(
            """      sections:
        - name: x
          mode: weirdo
"""
        )


def test_rejects_unknown_top_level_key() -> None:
    with pytest.raises(ParseError, match="Unknown entity_card_config key"):
        _parse(
            """      bogus: 1
      sections:
        - name: x
          mode: halo
"""
        )


def test_rejects_unknown_section_entry_key() -> None:
    with pytest.raises(ParseError, match="Unknown sections entry key"):
        _parse(
            """      sections:
        - name: x
          mode: halo
          weird: 1
"""
        )


def test_rejects_section_entry_without_dash() -> None:
    with pytest.raises(ParseError, match="must start with"):
        _parse(
            """      sections:
        name: x
"""
        )
