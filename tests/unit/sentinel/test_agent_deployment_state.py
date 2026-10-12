"""Tests for the Deployment & State detection agent (DS-05 and DS-08)."""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.governance import DataClassification
from dazzle.sentinel.agents.deployment_state import DeploymentStateAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, make_entity, pk_field, str_field


@pytest.fixture
def agent() -> DeploymentStateAgent:
    return DeploymentStateAgent()


# ---------------------------------------------------------------------------
# Policies helper
# ---------------------------------------------------------------------------


def _make_classification(
    entity: str,
    field: str,
    classification: DataClassification,
) -> MagicMock:
    cls_spec = MagicMock()
    cls_spec.entity = entity
    cls_spec.field = field
    cls_spec.classification = classification
    return cls_spec


def _make_erasure(entity: str) -> MagicMock:
    erasure = MagicMock()
    erasure.entity = entity
    return erasure


def _make_policies(
    *,
    classifications: list[MagicMock] | None = None,
    erasures: list[MagicMock] | None = None,
    audit_access: bool = True,
) -> MagicMock:
    policies = MagicMock()
    policies.classifications = classifications or []
    policies.erasures = erasures or []
    policies.audit_access = audit_access
    return policies


# =============================================================================
# DS-05  PII data without erasure policy
# =============================================================================


class TestDS05PiiWithoutErasure:
    @pytest.mark.parametrize(
        ("entity", "field", "classification"),
        [
            ("Customer", "email", DataClassification.PII_DIRECT),
            ("User", "ip_addr", DataClassification.PII_INDIRECT),
            ("Patient", "diagnosis", DataClassification.PII_SENSITIVE),
        ],
        ids=["pii_direct", "pii_indirect", "pii_sensitive"],
    )
    def test_flags_all_pii_classifications_without_erasure(
        self,
        agent: DeploymentStateAgent,
        entity: str,
        field: str,
        classification: DataClassification,
    ) -> None:
        cls_spec = _make_classification(entity, field, classification)
        policies = _make_policies(classifications=[cls_spec], erasures=[])
        findings = agent.pii_without_erasure(make_appspec(policies=policies))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-05"
        assert findings[0].severity == Severity.HIGH
        assert entity in findings[0].title

    def test_passes_when_erasure_exists(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        erasure = _make_erasure("Customer")
        policies = _make_policies(classifications=[cls_spec], erasures=[erasure])
        assert agent.pii_without_erasure(make_appspec(policies=policies)) == []

    @pytest.mark.parametrize(
        "policies_factory",
        [
            lambda: None,
            lambda: _make_policies(
                classifications=[
                    _make_classification("Order", "amount", DataClassification.FINANCIAL_TXN)
                ],
                erasures=[],
            ),
            lambda: _make_policies(classifications=[], erasures=[]),
        ],
        ids=["no_policies", "no_pii_classifications", "empty_classifications"],
    )
    def test_returns_empty_for_non_pii_or_empty(
        self, agent: DeploymentStateAgent, policies_factory: object
    ) -> None:
        policies = policies_factory()  # type: ignore[operator]
        assert agent.pii_without_erasure(make_appspec(policies=policies)) == []

    def test_multiple_entities_flags_only_without_erasure(
        self, agent: DeploymentStateAgent
    ) -> None:
        cls1 = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        cls2 = _make_classification("Employee", "ssn", DataClassification.PII_SENSITIVE)
        erasure = _make_erasure("Customer")
        policies = _make_policies(classifications=[cls1, cls2], erasures=[erasure])
        findings = agent.pii_without_erasure(make_appspec(policies=policies))
        assert len(findings) == 1
        assert "Employee" in findings[0].title

    def test_multiple_pii_fields_same_entity(self, agent: DeploymentStateAgent) -> None:
        cls1 = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        cls2 = _make_classification("Customer", "phone", DataClassification.PII_DIRECT)
        policies = _make_policies(classifications=[cls1, cls2], erasures=[])
        findings = agent.pii_without_erasure(make_appspec(policies=policies))
        assert len(findings) == 1
        assert "email" in findings[0].description
        assert "phone" in findings[0].description


# =============================================================================
# DS-08  Audit access disabled with sensitive data
# =============================================================================


class TestDS08AuditAccessDisabledSensitive:
    @pytest.mark.parametrize(
        ("entity", "field", "classification"),
        [
            ("Customer", "email", DataClassification.PII_DIRECT),
            ("Payment", "amount", DataClassification.FINANCIAL_TXN),
            ("Account", "card_number", DataClassification.FINANCIAL_ACCOUNT),
        ],
        ids=["pii_direct", "financial_txn", "financial_account"],
    )
    def test_flags_audit_disabled_with_sensitive_classification(
        self,
        agent: DeploymentStateAgent,
        entity: str,
        field: str,
        classification: DataClassification,
    ) -> None:
        cls_spec = _make_classification(entity, field, classification)
        policies = _make_policies(classifications=[cls_spec], audit_access=False)
        findings = agent.audit_access_disabled_sensitive(make_appspec(policies=policies))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-08"
        assert findings[0].severity == Severity.HIGH
        assert "Audit access disabled" in findings[0].title

    @pytest.mark.parametrize(
        "policies_factory",
        [
            lambda: _make_policies(
                classifications=[
                    _make_classification("Customer", "email", DataClassification.PII_DIRECT)
                ],
                audit_access=True,
            ),
            lambda: None,
            lambda: _make_policies(classifications=[], audit_access=False),
        ],
        ids=["audit_enabled", "no_policies", "no_sensitive_data"],
    )
    def test_no_finding(self, agent: DeploymentStateAgent, policies_factory: object) -> None:
        policies = policies_factory()  # type: ignore[operator]
        assert agent.audit_access_disabled_sensitive(make_appspec(policies=policies)) == []

    def test_affected_entities_sorted_in_description(self, agent: DeploymentStateAgent) -> None:
        cls1 = _make_classification("Zebra", "ssn", DataClassification.PII_SENSITIVE)
        cls2 = _make_classification("Alpha", "card", DataClassification.FINANCIAL_ACCOUNT)
        policies = _make_policies(classifications=[cls1, cls2], audit_access=False)
        findings = agent.audit_access_disabled_sensitive(make_appspec(policies=policies))
        assert len(findings) == 1
        # Single finding aggregates all sensitive entities.
        assert "Alpha" in findings[0].description
        assert "Zebra" in findings[0].description


# =============================================================================
# Full agent run
# =============================================================================


class TestDeploymentStateAgentRun:
    def test_agent_id(self, agent: DeploymentStateAgent) -> None:
        assert agent.agent_id == AgentId.DS

    def test_has_2_heuristics(self, agent: DeploymentStateAgent) -> None:
        assert len(agent.get_heuristics()) == 2

    def test_heuristic_ids(self, agent: DeploymentStateAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == ["DS-05", "DS-08"]

    def test_clean_appspec_no_findings(self, agent: DeploymentStateAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.findings == []
        assert result.errors == []

    def test_run_returns_agent_result_with_timing(self, agent: DeploymentStateAgent) -> None:
        result = agent.run(make_appspec())
        assert result.agent == AgentId.DS
        assert result.duration_ms >= 0
