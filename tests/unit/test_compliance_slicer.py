"""Tests for dazzle.compliance.slicer module."""

import pytest

from dazzle.compliance.slicer import slice_auditspec


@pytest.fixture
def sample_auditspec():
    return {
        "auditspec_version": "1.0",
        "framework": "test",
        "controls": [
            {
                "id": "C-1",
                "name": "Control 1",
                "status": "evidenced",
                "evidence": [{"construct": "permit", "count": 5}],
                "gaps": [],
            },
            {
                "id": "C-2",
                "name": "Control 2",
                "status": "partial",
                "evidence": [{"construct": "classify", "count": 3}],
                "gaps": [{"tier": 2, "description": "Missing scope"}],
            },
            {
                "id": "C-3",
                "name": "Control 3",
                "status": "gap",
                "evidence": [],
                "gaps": [{"tier": 3, "description": "No DSL construct"}],
            },
        ],
        "summary": {"total_controls": 3, "evidenced": 1, "partial": 1, "gaps": 1},
    }


def test_slice_all(sample_auditspec):
    result = slice_auditspec(sample_auditspec)
    assert len(result["controls"]) == 3


def test_slice_by_ids(sample_auditspec):
    result = slice_auditspec(sample_auditspec, controls=["C-1", "C-3"])
    assert len(result["controls"]) == 2
    ids = [c["id"] for c in result["controls"]]
    assert "C-1" in ids
    assert "C-3" in ids


def test_slice_by_status(sample_auditspec):
    result = slice_auditspec(sample_auditspec, status_filter=["gap"])
    assert len(result["controls"]) == 1
    assert result["controls"][0]["id"] == "C-3"


def test_slice_by_extract(sample_auditspec):
    result = slice_auditspec(sample_auditspec, extract=["permit"])
    assert len(result["controls"]) == 1
    assert result["controls"][0]["id"] == "C-1"


def test_slice_by_tier(sample_auditspec):
    result = slice_auditspec(sample_auditspec, tier_filter=[3])
    assert len(result["controls"]) == 1
    assert result["controls"][0]["id"] == "C-3"


def test_summary_recalculated(sample_auditspec):
    result = slice_auditspec(sample_auditspec, status_filter=["gap", "partial"])
    assert result["summary"]["total_controls"] == 2
    assert result["summary"]["partial"] == 1
    assert result["summary"]["gaps"] == 1
    assert result["summary"]["evidenced"] == 0


def test_empty_filter(sample_auditspec):
    result = slice_auditspec(sample_auditspec, controls=["NONEXISTENT"])
    assert len(result["controls"]) == 0
    assert result["summary"]["total_controls"] == 0


def test_combined_status_and_tier(sample_auditspec):
    """Combined filters should work together."""
    result = slice_auditspec(sample_auditspec, status_filter=["gap", "partial"], tier_filter=[3])
    assert len(result["controls"]) == 1
    assert result["controls"][0]["id"] == "C-3"


def test_excluded_count(sample_auditspec):
    """Summary should include excluded count."""
    result = slice_auditspec(sample_auditspec, status_filter=["gap"])
    assert result["summary"]["excluded"] == 2
