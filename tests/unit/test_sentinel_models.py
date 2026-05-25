"""Tests for Sentinel Pydantic models."""

from dazzle.sentinel.models import AgentId, Finding, Severity


def test_finding_carries_catalogue_entry() -> None:
    """A Finding may declare which counter-prior catalogue entry it enforces."""
    f = Finding(
        agent=AgentId.PA,
        heuristic_id="PA-LLM-07",
        category="python_audit",
        subcategory="llm_bias",
        severity=Severity.MEDIUM,
        title="exceptions as control flow",
        description="x",
        catalogue_entry="exceptions-as-control-flow",
    )
    assert f.catalogue_entry == "exceptions-as-control-flow"


def test_finding_catalogue_entry_defaults_none() -> None:
    """Findings unrelated to the catalogue may omit the field."""
    f = Finding(
        agent=AgentId.PA,
        heuristic_id="PA-UP001",
        category="python_audit",
        subcategory="modernisation",
        severity=Severity.LOW,
        title="x",
        description="y",
    )
    assert f.catalogue_entry is None
