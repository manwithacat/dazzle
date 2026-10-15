"""Property/fuzz tests for the small input-boundary parsers (#1342 fuzz-leverage #3).

Each asserts the parser's *contract invariant* — arbitrary input maps to a controlled
outcome (a documented exception type OR a valid result), never a raw/unexpected crash.
These are the new fuzz surfaces the leverage evaluation identified
(`docs/proposals/fuzz-harness-leverage-evaluation.md`)."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_UNICODE_TEXT = st.text(max_size=60) | st.text(
    alphabet=st.characters(min_codepoint=0, max_codepoint=0x2FFF), max_size=40
)


# ---- split_duration_token / short_duration_seconds: any str → result OR None, never raise ----


class TestDurationLexHelpers:
    @given(_UNICODE_TEXT)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_split_duration_token_never_raises(self, s: str) -> None:
        from dazzle.core.dsl_parser_impl._lexical import split_duration_token

        # Contract: returns (int, suffix) or None — NEVER a raw exception. str.isdigit()
        # is True for "²"/"٣" but int("²") raises; the parser must not leak that.
        result = split_duration_token(s)
        assert result is None or (isinstance(result, tuple) and isinstance(result[0], int))

    @given(_UNICODE_TEXT)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_short_duration_seconds_never_raises(self, s: str) -> None:
        from dazzle.core.dsl_parser_impl._lexical import short_duration_seconds

        result = short_duration_seconds(s)
        assert result is None or isinstance(result, int)

    @pytest.mark.parametrize("text", ["²h", "⁵d", "¹m", "²s", "٣h"])
    def test_unicode_digits_return_none_not_crash(self, text: str) -> None:
        from dazzle.core.dsl_parser_impl._lexical import (
            short_duration_seconds,
            split_duration_token,
        )

        assert split_duration_token(text) is None
        assert short_duration_seconds(text) is None


# ---- parse_schedule: TOTAL — any str → a (weekdays, start, end) tuple, never raises ----


class TestParseSchedule:
    @given(_UNICODE_TEXT)
    @settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
    def test_total_never_raises(self, s: str) -> None:
        from dazzle.http.runtime.sla_manager import parse_schedule

        weekdays, start_hm, end_hm = parse_schedule(s)
        assert isinstance(weekdays, set)
        assert isinstance(start_hm, tuple) and len(start_hm) == 2
        assert isinstance(end_hm, tuple) and len(end_hm) == 2

    def test_valid_schedule_still_parses(self) -> None:
        from dazzle.http.runtime.sla_manager import parse_schedule

        weekdays, start_hm, end_hm = parse_schedule("Mon-Fri 09:00-17:00")
        assert weekdays == {0, 1, 2, 3, 4}
        assert start_hm == (9, 0) and end_hm == (17, 0)
