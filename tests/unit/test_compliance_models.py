"""Tests for compliance Pydantic models."""

from dazzle.compliance.models import (
    AuditSpec,
    AuditSummary,
    Control,
    ControlResult,
    DslEvidence,
    EvidenceItem,
    EvidenceMap,
    Taxonomy,
    Theme,
)


class TestTaxonomyModels:
    def test_control_with_evidence(self) -> None:
        ctrl = Control(
            id="A.5.1",
            name="Policies",
            objective="Management direction",
            dsl_evidence=[DslEvidence(construct="classify")],
        )
        assert ctrl.id == "A.5.1"
        assert len(ctrl.dsl_evidence) == 1

    def test_taxonomy_round_trip(self) -> None:
        tax = Taxonomy(
            id="iso27001",
            name="ISO 27001:2022",
            version="2022",
            body="ISO",
            themes=[
                Theme(
                    id="org",
                    name="Organisational",
                    controls=[Control(id="A.5.1", name="Policies")],
                )
            ],
        )
        data = tax.model_dump()
        assert data["body"] == "ISO"
        assert len(data["themes"][0]["controls"]) == 1


class TestEvidenceModels:
    def test_evidence_item(self) -> None:
        item = EvidenceItem(
            entity="Customer",
            construct="classify",
            detail="PII_DIRECT on email",
            dsl_ref="Customer.classify",
        )
        assert item.entity == "Customer"

    def test_evidence_map_keying(self) -> None:
        emap = EvidenceMap(
            items={"classify": [], "permit": []},
            dsl_hash="sha256:abc123",
        )
        assert "classify" in emap.items


class TestAuditSpecModels:
    def test_control_result_tier_mapping(self) -> None:
        cr = ControlResult(
            control_id="A.5.1",
            control_name="Policies",
            theme_id="org",
            status="evidenced",
            tier=1,
            evidence=[],
        )
        assert cr.tier == 1

    def test_excluded_tier_zero(self) -> None:
        cr = ControlResult(
            control_id="A.5.1",
            control_name="Policies",
            theme_id="org",
            status="excluded",
            tier=0,
            evidence=[],
        )
        assert cr.tier == 0

    def test_audit_spec_summary(self) -> None:
        spec = AuditSpec(
            framework_id="iso27001",
            framework_name="ISO 27001:2022",
            generated_at="2026-03-23T00:00:00Z",
            dsl_hash="sha256:abc",
            controls=[],
            summary=AuditSummary(
                total_controls=0,
                evidenced=0,
                partial=0,
                gaps=0,
                excluded=0,
            ),
        )
        assert spec.framework_id == "iso27001"
