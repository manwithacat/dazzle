"""Tests for dazzle.compliance.review module."""

import pytest

from dazzle.compliance.review import generate_review_data


@pytest.fixture
def sample_auditspec():
    """Legacy dict schema (gaps list)."""
    return {
        "controls": [
            {
                "id": "C-1",
                "name": "Evidenced Control",
                "status": "evidenced",
                "evidence": [{"construct": "permit"}],
                "gaps": [],
            },
            {
                "id": "C-2",
                "name": "Partial Control",
                "status": "partial",
                "evidence": [{"construct": "classify"}],
                "gaps": [
                    {"tier": 2, "description": "Missing scope rules", "action": "Add scope blocks"},
                ],
            },
            {
                "id": "C-3",
                "name": "Gap Control",
                "status": "gap",
                "evidence": [],
                "gaps": [
                    {"tier": 3, "description": "No DSL construct", "action": "Document policy"},
                ],
            },
            {
                "id": "C-4",
                "name": "Tier 1 Gap",
                "status": "gap",
                "evidence": [],
                "gaps": [
                    {"tier": 1, "description": "Minor issue"},
                ],
            },
        ],
    }


def test_generates_reviews(sample_auditspec):
    result = generate_review_data(sample_auditspec)
    assert "pending_reviews" in result
    reviews = result["pending_reviews"]
    # Only tier 2 and 3 gaps
    assert len(reviews) == 2


def test_tier2_status_draft(sample_auditspec):
    result = generate_review_data(sample_auditspec)
    tier2 = [r for r in result["pending_reviews"] if r["tier"] == 2]
    assert len(tier2) == 1
    assert tier2[0]["status"] == "draft"
    assert tier2[0]["control_id"] == "C-2"


def test_tier3_status_stub(sample_auditspec):
    result = generate_review_data(sample_auditspec)
    tier3 = [r for r in result["pending_reviews"] if r["tier"] == 3]
    assert len(tier3) == 1
    assert tier3[0]["status"] == "stub"
    assert tier3[0]["control_id"] == "C-3"


def test_review_fields(sample_auditspec):
    result = generate_review_data(sample_auditspec)
    review = result["pending_reviews"][0]
    assert "control_id" in review
    assert "control_name" in review
    assert "tier" in review
    assert "description" in review
    assert "action" in review
    assert review["resolved"] is False


def test_empty_auditspec():
    result = generate_review_data({"controls": []})
    assert result["pending_reviews"] == []


def test_no_gaps():
    auditspec = {
        "controls": [
            {"id": "C-1", "name": "OK", "status": "evidenced", "gaps": []},
        ],
    }
    result = generate_review_data(auditspec)
    assert result["pending_reviews"] == []


def test_new_schema_review():
    """New typed AuditSpec schema uses tier as direct field."""
    auditspec = {
        "controls": [
            {
                "control_id": "C-1",
                "control_name": "Access Control",
                "status": "gap",
                "tier": 3,
                "evidence": [],
                "gap_description": "No DSL construct",
                "action": "Add permit blocks",
            },
            {
                "control_id": "C-2",
                "control_name": "OK Control",
                "status": "evidenced",
                "tier": 1,
                "evidence": [{"entity": "Task", "construct": "permit"}],
                "gap_description": "",
                "action": "",
            },
        ],
    }
    result = generate_review_data(auditspec)
    reviews = result["pending_reviews"]
    assert len(reviews) == 1
    assert reviews[0]["control_id"] == "C-1"
    assert reviews[0]["tier"] == 3
    assert reviews[0]["description"] == "No DSL construct"
