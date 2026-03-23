"""Tests for dazzle.compliance.citation module."""

import pytest

from dazzle.compliance.citation import CITATION_PATTERN, validate_citations


@pytest.fixture
def sample_auditspec():
    return {
        "controls": [
            {
                "id": "C-1",
                "evidence": [
                    {
                        "construct": "permit",
                        "refs": [
                            {"entity": "User", "operations": {"read": ["admin"]}},
                            {"entity": "School", "operations": {"list": ["admin"]}},
                        ],
                    },
                    {
                        "construct": "classify",
                        "refs": [
                            {"entity": "StudentProfile", "field": "dob"},
                        ],
                    },
                ],
            },
        ],
    }


def test_valid_citations(sample_auditspec):
    text = "Access is controlled (DSL ref: User.permit) and data classified (DSL ref: StudentProfile.classify)."
    issues = validate_citations(text, sample_auditspec)
    assert issues == []


def test_invalid_citation(sample_auditspec):
    text = "See DSL ref: Nonexistent.permit for details."
    issues = validate_citations(text, sample_auditspec)
    assert len(issues) == 1
    assert "Nonexistent.permit" in issues[0]


def test_mixed_citations(sample_auditspec):
    text = "Valid (DSL ref: User.permit) and invalid (DSL ref: Foo.bar)."
    issues = validate_citations(text, sample_auditspec)
    assert len(issues) == 1
    assert "Foo.bar" in issues[0]


def test_no_citations():
    text = "No citations here at all."
    issues = validate_citations(text, {"controls": []})
    assert issues == []


def test_citation_pattern():
    text = "DSL ref: Entity.construct"
    match = CITATION_PATTERN.search(text)
    assert match is not None
    assert match.group(1) == "Entity"
    assert match.group(2) == "construct"


def test_empty_auditspec():
    text = "DSL ref: User.permit"
    issues = validate_citations(text, {"controls": []})
    assert len(issues) == 1
