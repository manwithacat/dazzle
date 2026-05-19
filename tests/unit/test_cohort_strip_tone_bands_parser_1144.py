"""#1144 part 1: parser tests for the `tone_bands:` block on
cohort_strip lenses."""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse_lens(lens_body: str) -> object:
    """Wrap the lens body in module/app/entity/workspace boilerplate
    and return the parsed lens object."""
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
        - id: score
          label: Score
          primary: score
{lens_body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    return fragment.workspaces[0].regions[0].cohort_strip_config.lenses[0]


def test_parses_tone_bands_block() -> None:
    lens = _parse_lens(
        """          tone_bands:
            - at: 90
              tone: good
            - at: 70
              tone: warn
            - at: 0
              tone: bad
"""
    )
    bands = lens.tone_bands
    assert len(bands) == 3
    assert bands[0].at == 90
    assert bands[0].tone == "good"
    assert bands[1].at == 70
    assert bands[1].tone == "warn"
    assert bands[2].at == 0
    assert bands[2].tone == "bad"
    # `threshold:` left unset when `tone_bands:` carries the mapping.
    assert lens.threshold is None


def test_tone_bands_and_threshold_rejected_at_parse_time() -> None:
    """The model validator (#1144 part 1) raises when both are set
    — surfaces via the parser wrap."""
    with pytest.raises((ParseError, ValueError), match="mutually exclusive"):
        _parse_lens(
            """          threshold: 80
          tone_bands:
            - at: 90
              tone: good
"""
        )


def test_tone_bands_entry_requires_at_first() -> None:
    """The dash-list contract pins `at:` as the leading key per
    entry — matches the `id:` / `title:` convention elsewhere."""
    with pytest.raises(ParseError, match="must start with `at:`"):
        _parse_lens(
            """          tone_bands:
            - tone: good
              at: 90
"""
        )


def test_tone_bands_entry_requires_tone() -> None:
    with pytest.raises(ParseError, match="requires a `tone:` field"):
        _parse_lens(
            """          tone_bands:
            - at: 90
"""
        )


def test_tone_bands_unknown_key_rejected() -> None:
    with pytest.raises(ParseError, match="Unknown tone_bands entry key"):
        _parse_lens(
            """          tone_bands:
            - at: 90
              tone: good
              fizzbuzz: nope
"""
        )


def test_threshold_alone_unchanged() -> None:
    """Regression guard — scalar `threshold:` still parses without
    `tone_bands:`."""
    lens = _parse_lens(
        """          threshold: 80
"""
    )
    assert lens.threshold == 80
    assert lens.tone_bands == []
