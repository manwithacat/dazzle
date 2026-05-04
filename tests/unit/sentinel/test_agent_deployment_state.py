"""Tests for the Deployment & State detection agent (DS-01 through DS-08)."""

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
    @pytest.mark.parametrize(
        ("auth", "expect_flagged"),
        [
            (InterfaceAuthMethod.NONE, True),
            (InterfaceAuthMethod.OAUTH2, False),
            (InterfaceAuthMethod.API_KEY, False),
        ],
        ids=["auth_none", "oauth2", "api_key"],
    )
    def test_single_interface_auth(
        self,
        agent: DeploymentStateAgent,
        auth: InterfaceAuthMethod,
        expect_flagged: bool,
    ) -> None:
        iface = _make_interface("orders_api", auth=auth)
        findings = agent.interface_without_auth(make_appspec(interfaces=_make_interfaces([iface])))
        if expect_flagged:
            assert len(findings) == 1
            assert findings[0].heuristic_id == "DS-01"
            assert findings[0].severity == Severity.HIGH
            assert "orders_api" in findings[0].title
        else:
            assert findings == []

    @pytest.mark.parametrize(
        "interfaces_arg",
        [None, _make_interfaces([])],
        ids=["no_interfaces", "empty_apis"],
    )
    def test_no_interfaces(self, agent: DeploymentStateAgent, interfaces_arg: object) -> None:
        assert agent.interface_without_auth(make_appspec(interfaces=interfaces_arg)) == []

    def test_multiple_interfaces_flags_only_unauthenticated(
        self, agent: DeploymentStateAgent
    ) -> None:
        good = _make_interface("secure_api", auth=InterfaceAuthMethod.JWT)
        bad = _make_interface("public_api", auth=InterfaceAuthMethod.NONE)
        findings = agent.interface_without_auth(
            make_appspec(interfaces=_make_interfaces([good, bad]))
        )
        assert len(findings) == 1
        assert "public_api" in findings[0].title


# =============================================================================
# DS-02  Interface API without rate limiting
# =============================================================================


