"""Issue #1016 (v0.67.12): regression tests for the
`day_timeline_config:` DSL block parser.

Mirrors the cohort_strip_config_parser tests; same shape contract,
simpler config (three string fields, no nested lens block).
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(body: str) -> object:
    src = f"""module ops
app demo_app "Demo"

entity Slot "Slot":
  id: uuid pk
  name: str(100) required
  period_start: datetime
  period_end: datetime

workspace dash "Dash":
  today_slots:
    source: Slot
    display: day_timeline
    day_timeline_config:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    region = fragment.workspaces[0].regions[0]
    return region.day_timeline_config


def test_parses_minimal_config() -> None:
    cfg = _parse(
        """      starts_at: period_start
      ends_at: period_end
"""
    )
    assert cfg is not None
    assert cfg.starts_at == "period_start"
    assert cfg.ends_at == "period_end"
    assert cfg.card == ""  # optional


def test_parses_card_template_name() -> None:
    cfg = _parse(
        """      starts_at: period_start
      ends_at: period_end
      card: lesson_card
"""
    )
    assert cfg.card == "lesson_card"


def test_rejects_missing_starts_at() -> None:
    with pytest.raises(ParseError, match="starts_at"):
        _parse(
            """      ends_at: period_end
"""
        )


def test_rejects_missing_ends_at() -> None:
    with pytest.raises(ParseError, match="ends_at"):
        _parse(
            """      starts_at: period_start
"""
        )


def test_rejects_unknown_key() -> None:
    with pytest.raises(ParseError, match="Unknown day_timeline_config key"):
        _parse(
            """      starts_at: period_start
      ends_at: period_end
      bogus: 1
"""
        )


def test_runtime_default_card_is_empty_string() -> None:
    """When `card:` is omitted the runtime falls through to a minimal
    default body (start/end label only) — IR carries empty string."""
    cfg = _parse(
        """      starts_at: period_start
      ends_at: period_end
"""
    )
    assert cfg.card == ""
