"""Tests for compliance AuditSpec compiler."""

from dazzle.compliance.compiler import compile_auditspec
from dazzle.compliance.models import (
    AuditSpec,
    Control,
    DslEvidence,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
    Theme,
)


def _mini_taxonomy() -> Taxonomy:
    return Taxonomy(
        id="test",
        name="Test Framework",
        themes=[
            Theme(
                id="org",
                name="Organisational",
                controls=[
                    Control(
                        id="C-1",
                        name="Access Control",
                        dsl_evidence=[DslEvidence(construct="permit")],
                    ),
                    Control(
                        id="C-2",
                        name="Data Classification",
                        dsl_evidence=[DslEvidence(construct="classify")],
                    ),
                    Control(
                        id="C-3",
                        name="Workflow Control",
                        dsl_evidence=[DslEvidence(construct="transitions")],
                    ),
                ],
            )
        ],
    )


def _evidence_with_permit() -> EvidenceMap:
    return EvidenceMap(
        items={
            "permit": [
                EvidenceItem(
                    entity="Task",
                    construct="permit",
                    detail="create: authenticated",
                    dsl_ref="Task.permit",
                )
            ],
            "classify": [],
        },
        dsl_hash="sha256:abc123",
    )


class TestCompileAuditspec:
    def test_returns_audit_spec(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        assert isinstance(result, AuditSpec)

    def test_evidenced_control(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        c1 = next(c for c in result.controls if c.control_id == "C-1")
        assert c1.status == "evidenced"
        assert c1.tier == 1

    def test_gap_control(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        c3 = next(c for c in result.controls if c.control_id == "C-3")
        assert c3.status == "gap"
        assert c3.tier == 3

    def test_summary_counts(self) -> None:
        result = compile_auditspec(_mini_taxonomy(), _evidence_with_permit())
        assert result.summary.total_controls == 3
        assert result.summary.evidenced == 1
        assert result.summary.gaps == 2

    def test_empty_evidence_all_gaps(self) -> None:
        empty = EvidenceMap(items={}, dsl_hash="sha256:empty")
        result = compile_auditspec(_mini_taxonomy(), empty)
        assert result.summary.gaps == 3
        assert result.summary.evidenced == 0

    def test_construct_to_key_mapping(self) -> None:
        """grant_schema evidence should match 'permit' controls."""
        evidence = EvidenceMap(
            items={
                "grant_schema": [
                    EvidenceItem(
                        entity="School",
                        construct="grant_schema",
                        detail="delegation",
                        dsl_ref="School.grant_schema",
                    )
                ],
            },
            dsl_hash="sha256:test",
        )
        result = compile_auditspec(_mini_taxonomy(), evidence)
        c1 = next(c for c in result.controls if c.control_id == "C-1")
        assert c1.status == "evidenced"
