"""Issue #1016 (v0.67.12): regression tests for the
`day_timeline_config:` DSL block parser.

Mirrors the cohort_strip_config_parser tests; same shape contract,
simpler config (string fields, no nested lens block).
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.core.errors import ParseError
from tests.unit.helpers.dsl import region_config

_SLOT = """
entity Slot "Slot":
  id: uuid pk
  name: str(100) required
  period_start: datetime
  period_end: datetime
"""

_BOUNDS = "starts_at: period_start\nends_at: period_end\n"


def _parse(body: str) -> Any:
    return region_config(entity=_SLOT, display="day_timeline", body=body)


def test_parses_minimal_config() -> None:
    """When `card:` is omitted the runtime falls through to a minimal default
    body (start/end label only) — IR carries the empty string."""
    cfg = _parse(_BOUNDS)
    assert (cfg.starts_at, cfg.ends_at, cfg.card) == ("period_start", "period_end", "")


@pytest.mark.parametrize(
    ("extra", "attr", "expected"),
    [
        pytest.param("card: lesson_card", "card", "lesson_card", id="card-template-name"),
        # #1234 — `today` / `now` are lexer-reserved keywords but must be
        # usable as the `as_of:` date anchor.
        pytest.param("as_of: today", "as_of", "today", id="as-of-today-keyword-1234"),
        pytest.param("as_of: now", "as_of", "now", id="as-of-now-keyword-1234"),
    ],
)
def test_parses_optional_key(extra: str, attr: str, expected: str) -> None:
    assert getattr(_parse(_BOUNDS + extra), attr) == expected


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param("ends_at: period_end\n", "starts_at", id="missing-starts-at"),
        pytest.param("starts_at: period_start\n", "ends_at", id="missing-ends-at"),
        pytest.param(_BOUNDS + "bogus: 1\n", "Unknown day_timeline_config key", id="unknown-key"),
    ],
)
def test_rejects_invalid_config(body: str, error: str) -> None:
    with pytest.raises(ParseError, match=error):
        _parse(body)
