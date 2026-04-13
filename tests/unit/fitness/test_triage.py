"""Unit tests for dazzle.fitness.triage."""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.fitness.triage import (
    SEVERITY_RANK,
    DedupeKey,
    canonicalize_summary,
    cluster_findings,
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


def _row(
    *,
    finding_id: str = "FIND-abc",
    created: str = "2026-04-13T19:13:10+00:00",
    locus: str = "story_drift",
    axis: str = "coverage",
    severity: str = "medium",
    persona: str = "Administrator",
    summary: str = "No matching story found",
) -> dict[str, str]:
    return {
        "id": finding_id,
        "created": created,
        "locus": locus,
        "axis": axis,
        "severity": severity,
        "persona": persona,
        "status": "PROPOSED",
        "route": "soft",
        "summary": summary,
    }


class TestClusterFindings:
    def test_empty_input_returns_empty_list(self) -> None:
        assert cluster_findings([]) == []

    def test_single_row_produces_single_cluster(self) -> None:
        clusters = cluster_findings([_row()])
        assert len(clusters) == 1
        c = clusters[0]
        assert c.cluster_size == 1
        assert c.severity == "medium"
        assert c.persona == "Administrator"

    def test_three_distinct_keys_produce_three_clusters(self) -> None:
        rows = [
            _row(finding_id="FIND-1", persona="A"),
            _row(finding_id="FIND-2", persona="B"),
            _row(finding_id="FIND-3", persona="C"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 3
        personas = {c.persona for c in clusters}
        assert personas == {"A", "B", "C"}

    def test_identical_keys_aggregate(self) -> None:
        rows = [
            _row(finding_id="FIND-1", created="2026-04-13T19:00:00+00:00"),
            _row(finding_id="FIND-2", created="2026-04-13T19:30:00+00:00"),
            _row(finding_id="FIND-3", created="2026-04-13T20:00:00+00:00"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 1
        c = clusters[0]
        assert c.cluster_size == 3
        assert c.first_seen == datetime(2026, 4, 13, 19, 0, 0, tzinfo=UTC)
        assert c.last_seen == datetime(2026, 4, 13, 20, 0, 0, tzinfo=UTC)
        assert c.sample_id == "FIND-1"

    def test_severity_aggregation_takes_max(self) -> None:
        rows = [
            _row(finding_id="FIND-1", severity="medium"),
            _row(finding_id="FIND-2", severity="high"),
            _row(finding_id="FIND-3", severity="low"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 1
        assert clusters[0].severity == "high"

    def test_sort_order_severity_descending(self) -> None:
        rows = [
            _row(finding_id="FIND-1", persona="X", severity="low"),
            _row(finding_id="FIND-2", persona="Y", severity="critical"),
            _row(finding_id="FIND-3", persona="Z", severity="medium"),
        ]
        clusters = cluster_findings(rows)
        severities = [c.severity for c in clusters]
        assert severities == ["critical", "medium", "low"]

    def test_sort_order_within_severity_by_cluster_size_desc(self) -> None:
        rows = [
            # cluster A: 1 member, medium
            _row(finding_id="FIND-a1", persona="A", severity="medium"),
            # cluster B: 3 members, medium
            _row(finding_id="FIND-b1", persona="B", severity="medium"),
            _row(finding_id="FIND-b2", persona="B", severity="medium"),
            _row(finding_id="FIND-b3", persona="B", severity="medium"),
        ]
        clusters = cluster_findings(rows)
        assert len(clusters) == 2
        assert clusters[0].persona == "B"  # size 3 first
        assert clusters[1].persona == "A"  # size 1 second

    def test_sort_tiebreaker_is_cluster_id(self) -> None:
        """Same severity, same size → sort by cluster_id lex for stability."""
        rows = [
            _row(finding_id="FIND-1", persona="Zebra", severity="medium"),
            _row(finding_id="FIND-2", persona="Alpha", severity="medium"),
        ]
        clusters_1 = cluster_findings(rows)
        clusters_2 = cluster_findings(list(reversed(rows)))
        # Same set of clusters, same stable order, regardless of input order.
        assert [c.cluster_id for c in clusters_1] == [c.cluster_id for c in clusters_2]


class TestClusterUnknownSeverity:
    def test_falls_back_to_lowest_rank(self) -> None:
        rows = [
            _row(finding_id="FIND-1", severity="wonky"),
        ]
        clusters = cluster_findings(rows)
        # Unknown severity → rank 0 (lowest) → preserved as-is in the
        # aggregated severity field so callers see the raw value.
        assert len(clusters) == 1
        assert clusters[0].severity == "wonky"
