"""Unit tests for dazzle.fitness.triage."""

from __future__ import annotations

from dazzle.fitness.triage import (
    SEVERITY_RANK,
    DedupeKey,
    canonicalize_summary,
    compute_cluster_id,
    dedupe_key_for,
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


class TestDedupeKeyFor:
    def test_extracts_all_four_fields(self) -> None:
        row = {
            "id": "FIND-abc",
            "created": "2026-04-13T19:13:10+00:00",
            "locus": "story_drift",
            "axis": "coverage",
            "severity": "medium",
            "persona": "Administrator",
            "status": "PROPOSED",
            "route": "soft",
            "summary": "No matching story found",
        }
        key = dedupe_key_for(row)
        assert key.locus == "story_drift"
        assert key.axis == "coverage"
        assert key.canonical_summary == "no matching story found"
        assert key.persona == "Administrator"

    def test_canonicalises_summary(self) -> None:
        row = {
            "id": "FIND-abc",
            "created": "2026-04-13T19:13:10+00:00",
            "locus": "spec_stale",
            "axis": "conformance",
            "severity": "high",
            "persona": "Admin",
            "status": "PROPOSED",
            "route": "hard",
            "summary": "  MIXED  CASE  Summary  ",
        }
        key = dedupe_key_for(row)
        assert key.canonical_summary == "mixed case summary"


class TestComputeClusterID:
    def test_format(self) -> None:
        key = DedupeKey(
            locus="story_drift",
            axis="coverage",
            canonical_summary="no matching story found",
            persona="Administrator",
        )
        cluster_id = compute_cluster_id(key)
        assert cluster_id.startswith("CL-")
        assert len(cluster_id) == 3 + 8  # "CL-" + 8 hex chars

    def test_deterministic(self) -> None:
        key = DedupeKey(
            locus="story_drift",
            axis="coverage",
            canonical_summary="foo",
            persona="Admin",
        )
        assert compute_cluster_id(key) == compute_cluster_id(key)

    def test_different_keys_produce_different_ids(self) -> None:
        key1 = DedupeKey(locus="story_drift", axis="coverage", canonical_summary="foo", persona="A")
        key2 = DedupeKey(locus="story_drift", axis="coverage", canonical_summary="foo", persona="B")
        assert compute_cluster_id(key1) != compute_cluster_id(key2)

    def test_hex_characters_only(self) -> None:
        key = DedupeKey(locus="l", axis="a", canonical_summary="s", persona="p")
        suffix = compute_cluster_id(key)[3:]  # strip "CL-"
        assert all(c in "0123456789abcdef" for c in suffix)


class TestDedupeKeyFrozen:
    def test_is_frozen(self) -> None:
        import pytest

        key = DedupeKey(locus="l", axis="a", canonical_summary="s", persona="p")
        with pytest.raises((AttributeError, TypeError)):
            key.locus = "x"  # type: ignore[misc]
