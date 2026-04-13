"""Unit tests for dazzle.fitness.triage."""

from __future__ import annotations

from dazzle.fitness.triage import (
    SEVERITY_RANK,
    canonicalize_summary,
)


class TestCanonicalizeSummary:
    def test_lowercases(self) -> None:
        assert canonicalize_summary("FooBar") == "foobar"

    def test_strips_outer_whitespace(self) -> None:
        assert canonicalize_summary("  hello  ") == "hello"

    def test_collapses_internal_whitespace(self) -> None:
        assert canonicalize_summary("a  b\t c\n d") == "a b c d"

    def test_truncates_at_120_chars(self) -> None:
        long = "x" * 200
        assert len(canonicalize_summary(long)) == 120

    def test_idempotent(self) -> None:
        s = "  Hello   World  "
        once = canonicalize_summary(s)
        assert canonicalize_summary(once) == once


class TestSeverityRank:
    def test_rank_ordering(self) -> None:
        assert SEVERITY_RANK["critical"] > SEVERITY_RANK["high"]
        assert SEVERITY_RANK["high"] > SEVERITY_RANK["medium"]
        assert SEVERITY_RANK["medium"] > SEVERITY_RANK["low"]

    def test_all_four_levels_present(self) -> None:
        assert set(SEVERITY_RANK.keys()) == {"critical", "high", "medium", "low"}
