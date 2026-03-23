"""Tests for dazzle.compliance.compiler module."""

from pathlib import Path

import pytest

from dazzle.compliance.compiler import (
    _compute_status,
    compile_auditspec,
)
from dazzle.compliance.taxonomy import load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "compliance"


@pytest.fixture
def mini_taxonomy():
    return load_taxonomy(FIXTURES / "mini_taxonomy.yaml")


@pytest.fixture
def full_evidence():
    """Evidence that covers all constructs in the mini taxonomy."""
    return {
        "classify": [{"entity": "User", "field": "email", "classification": "pii"}],
        "permit": {"User": {"operations": {"read": ["admin"]}}},
        "scope": [{"entity": "User", "operation": "read", "rule": "school = current_user.school"}],
        "transitions": [
            {"entity": "Order", "from_state": "draft", "to_state": "submitted", "roles": ["admin"]}
        ],
        "processes": [{"name": "onboard", "title": "Onboarding"}],
        "visible": [{"context": "User", "type": "field", "roles": ["admin"]}],
        "stories": [{"title": "Admin creates user", "story_id": "S1"}],
        "personas": [{"name": "admin", "label": "Administrator"}],
    }


@pytest.fixture
def empty_evidence():
    return {
        "classify": [],
        "permit": {},
        "scope": [],
        "transitions": [],
        "processes": [],
        "visible": [],
        "stories": [],
        "personas": [],
    }


def test_compile_produces_auditspec(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="entity Foo")
    assert result["auditspec_version"] == "1.0"
    assert result["framework"] == "mini_test"
    assert "summary" in result
    assert "controls" in result
    assert len(result["controls"]) == 5


def test_summary_counts(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="entity Foo")
    s = result["summary"]
    assert s["total_controls"] == 5
    # AC-1 (permit), AC-2 (classify), AC-3 (scope) -> evidenced
    # OP-1 (transitions+processes) -> evidenced
    # OP-2 (no dsl_evidence) -> gap
    assert s["evidenced"] == 4
    assert s["gaps"] == 1


def test_all_gaps_when_no_evidence(mini_taxonomy, empty_evidence):
    result = compile_auditspec(mini_taxonomy, empty_evidence, "test.dsl", dsl_content="")
    s = result["summary"]
    # AC-1..AC-3 + OP-1 have dsl_evidence mappings but no data -> gap
    # OP-2 has no dsl_evidence -> gap (tier 3)
    assert s["gaps"] == 5
    assert s["evidenced"] == 0


def test_dsl_hash_present(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="hello")
    assert result["dsl_hash"].startswith("sha256:")


def test_control_status_values(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="")
    statuses = {c["id"]: c["status"] for c in result["controls"]}
    assert statuses["AC-1"] == "evidenced"
    assert statuses["OP-2"] == "gap"


def test_compute_status():
    assert _compute_status([{"x": 1}], []) == "evidenced"
    assert _compute_status([], [{"x": 1}]) == "gap"
    assert _compute_status([{"x": 1}], [{"y": 2}]) == "partial"


def test_partial_evidence(mini_taxonomy):
    """OP-1 requires transitions AND processes — provide only transitions."""
    evidence = {
        "classify": [],
        "permit": {},
        "scope": [],
        "transitions": [{"entity": "Order", "from_state": "a", "to_state": "b"}],
        "processes": [],
        "visible": [],
        "stories": [],
        "personas": [],
    }
    result = compile_auditspec(mini_taxonomy, evidence, "test.dsl", dsl_content="")
    op1 = next(c for c in result["controls"] if c["id"] == "OP-1")
    assert op1["status"] == "partial"
    assert len(op1["evidence"]) == 1
    assert len(op1["gaps"]) == 1


def test_generated_at_present(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="")
    assert "generated_at" in result


def test_theme_assigned(mini_taxonomy, full_evidence):
    result = compile_auditspec(mini_taxonomy, full_evidence, "test.dsl", dsl_content="")
    ac1 = next(c for c in result["controls"] if c["id"] == "AC-1")
    assert ac1["theme"] == "theme_access"
    op1 = next(c for c in result["controls"] if c["id"] == "OP-1")
    assert op1["theme"] == "theme_ops"