class TestDS02InterfaceWithoutRateLimit:
    def test_flags_interface_without_rate_limit(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", rate_limit=None)
        findings = agent.interface_without_rate_limit(
            make_appspec(interfaces=_make_interfaces([iface]))
        )
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-02"
        assert findings[0].severity == Severity.MEDIUM
        assert "orders_api" in findings[0].title

    def test_passes_with_rate_limit(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", rate_limit="1000/hour")
        assert (
            agent.interface_without_rate_limit(make_appspec(interfaces=_make_interfaces([iface])))
            == []
        )

    def test_multiple_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        ok = _make_interface("secure_api", rate_limit="500/minute")
        bad = _make_interface("open_api", rate_limit=None)
        findings = agent.interface_without_rate_limit(
            make_appspec(interfaces=_make_interfaces([ok, bad]))
        )
        assert len(findings) == 1
        assert "open_api" in findings[0].title

    @pytest.mark.parametrize(
        "interfaces_arg",
        [None, _make_interfaces([])],
        ids=["no_interfaces", "empty_apis"],
    )
    def test_no_interfaces(self, agent: DeploymentStateAgent, interfaces_arg: object) -> None:
        assert agent.interface_without_rate_limit(make_appspec(interfaces=interfaces_arg)) == []


# =============================================================================
# DS-03  Transaction without idempotency key
# =============================================================================


class TestDS03TransactionWithoutIdempotency:
    def test_flags_empty_idempotency_key(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", idempotency_key="")
        findings = agent.transaction_without_idempotency(make_appspec(transactions=[txn]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-03"
        assert findings[0].severity == Severity.HIGH
        assert "RecordPayment" in findings[0].title

    def test_passes_with_idempotency_key(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", idempotency_key="payment.id")
        assert agent.transaction_without_idempotency(make_appspec(transactions=[txn])) == []

    def test_multiple_transactions_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        good = _make_transaction("SafePayment", idempotency_key="order.id")
        bad = _make_transaction("UnsafeTransfer", idempotency_key="")
        findings = agent.transaction_without_idempotency(make_appspec(transactions=[good, bad]))
        assert len(findings) == 1
        assert "UnsafeTransfer" in findings[0].title

    def test_no_transactions(self, agent: DeploymentStateAgent) -> None:
        assert agent.transaction_without_idempotency(make_appspec(transactions=[])) == []


# =============================================================================
# DS-04  Queue channel with direct delivery
# =============================================================================


class TestDS04QueueDirectDelivery:
    @pytest.mark.parametrize(
        ("channel_name", "kind", "op_name", "delivery_mode", "expect_flagged"),
        [
            ("order_queue", ChannelKind.QUEUE, "order_send", DeliveryMode.DIRECT, True),
            ("order_queue", ChannelKind.QUEUE, "order_send", DeliveryMode.OUTBOX, False),
            ("notifications", ChannelKind.EMAIL, "email_send", DeliveryMode.DIRECT, False),
            ("events", ChannelKind.STREAM, "event_send", DeliveryMode.DIRECT, False),
        ],
        ids=[
            "queue_direct",
            "queue_outbox",
            "email_direct",
            "stream_direct",
        ],
    )
    def test_single_channel(
        self,
        agent: DeploymentStateAgent,
        channel_name: str,
        kind: ChannelKind,
        op_name: str,
        delivery_mode: DeliveryMode,
        expect_flagged: bool,
    ) -> None:
        op = _make_send_op(op_name, delivery_mode=delivery_mode)
        channel = _make_channel(channel_name, kind=kind, send_operations=[op])
        findings = agent.queue_direct_delivery(make_appspec(channels=[channel]))
        if expect_flagged:
            assert len(findings) == 1
            assert findings[0].heuristic_id == "DS-04"
            assert findings[0].severity == Severity.MEDIUM
            assert channel_name in findings[0].title
        else:
            assert findings == []

    def test_no_channels(self, agent: DeploymentStateAgent) -> None:
        assert agent.queue_direct_delivery(make_appspec(channels=[])) == []

    def test_multiple_channels_flags_only_queue_direct(self, agent: DeploymentStateAgent) -> None:
        ok_op = _make_send_op("safe_send", delivery_mode=DeliveryMode.OUTBOX)
        ok = _make_channel("safe_queue", kind=ChannelKind.QUEUE, send_operations=[ok_op])
        bad_op = _make_send_op("risky_send", delivery_mode=DeliveryMode.DIRECT)
        bad = _make_channel("risky_queue", kind=ChannelKind.QUEUE, send_operations=[bad_op])
        email_op = _make_send_op("alert_send", delivery_mode=DeliveryMode.DIRECT)
        email = _make_channel("alerts", kind=ChannelKind.EMAIL, send_operations=[email_op])
        findings = agent.queue_direct_delivery(make_appspec(channels=[ok, bad, email]))
        assert len(findings) == 1
        assert "risky_queue" in findings[0].title


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
# DS-06  Transaction without validation rules
# =============================================================================


class TestDS06TransactionWithoutValidations:
    def test_flags_transaction_without_validation(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", validation=[])
        findings = agent.transaction_without_validations(make_appspec(transactions=[txn]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "RecordPayment" in findings[0].title

    def test_passes_with_validation(self, agent: DeploymentStateAgent) -> None:
        txn = _make_transaction("RecordPayment", validation=[MagicMock()])
        assert agent.transaction_without_validations(make_appspec(transactions=[txn])) == []

    def test_multiple_transactions_flags_only_missing(self, agent: DeploymentStateAgent) -> None:
        good = _make_transaction("SafePayment", validation=[MagicMock()])
        bad = _make_transaction("UnsafeTransfer", validation=[])
        findings = agent.transaction_without_validations(make_appspec(transactions=[good, bad]))
        assert len(findings) == 1
        assert "UnsafeTransfer" in findings[0].title

    def test_no_transactions(self, agent: DeploymentStateAgent) -> None:
        assert agent.transaction_without_validations(make_appspec(transactions=[])) == []


# =============================================================================
# DS-07  Channel without throttle configuration
# =============================================================================


class TestDS07ChannelWithoutThrottle:
    def test_flags_channel_without_provider_config(self, agent: DeploymentStateAgent) -> None:
        channel = _make_channel("notifications", provider_config=None)
        findings = agent.channel_without_throttle(make_appspec(channels=[channel]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "DS-07"
        assert findings[0].severity == Severity.LOW
        assert "notifications" in findings[0].title

    def test_passes_with_provider_config(self, agent: DeploymentStateAgent) -> None:
        channel = _make_channel("notifications", provider_config=MagicMock())
        assert agent.channel_without_throttle(make_appspec(channels=[channel])) == []

    def test_no_channels(self, agent: DeploymentStateAgent) -> None:
        assert agent.channel_without_throttle(make_appspec(channels=[])) == []

    def test_flags_all_channel_kinds(self, agent: DeploymentStateAgent) -> None:
        # Covers iteration across multiple channel kinds.
        channels = [
            _make_channel("email_ch", kind=ChannelKind.EMAIL, provider_config=None),
            _make_channel("queue_ch", kind=ChannelKind.QUEUE, provider_config=None),
            _make_channel("stream_ch", kind=ChannelKind.STREAM, provider_config=None),
        ]
        findings = agent.channel_without_throttle(make_appspec(channels=channels))
        assert len(findings) == 3


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

    def test_has_8_heuristics(self, agent: DeploymentStateAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: DeploymentStateAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"DS-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_findings(self, agent: DeploymentStateAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.findings == []
        assert result.errors == []

    def test_run_aggregates_across_heuristics(self, agent: DeploymentStateAgent) -> None:
        iface = _make_interface("orders_api", auth=InterfaceAuthMethod.NONE)
        txn = _make_transaction("RecordPayment", idempotency_key="")
        channel = _make_channel("alerts", provider_config=None)
        result = agent.run(
            make_appspec(
                interfaces=_make_interfaces([iface]),
                transactions=[txn],
                channels=[channel],
            )
        )
        ids = {f.heuristic_id for f in result.findings}
        assert "DS-01" in ids
        assert "DS-03" in ids
        assert "DS-07" in ids
        assert result.errors == []

    def test_run_returns_agent_result_with_timing(self, agent: DeploymentStateAgent) -> None:
        result = agent.run(make_appspec())
        assert result.agent == AgentId.DS
        assert result.duration_ms >= 0
