"""Issue #1018 (v0.67.11): regression tests for the
`cohort_strip_config:` DSL block parser.

The parser pilot for the discriminated typed-config blocks in the
#1015–#1018 region-primitive quartet. Establishes the syntax shape
and the required-field / lens-validation contracts that #1015,
#1016, #1017's config-block parsers will mirror.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(body: str) -> object:
    """Wrap a region body in module/app/entity/workspace boilerplate
    and return the parsed CohortStripConfig (or raise ParseError).
    """
    src = f"""module ops
app demo_app "Demo"

entity Member "Member":
  id: uuid pk
  name: str(100) required
  status: str(50)
  score: int

workspace dash "Dash":
  members:
    source: Member
    display: cohort_strip
    cohort_strip_config:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]  # ModuleFragment is the last tuple element
    ws = fragment.workspaces[0]
    region = ws.regions[0]
    return region.cohort_strip_config


def test_parses_minimal_config() -> None:
    cfg = _parse(
        """      member_via: id
      lenses:
        - id: status
          label: Status
          primary: status
"""
    )
    assert cfg is not None
    assert cfg.member_via == "id"
    assert cfg.default_lens == ""  # optional, defaults empty
    assert len(cfg.lenses) == 1
    assert cfg.lenses[0].id == "status"
    assert cfg.lenses[0].label == "Status"
    assert cfg.lenses[0].primary == "status"
    assert cfg.lenses[0].threshold is None


def test_parses_default_lens_and_multiple_lenses() -> None:
    cfg = _parse(
        """      member_via: id
      default_lens: score
      lenses:
        - id: status
          label: Status
          primary: status
        - id: score
          label: "Score"
          primary: score
          threshold: 80
"""
    )
    assert cfg.default_lens == "score"
    assert len(cfg.lenses) == 2
    assert cfg.lenses[1].id == "score"
    assert cfg.lenses[1].threshold == 80.0


def test_parses_quoted_label_with_spaces_and_punctuation() -> None:
    cfg = _parse(
        """      member_via: id
      lenses:
        - id: rt
          label: "Response time (P95)"
          primary: score
"""
    )
    assert cfg.lenses[0].label == "Response time (P95)"


def test_parses_label_as_bare_identifier_when_no_spaces() -> None:
    cfg = _parse(
        """      member_via: id
      lenses:
        - id: x
          label: Status
          primary: status
"""
    )
    assert cfg.lenses[0].label == "Status"


def test_parses_threshold_as_integer() -> None:
    cfg = _parse(
        """      member_via: id
      lenses:
        - id: x
          label: X
          primary: score
          threshold: 80
"""
    )
    assert cfg.lenses[0].threshold == 80.0


# ── Validation errors ──


def test_rejects_missing_member_via() -> None:
    with pytest.raises(ParseError, match="member_via"):
        _parse(
            """      lenses:
        - id: x
          label: X
          primary: score
"""
        )


def test_rejects_empty_lenses_list() -> None:
    with pytest.raises(ParseError, match="at least one lens"):
        _parse(
            """      member_via: id
"""
        )


def test_rejects_default_lens_not_in_declared_lenses() -> None:
    with pytest.raises(ParseError, match="default_lens"):
        _parse(
            """      member_via: id
      default_lens: ghost
      lenses:
        - id: status
          label: Status
          primary: status
"""
        )


def test_rejects_lens_missing_label() -> None:
    with pytest.raises(ParseError, match="label"):
        _parse(
            """      member_via: id
      lenses:
        - id: x
          primary: score
"""
        )


def test_rejects_lens_missing_primary() -> None:
    with pytest.raises(ParseError, match="primary"):
        _parse(
            """      member_via: id
      lenses:
        - id: x
          label: X
"""
        )


def test_rejects_unknown_top_level_key() -> None:
    with pytest.raises(ParseError, match="Unknown cohort_strip_config key"):
        _parse(
            """      member_via: id
      bogus: 1
      lenses:
        - id: x
          label: X
          primary: score
"""
        )


def test_rejects_unknown_lens_key() -> None:
    with pytest.raises(ParseError, match="Unknown lenses key"):
        _parse(
            """      member_via: id
      lenses:
        - id: x
          label: X
          primary: score
          weird: 1
"""
        )


def test_rejects_lens_entry_without_dash() -> None:
    with pytest.raises(ParseError, match="must start with `- id:"):
        _parse(
            """      member_via: id
      lenses:
        id: x
"""
        )


def test_rejects_lens_entry_starting_with_non_id_key() -> None:
    with pytest.raises(ParseError, match="must start with `id:`"):
        _parse(
            """      member_via: id
      lenses:
        - label: X
          id: x
          primary: score
"""
        )
