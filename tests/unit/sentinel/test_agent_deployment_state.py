"""Tests for the Deployment & State detection agent (DS-01 through DS-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.governance import DataClassification, InterfaceAuthMethod
from dazzle.core.ir.messaging import ChannelKind, DeliveryMode
from dazzle.sentinel.agents.deployment_state import DeploymentStateAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, make_entity, pk_field, str_field


@pytest.fixture
def agent() -> DeploymentStateAgent:
    return DeploymentStateAgent()


# ---------------------------------------------------------------------------
# Interface helpers
# ---------------------------------------------------------------------------


def _make_interface(
    name: str,
    *,
    auth: InterfaceAuthMethod = InterfaceAuthMethod.NONE,
    rate_limit: str | None = None,
) -> MagicMock:
    iface = MagicMock()
    iface.name = name
    iface.auth = auth
    iface.rate_limit = rate_limit
    return iface


def _make_interfaces(apis: list[MagicMock]) -> MagicMock:
    interfaces = MagicMock()
    interfaces.apis = apis
    return interfaces


# ---------------------------------------------------------------------------
# Transaction helper
# ---------------------------------------------------------------------------


def _make_transaction(
    name: str,
    *,
    idempotency_key: str = "",
    validation: list | None = None,
) -> MagicMock:
    txn = MagicMock()
    txn.name = name
    txn.idempotency_key = idempotency_key
    txn.validation = validation if validation is not None else []
    return txn


# ---------------------------------------------------------------------------
# Channel helper
# ---------------------------------------------------------------------------


def _make_send_op(
    name: str = "default_send",
    *,
    delivery_mode: DeliveryMode = DeliveryMode.DIRECT,
) -> MagicMock:
    op = MagicMock()
    op.name = name
    op.delivery_mode = delivery_mode
    return op


def _make_channel(
    name: str,
    *,
    kind: ChannelKind = ChannelKind.QUEUE,
    send_operations: list[MagicMock] | None = None,
    provider_config: object | None = None,
) -> MagicMock:
    channel = MagicMock()
    channel.name = name
    channel.kind = kind
    channel.send_operations = send_operations if send_operations is not None else []
    channel.provider_config = provider_config
    return channel


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
# DS-01  Interface API without authentication
# =============================================================================


class TestDS01InterfaceWithoutAuth:
    def test_flags_interface_with_auth_none(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", auth=InterfaceAuthMethod.NONE)
        interfaces = _make_interfaces([iface])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_auth(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-01"
        assert findings[0].severity == Severity.HIGH
        assert "orders_api" in findings[0].title

    def test_passes_with_oauth2(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", auth=InterfaceAuthMethod.OAUTH2)
        interfaces = _make_interfaces([iface])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_auth(appspec)
        assert findings == []

    def test_passes_with_api_key(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", auth=InterfaceAuthMethod.API_KEY)
        interfaces = _make_interfaces([iface])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_auth(appspec)
        assert findings == []

    def test_no_interfaces_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(interfaces=None)
        findings = agent.interface_without_auth(appspec)
        assert findings == []

    def test_multiple_interfaces_flags_only_unauthenticated(
        self, agent: DeploymentStateAgent
    ) -> None:
        good = _make_interface("secure_api", auth=InterfaceAuthMethod.JWT)
        bad = _make_interface("public_api", auth=InterfaceAuthMethod.NONE)
        interfaces = _make_interfaces([good, bad])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_auth(appspec)
        assert len(findings) == 1
        assert "public_api" in findings[0].title

    def test_empty_apis_list(self, agent: DeploymentStateAgent) -> None:
        interfaces = _make_interfaces([])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_auth(appspec)
        assert findings == []


# =============================================================================
# DS-02  Interface API without rate limiting
# =============================================================================


class TestDS02InterfaceWithoutRateLimit:
    def test_flags_interface_without_rate_limit(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", rate_limit=None)
        interfaces = _make_interfaces([iface])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_rate_limit(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-02"
        assert findings[0].severity == Severity.MEDIUM
        assert "orders_api" in findings[0].title

    def test_passes_with_rate_limit(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", rate_limit="1000/hour")
        interfaces = _make_interfaces([iface])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_rate_limit(appspec)
        assert findings == []

    def test_no_interfaces_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(interfaces=None)
        findings = agent.interface_without_rate_limit(appspec)
        assert findings == []

    def test_multiple_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        ok = _make_interface("secure_api", rate_limit="500/minute")
        bad = _make_interface("open_api", rate_limit=None)
        interfaces = _make_interfaces([ok, bad])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_rate_limit(appspec)
        assert len(findings) == 1
        assert "open_api" in findings[0].title

    def test_empty_apis_list(self, agent: DeploymentStateAgent) -> None:
        interfaces = _make_interfaces([])
        appspec = make_appspec(interfaces=interfaces)
        findings = agent.interface_without_rate_limit(appspec)
        assert findings == []


# =============================================================================
# DS-03  Transaction without idempotency key
# =============================================================================


class TestDS03TransactionWithoutIdempotency:
    def test_flags_empty_idempotency_key(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", idempotency_key="")
        appspec = make_appspec(transactions=[txn])
        findings = agent.transaction_without_idempotency(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-03"
        assert findings[0].severity == Severity.HIGH
        assert "RecordPayment" in findings[0].title

    def test_passes_with_idempotency_key(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", idempotency_key="payment.id")
        appspec = make_appspec(transactions=[txn])
        findings = agent.transaction_without_idempotency(appspec)
        assert findings == []

    def test_no_transactions_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(transactions=[])
        findings = agent.transaction_without_idempotency(appspec)
        assert findings == []

    def test_multiple_transactions_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        good = _make_transaction("SafePayment", idempotency_key="order.id")
        bad = _make_transaction("UnsafeTransfer", idempotency_key="")
        appspec = make_appspec(transactions=[good, bad])
        findings = agent.transaction_without_idempotency(appspec)
        assert len(findings) == 1
        assert "UnsafeTransfer" in findings[0].title


# =============================================================================
# DS-04  Queue channel with direct delivery
# =============================================================================


class TestDS04QueueDirectDelivery:
    def test_flags_queue_with_direct_send(self, agent: DeploymentStateAgent) -> None:
        op = _make_send_op("order_send", delivery_mode=DeliveryMode.DIRECT)
        channel = _make_channel("order_queue", kind=ChannelKind.QUEUE, send_operations=[op])
        appspec = make_appspec(channels=[channel])
        findings = agent.queue_direct_delivery(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-04"
        assert findings[0].severity == Severity.MEDIUM
        assert "order_queue" in findings[0].title

    def test_passes_queue_with_outbox_send(self, agent: DeploymentStateAgent) -> None:
        op = _make_send_op("order_send", delivery_mode=DeliveryMode.OUTBOX)
        channel = _make_channel("order_queue", kind=ChannelKind.QUEUE, send_operations=[op])
        appspec = make_appspec(channels=[channel])
        findings = agent.queue_direct_delivery(appspec)
        assert findings == []

    def test_ignores_non_queue_channel_with_direct(self, agent: DeploymentStateAgent) -> None:
        op = _make_send_op("email_send", delivery_mode=DeliveryMode.DIRECT)
        channel = _make_channel("notifications", kind=ChannelKind.EMAIL, send_operations=[op])
        appspec = make_appspec(channels=[channel])
        findings = agent.queue_direct_delivery(appspec)
        assert findings == []

    def test_ignores_stream_channel(self, agent: DeploymentStateAgent) -> None:
        op = _make_send_op("event_send", delivery_mode=DeliveryMode.DIRECT)
        channel = _make_channel("events", kind=ChannelKind.STREAM, send_operations=[op])
        appspec = make_appspec(channels=[channel])
        findings = agent.queue_direct_delivery(appspec)
        assert findings == []

    def test_no_channels_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(channels=[])
        findings = agent.queue_direct_delivery(appspec)
        assert findings == []

    def test_multiple_channels_flags_only_queue_direct(self, agent: DeploymentStateAgent) -> None:
        ok_op = _make_send_op("safe_send", delivery_mode=DeliveryMode.OUTBOX)
        ok = _make_channel("safe_queue", kind=ChannelKind.QUEUE, send_operations=[ok_op])
        bad_op = _make_send_op("risky_send", delivery_mode=DeliveryMode.DIRECT)
        bad = _make_channel("risky_queue", kind=ChannelKind.QUEUE, send_operations=[bad_op])
        email_op = _make_send_op("alert_send", delivery_mode=DeliveryMode.DIRECT)
        email = _make_channel("alerts", kind=ChannelKind.EMAIL, send_operations=[email_op])
        appspec = make_appspec(channels=[ok, bad, email])
        findings = agent.queue_direct_delivery(appspec)
        assert len(findings) == 1
        assert "risky_queue" in findings[0].title


# =============================================================================
# DS-05  PII data without erasure policy
# =============================================================================


class TestDS05PiiWithoutErasure:
    def test_flags_pii_entity_without_erasure(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        policies = _make_policies(classifications=[cls_spec], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-05"
        assert findings[0].severity == Severity.HIGH
        assert "Customer" in findings[0].title

    def test_passes_when_erasure_exists(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        erasure = _make_erasure("Customer")
        policies = _make_policies(classifications=[cls_spec], erasures=[erasure])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert findings == []

    def test_no_policies_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(policies=None)
        findings = agent.pii_without_erasure(appspec)
        assert findings == []

    def test_no_pii_classifications_returns_empty(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Order", "amount", DataClassification.FINANCIAL_TXN)
        policies = _make_policies(classifications=[cls_spec], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert findings == []

    def test_flags_pii_indirect(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("User", "ip_addr", DataClassification.PII_INDIRECT)
        policies = _make_policies(classifications=[cls_spec], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert len(findings) == 1
        assert "User" in findings[0].title

    def test_flags_pii_sensitive(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Patient", "diagnosis", DataClassification.PII_SENSITIVE)
        policies = _make_policies(classifications=[cls_spec], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert len(findings) == 1
        assert "Patient" in findings[0].title

    def test_multiple_entities_flags_only_without_erasure(
        self, agent: DeploymentStateAgent
    ) -> None:
        cls1 = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        cls2 = _make_classification("Employee", "ssn", DataClassification.PII_SENSITIVE)
        erasure = _make_erasure("Customer")
        policies = _make_policies(classifications=[cls1, cls2], erasures=[erasure])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert len(findings) == 1
        assert "Employee" in findings[0].title

    def test_multiple_pii_fields_same_entity(self, agent: DeploymentStateAgent) -> None:
        cls1 = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        cls2 = _make_classification("Customer", "phone", DataClassification.PII_DIRECT)
        policies = _make_policies(classifications=[cls1, cls2], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        # Should produce one finding per entity, not per field
        assert len(findings) == 1
        assert "email" in findings[0].description
        assert "phone" in findings[0].description

    def test_empty_classifications(self, agent: DeploymentStateAgent) -> None:
        policies = _make_policies(classifications=[], erasures=[])
        appspec = make_appspec(policies=policies)
        findings = agent.pii_without_erasure(appspec)
        assert findings == []


# =============================================================================
# DS-06  Transaction without validation rules
# =============================================================================


class TestDS06TransactionWithoutValidations:
    def test_flags_transaction_without_validation(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", validation=[])
        appspec = make_appspec(transactions=[txn])
        findings = agent.transaction_without_validations(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "RecordPayment" in findings[0].title

    def test_passes_with_validation(self, agent: DeploymentStateAgent) -> None:
        rule = MagicMock()
        txn = _make_transaction("RecordPayment", validation=[rule])
        appspec = make_appspec(transactions=[txn])
        findings = agent.transaction_without_validations(appspec)
        assert findings == []

    def test_no_transactions_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(transactions=[])
        findings = agent.transaction_without_validations(appspec)
        assert findings == []

    def test_multiple_transactions_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        rule = MagicMock()
        good = _make_transaction("SafePayment", validation=[rule])
        bad = _make_transaction("UnsafeTransfer", validation=[])
        appspec = make_appspec(transactions=[good, bad])
        findings = agent.transaction_without_validations(appspec)
        assert len(findings) == 1
        assert "UnsafeTransfer" in findings[0].title


# =============================================================================
# DS-07  Channel without throttle configuration
# =============================================================================


class TestDS07ChannelWithoutThrottle:
    def test_flags_channel_without_provider_config(self, agent: DeploymentStateAgent) -> None:
        channel = _make_channel("notifications", provider_config=None)
        appspec = make_appspec(channels=[channel])
        findings = agent.channel_without_throttle(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-07"
        assert findings[0].severity == Severity.LOW
        assert "notifications" in findings[0].title

    def test_passes_with_provider_config(self, agent: DeploymentStateAgent) -> None:
        prov = MagicMock()
        channel = _make_channel("notifications", provider_config=prov)
        appspec = make_appspec(channels=[channel])
        findings = agent.channel_without_throttle(appspec)
        assert findings == []

    def test_no_channels_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(channels=[])
        findings = agent.channel_without_throttle(appspec)
        assert findings == []

    def test_multiple_channels_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        prov = MagicMock()
        ok = _make_channel("safe_channel", provider_config=prov)
        bad = _make_channel("open_channel", provider_config=None)
        appspec = make_appspec(channels=[ok, bad])
        findings = agent.channel_without_throttle(appspec)
        assert len(findings) == 1
        assert "open_channel" in findings[0].title

    def test_flags_all_channel_kinds(self, agent: DeploymentStateAgent) -> None:
        channels = [
            _make_channel("email_ch", kind=ChannelKind.EMAIL, provider_config=None),
            _make_channel("queue_ch", kind=ChannelKind.QUEUE, provider_config=None),
            _make_channel("stream_ch", kind=ChannelKind.STREAM, provider_config=None),
        ]
        appspec = make_appspec(channels=channels)
        findings = agent.channel_without_throttle(appspec)
        assert len(findings) == 3


# =============================================================================
# DS-08  Audit access disabled with sensitive data
# =============================================================================


class TestDS08AuditAccessDisabledSensitive:
    def test_flags_audit_disabled_with_pii(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        policies = _make_policies(classifications=[cls_spec], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-08"
        assert findings[0].severity == Severity.HIGH
        assert "Audit access disabled" in findings[0].title

    def test_flags_audit_disabled_with_financial_txn(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Payment", "amount", DataClassification.FINANCIAL_TXN)
        policies = _make_policies(classifications=[cls_spec], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert len(findings) == 1

    def test_flags_audit_disabled_with_financial_account(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification(
            "Account", "card_number", DataClassification.FINANCIAL_ACCOUNT
        )
        policies = _make_policies(classifications=[cls_spec], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert len(findings) == 1

    def test_passes_with_audit_enabled(self, agent: DeploymentStateAgent) -> None:
        cls_spec = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        policies = _make_policies(classifications=[cls_spec], audit_access=True)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert findings == []

    def test_no_policies_returns_empty(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec(policies=None)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert findings == []

    def test_audit_disabled_no_sensitive_data(self, agent: DeploymentStateAgent) -> None:
        """audit_access=False but no sensitive classifications => no finding."""
        policies = _make_policies(classifications=[], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert findings == []

    def test_affected_entities_sorted_in_description(self, agent: DeploymentStateAgent) -> None:
        cls1 = _make_classification("Zebra", "ssn", DataClassification.PII_SENSITIVE)
        cls2 = _make_classification("Alpha", "card", DataClassification.FINANCIAL_ACCOUNT)
        policies = _make_policies(classifications=[cls1, cls2], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        assert len(findings) == 1
        # Entity names should appear sorted in description
        assert "Alpha" in findings[0].description
        assert "Zebra" in findings[0].description

    def test_single_finding_for_multiple_sensitive_entities(
        self, agent: DeploymentStateAgent
    ) -> None:
        cls1 = _make_classification("Customer", "email", DataClassification.PII_DIRECT)
        cls2 = _make_classification("Payment", "amount", DataClassification.FINANCIAL_TXN)
        policies = _make_policies(classifications=[cls1, cls2], audit_access=False)
        appspec = make_appspec(policies=policies)
        findings = agent.audit_access_disabled_sensitive(appspec)
        # DS-08 produces exactly one finding, not one per entity
        assert len(findings) == 1


# =============================================================================
# Full agent run
# =============================================================================


class TestDeploymentStateAgentRun:
    def test_agent_id(self, agent: DeploymentStateAgent) -> None:
        assert agent.agent_id == AgentId.DS

    def test_has_8_heuristics(self, agent: DeploymentStateAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: DeploymentStateAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"DS-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_findings(self, agent: DeploymentStateAgent) -> None:
        """A minimal appspec with no interfaces/transactions/channels/policies produces zero findings."""
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.findings == []
        assert result.errors == []

    def test_run_aggregates_across_heuristics(self, agent: DeploymentStateAgent) -> None:
        """A spec that triggers multiple heuristics produces findings from each."""
        # DS-01: interface without auth
        iface = _make_interface("orders_api", auth=InterfaceAuthMethod.NONE)
        interfaces = _make_interfaces([iface])

        # DS-03: transaction without idempotency
        txn = _make_transaction("RecordPayment", idempotency_key="")

        # DS-07: channel without provider config
        channel = _make_channel("alerts", provider_config=None)

        appspec = make_appspec(
            interfaces=interfaces,
            transactions=[txn],
            channels=[channel],
        )
        result = agent.run(appspec)
        heuristic_ids = {f.heuristic_id for f in result.findings}
        # At minimum we expect DS-01, DS-02 (rate_limit=None default), DS-03, DS-04 (queue+direct defaults), DS-06 (empty validations), DS-07
        assert "DS-01" in heuristic_ids
        assert "DS-03" in heuristic_ids
        assert "DS-07" in heuristic_ids
        assert result.errors == []

    def test_run_returns_agent_result_with_timing(self, agent: DeploymentStateAgent) -> None:
        appspec = make_appspec()
        result = agent.run(appspec)
        assert result.agent == AgentId.DS
        assert result.duration_ms >= 0
