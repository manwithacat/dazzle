"""Tests for the Integration & Dependency detection agent (ID-01 through ID-08)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.services import AuthKind, DomainServiceKind
from dazzle.sentinel.agents.integration_dependency import IntegrationDependencyAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, make_entity, pk_field, str_field


@pytest.fixture
def agent() -> IntegrationDependencyAgent:
    return IntegrationDependencyAgent()


# ---------------------------------------------------------------------------
# Helpers for building mock IR objects
# ---------------------------------------------------------------------------


def _api(name: str, *, auth_kind: AuthKind = AuthKind.API_KEY_HEADER) -> MagicMock:
    api = MagicMock()
    api.name = name
    api.title = name.title()
    api.auth_profile = MagicMock()
    api.auth_profile.kind = auth_kind
    return api


def _integration(
    name: str,
    *,
    api_refs: list[str] | None = None,
    foreign_model_refs: list[str] | None = None,
    syncs: list[MagicMock] | None = None,
) -> MagicMock:
    integration = MagicMock()
    integration.name = name
    integration.api_refs = api_refs or []
    integration.foreign_model_refs = foreign_model_refs or []
    integration.syncs = syncs or []
    return integration


def _sync(name: str, *, match_rules: list | None = None) -> MagicMock:
    sync = MagicMock()
    sync.name = name
    sync.match_rules = match_rules or []
    return sync


def _webhook(
    name: str,
    *,
    url: str = "https://example.com/hook",
    retry: object | None = None,
) -> MagicMock:
    webhook = MagicMock()
    webhook.name = name
    webhook.title = name.replace("_", " ").title()
    webhook.url = url
    webhook.auth = None
    webhook.retry = retry
    webhook.entity = "Order"
    return webhook


def _foreign_model(name: str, *, key_fields: list[str] | None = None) -> MagicMock:
    fm = MagicMock()
    fm.name = name
    fm.key_fields = key_fields or []
    return fm


def _domain_service(
    name: str,
    *,
    kind: DomainServiceKind = DomainServiceKind.INTEGRATION,
    guarantees: list[str] | None = None,
) -> MagicMock:
    svc = MagicMock()
    svc.name = name
    svc.title = name.replace("_", " ").title()
    svc.kind = kind
    svc.guarantees = guarantees or []
    return svc


# =============================================================================
# ID-01  External API without authentication
# =============================================================================


class TestID01ApiWithoutAuth:
    def test_flags_api_with_no_auth(self, agent: IntegrationDependencyAgent) -> None:
        api = _api("stripe", auth_kind=AuthKind.NONE)
        findings = agent.api_without_auth(make_appspec(apis=[api]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-01"
        assert findings[0].severity == Severity.HIGH
        assert "stripe" in findings[0].title

    def test_passes_with_api_key_auth(self, agent: IntegrationDependencyAgent) -> None:
        api = _api("stripe", auth_kind=AuthKind.API_KEY_HEADER)
        findings = agent.api_without_auth(make_appspec(apis=[api]))
        assert findings == []

    def test_passes_with_oauth2(self, agent: IntegrationDependencyAgent) -> None:
        api = _api("github", auth_kind=AuthKind.OAUTH2_PKCE)
        findings = agent.api_without_auth(make_appspec(apis=[api]))
        assert findings == []

    def test_flags_multiple_unauthenticated_apis(self, agent: IntegrationDependencyAgent) -> None:
        apis = [
            _api("stripe", auth_kind=AuthKind.NONE),
            _api("github", auth_kind=AuthKind.NONE),
        ]
        findings = agent.api_without_auth(make_appspec(apis=apis))
        assert len(findings) == 2

    def test_no_apis(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.api_without_auth(make_appspec())
        assert findings == []


# =============================================================================
# ID-02  Integration referencing unknown API
# =============================================================================


class TestID02IntegrationUnknownApi:
    def test_flags_unknown_api_ref(self, agent: IntegrationDependencyAgent) -> None:
        integration = _integration("stripe_sync", api_refs=["stripe"])
        findings = agent.integration_unknown_api(make_appspec(integrations=[integration]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-02"
        assert findings[0].severity == Severity.HIGH
        assert "stripe" in findings[0].title

    def test_passes_when_api_exists(self, agent: IntegrationDependencyAgent) -> None:
        api = _api("stripe")
        integration = _integration("stripe_sync", api_refs=["stripe"])
        findings = agent.integration_unknown_api(
            make_appspec(apis=[api], integrations=[integration])
        )
        assert findings == []

    def test_flags_only_missing_refs(self, agent: IntegrationDependencyAgent) -> None:
        api = _api("stripe")
        integration = _integration("multi_sync", api_refs=["stripe", "paypal"])
        findings = agent.integration_unknown_api(
            make_appspec(apis=[api], integrations=[integration])
        )
        assert len(findings) == 1
        assert "paypal" in findings[0].title

    def test_no_integrations(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.integration_unknown_api(make_appspec())
        assert findings == []

    def test_empty_api_refs(self, agent: IntegrationDependencyAgent) -> None:
        integration = _integration("empty_sync", api_refs=[])
        findings = agent.integration_unknown_api(make_appspec(integrations=[integration]))
        assert findings == []


# =============================================================================
# ID-03  Integration referencing unknown foreign model
# =============================================================================


class TestID03IntegrationUnknownForeignModel:
    def test_flags_unknown_foreign_model_ref(self, agent: IntegrationDependencyAgent) -> None:
        integration = _integration("stripe_sync", foreign_model_refs=["StripeCustomer"])
        findings = agent.integration_unknown_foreign_model(make_appspec(integrations=[integration]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-03"
        assert findings[0].severity == Severity.HIGH
        assert "StripeCustomer" in findings[0].title

    def test_passes_when_foreign_model_exists(self, agent: IntegrationDependencyAgent) -> None:
        fm = _foreign_model("StripeCustomer", key_fields=["stripe_id"])
        integration = _integration("stripe_sync", foreign_model_refs=["StripeCustomer"])
        findings = agent.integration_unknown_foreign_model(
            make_appspec(foreign_models=[fm], integrations=[integration])
        )
        assert findings == []

    def test_flags_only_missing_refs(self, agent: IntegrationDependencyAgent) -> None:
        fm = _foreign_model("StripeCustomer", key_fields=["stripe_id"])
        integration = _integration(
            "multi_sync",
            foreign_model_refs=["StripeCustomer", "PaypalAccount"],
        )
        findings = agent.integration_unknown_foreign_model(
            make_appspec(foreign_models=[fm], integrations=[integration])
        )
        assert len(findings) == 1
        assert "PaypalAccount" in findings[0].title

    def test_no_integrations(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.integration_unknown_foreign_model(make_appspec())
        assert findings == []

    def test_empty_foreign_model_refs(self, agent: IntegrationDependencyAgent) -> None:
        integration = _integration("empty_sync", foreign_model_refs=[])
        findings = agent.integration_unknown_foreign_model(make_appspec(integrations=[integration]))
        assert findings == []


# =============================================================================
# ID-04  Webhook without retry configuration
# =============================================================================


class TestID04WebhookWithoutRetry:
    def test_flags_webhook_without_retry(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", retry=None)
        findings = agent.webhook_without_retry(make_appspec(webhooks=[webhook]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-04"
        assert findings[0].severity == Severity.MEDIUM
        assert "order_notify" in findings[0].title

    def test_passes_with_retry_configured(self, agent: IntegrationDependencyAgent) -> None:
        retry = MagicMock()
        retry.max_attempts = 3
        webhook = _webhook("order_notify", retry=retry)
        findings = agent.webhook_without_retry(make_appspec(webhooks=[webhook]))
        assert findings == []

    def test_flags_multiple_webhooks_without_retry(self, agent: IntegrationDependencyAgent) -> None:
        webhooks = [
            _webhook("hook_a", retry=None),
            _webhook("hook_b", retry=None),
        ]
        findings = agent.webhook_without_retry(make_appspec(webhooks=webhooks))
        assert len(findings) == 2

    def test_no_webhooks(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.webhook_without_retry(make_appspec())
        assert findings == []


# =============================================================================
# ID-05  Hard-coded webhook URL
# =============================================================================


class TestID05HardcodedWebhookUrl:
    def test_flags_literal_url(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", url="https://example.com/hook")
        findings = agent.hardcoded_webhook_url(make_appspec(webhooks=[webhook]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-05"
        assert findings[0].severity == Severity.LOW
        assert "order_notify" in findings[0].title

    def test_passes_with_config_reference(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", url='config("WEBHOOK_ORDER_NOTIFY_URL")')
        findings = agent.hardcoded_webhook_url(make_appspec(webhooks=[webhook]))
        assert findings == []

    def test_passes_with_config_no_quotes(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", url="config(WEBHOOK_URL)")
        findings = agent.hardcoded_webhook_url(make_appspec(webhooks=[webhook]))
        assert findings == []

    def test_skips_empty_url(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", url="")
        findings = agent.hardcoded_webhook_url(make_appspec(webhooks=[webhook]))
        assert findings == []

    def test_skips_none_url(self, agent: IntegrationDependencyAgent) -> None:
        webhook = _webhook("order_notify", url=None)
        findings = agent.hardcoded_webhook_url(make_appspec(webhooks=[webhook]))
        assert findings == []

    def test_no_webhooks(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.hardcoded_webhook_url(make_appspec())
        assert findings == []


# =============================================================================
# ID-06  Foreign model without key fields
# =============================================================================


class TestID06ForeignModelNoKeys:
    def test_flags_foreign_model_with_empty_keys(self, agent: IntegrationDependencyAgent) -> None:
        fm = _foreign_model("StripeCustomer", key_fields=[])
        findings = agent.foreign_model_no_keys(make_appspec(foreign_models=[fm]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-06"
        assert findings[0].severity == Severity.MEDIUM
        assert "StripeCustomer" in findings[0].title

    def test_passes_with_key_fields(self, agent: IntegrationDependencyAgent) -> None:
        fm = _foreign_model("StripeCustomer", key_fields=["stripe_id"])
        findings = agent.foreign_model_no_keys(make_appspec(foreign_models=[fm]))
        assert findings == []

    def test_flags_multiple_keyless_models(self, agent: IntegrationDependencyAgent) -> None:
        fms = [
            _foreign_model("StripeCustomer", key_fields=[]),
            _foreign_model("PaypalAccount", key_fields=[]),
        ]
        findings = agent.foreign_model_no_keys(make_appspec(foreign_models=fms))
        assert len(findings) == 2

    def test_no_foreign_models(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.foreign_model_no_keys(make_appspec())
        assert findings == []


# =============================================================================
# ID-07  Integration sync without match rules
# =============================================================================


class TestID07SyncWithoutMatchRules:
    def test_flags_sync_without_match_rules(self, agent: IntegrationDependencyAgent) -> None:
        sync = _sync("sync_customers", match_rules=[])
        integration = _integration("stripe_sync", syncs=[sync])
        findings = agent.sync_without_match_rules(make_appspec(integrations=[integration]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-07"
        assert findings[0].severity == Severity.MEDIUM
        assert "sync_customers" in findings[0].title
        assert "stripe_sync" in findings[0].title

    def test_passes_with_match_rules(self, agent: IntegrationDependencyAgent) -> None:
        rule = MagicMock()
        sync = _sync("sync_customers", match_rules=[rule])
        integration = _integration("stripe_sync", syncs=[sync])
        findings = agent.sync_without_match_rules(make_appspec(integrations=[integration]))
        assert findings == []

    def test_flags_multiple_syncs_without_rules(self, agent: IntegrationDependencyAgent) -> None:
        syncs = [
            _sync("sync_a", match_rules=[]),
            _sync("sync_b", match_rules=[]),
        ]
        integration = _integration("data_sync", syncs=syncs)
        findings = agent.sync_without_match_rules(make_appspec(integrations=[integration]))
        assert len(findings) == 2

    def test_no_syncs(self, agent: IntegrationDependencyAgent) -> None:
        integration = _integration("stripe_sync", syncs=[])
        findings = agent.sync_without_match_rules(make_appspec(integrations=[integration]))
        assert findings == []

    def test_no_integrations(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.sync_without_match_rules(make_appspec())
        assert findings == []


# =============================================================================
# ID-08  Integration service without guarantees
# =============================================================================


class TestID08IntegrationServiceNoGuarantees:
    def test_flags_integration_service_without_guarantees(
        self, agent: IntegrationDependencyAgent
    ) -> None:
        svc = _domain_service("sync_data", guarantees=[])
        findings = agent.integration_service_no_guarantees(make_appspec(domain_services=[svc]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "ID-08"
        assert findings[0].severity == Severity.LOW
        assert "sync_data" in findings[0].title

    def test_passes_with_guarantees(self, agent: IntegrationDependencyAgent) -> None:
        svc = _domain_service("sync_data", guarantees=["Idempotent", "Timeout: 30s"])
        findings = agent.integration_service_no_guarantees(make_appspec(domain_services=[svc]))
        assert findings == []

    def test_ignores_non_integration_kind(self, agent: IntegrationDependencyAgent) -> None:
        svc = _domain_service(
            "validate_order",
            kind=DomainServiceKind.VALIDATION,
            guarantees=[],
        )
        findings = agent.integration_service_no_guarantees(make_appspec(domain_services=[svc]))
        assert findings == []

    def test_ignores_domain_logic_kind(self, agent: IntegrationDependencyAgent) -> None:
        svc = _domain_service(
            "calc_total",
            kind=DomainServiceKind.DOMAIN_LOGIC,
            guarantees=[],
        )
        findings = agent.integration_service_no_guarantees(make_appspec(domain_services=[svc]))
        assert findings == []

    def test_flags_multiple_services(self, agent: IntegrationDependencyAgent) -> None:
        svcs = [
            _domain_service("sync_a", guarantees=[]),
            _domain_service("sync_b", guarantees=[]),
        ]
        findings = agent.integration_service_no_guarantees(make_appspec(domain_services=svcs))
        assert len(findings) == 2

    def test_no_domain_services(self, agent: IntegrationDependencyAgent) -> None:
        findings = agent.integration_service_no_guarantees(make_appspec())
        assert findings == []


# =============================================================================
# Full agent run
# =============================================================================


class TestIntegrationDependencyAgentRun:
    def test_agent_id(self, agent: IntegrationDependencyAgent) -> None:
        assert agent.agent_id == AgentId.ID

    def test_has_8_heuristics(self, agent: IntegrationDependencyAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: IntegrationDependencyAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"ID-0{i}" for i in range(1, 9)]

    def test_clean_appspec_no_findings(self, agent: IntegrationDependencyAgent) -> None:
        entity = make_entity("Task", [pk_field(), str_field("title", required=True)])
        result = agent.run(make_appspec([entity]))
        assert result.errors == []
        assert result.findings == []

    def test_run_collects_findings_from_multiple_heuristics(
        self, agent: IntegrationDependencyAgent
    ) -> None:
        api = _api("stripe", auth_kind=AuthKind.NONE)
        webhook = _webhook("order_notify", retry=None)
        fm = _foreign_model("StripeCustomer", key_fields=[])
        result = agent.run(make_appspec(apis=[api], webhooks=[webhook], foreign_models=[fm]))
        assert result.errors == []
        heuristic_ids = {f.heuristic_id for f in result.findings}
        assert "ID-01" in heuristic_ids
        assert "ID-04" in heuristic_ids
        assert "ID-06" in heuristic_ids
