"""#1144 part 2: parser tests for `primary_composite:` on
cohort_strip lenses."""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse_lens(lens_body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Member "Member":
  id: uuid pk
  score: int

workspace dash "Dash":
  members:
    source: Member
    display: cohort_strip
    cohort_strip_config:
      member_via: id
      lenses:
        - id: ao
          label: "AO breakdown"
{lens_body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    return fragment.workspaces[0].regions[0].cohort_strip_config.lenses[0]


def test_parses_primary_composite_block() -> None:
    lens = _parse_lens(
        """          primary_composite:
            separator: " / "
            parts:
              - field: ao1_score
              - field: ao2_score
              - field: ao3_score
"""
    )
    assert lens.primary == ""
    assert lens.primary_composite is not None
    assert len(lens.primary_composite.parts) == 3
    assert [p.field for p in lens.primary_composite.parts] == [
        "ao1_score",
        "ao2_score",
        "ao3_score",
    ]
    assert lens.primary_composite.separator == " / "


def test_parses_per_part_tone() -> None:
    lens = _parse_lens(
        """          primary_composite:
            separator: " | "
            parts:
              - field: pos_count
                tone: good
              - field: neg_count
                tone: bad
"""
    )
    parts = lens.primary_composite.parts
    assert parts[0].tone == "good"
    assert parts[1].tone == "bad"


def test_default_separator_when_omitted() -> None:
    lens = _parse_lens(
        """          primary_composite:
            parts:
              - field: a
              - field: b
"""
    )
    assert lens.primary_composite.separator == " / "


def test_primary_and_primary_composite_rejected() -> None:
    """Both `primary:` and `primary_composite:` on one lens — IR
    validator surfaces through the parser wrap."""
    with pytest.raises((ParseError, ValueError), match="mutually exclusive"):
        _parse_lens(
            """          primary: score
          primary_composite:
            parts:
              - field: a
"""
        )


def test_lens_with_neither_primary_form_rejected() -> None:
    """A lens declaring neither `primary:` nor `primary_composite:`
    is rejected at parse time."""
    with pytest.raises(ParseError, match="requires exactly one"):
        _parse_lens("""""")


def test_parts_empty_rejected() -> None:
    with pytest.raises(ParseError, match="non-empty `parts:`"):
        _parse_lens(
            """          primary_composite:
            separator: " / "
"""
        )


def test_parts_entry_requires_field() -> None:
    with pytest.raises(ParseError, match="must start with `field:`"):
        _parse_lens(
            """          primary_composite:
            parts:
              - tone: good
                field: a
"""
        )


def test_unknown_composite_key_rejected() -> None:
    with pytest.raises(ParseError, match="Unknown primary_composite key"):
        _parse_lens(
            """          primary_composite:
            bogus: nope
            parts:
              - field: a
"""
        )


def test_scalar_primary_still_works() -> None:
    """Regression — `primary: <ident>` keeps the existing shape."""
    lens = _parse_lens(
        """          primary: score
"""
    )
    assert lens.primary == "score"
    assert lens.primary_composite is None
