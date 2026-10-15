"""Tests for the Integration & Dependency detection agent (ID-01 through ID-08).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.services import AuthKind, DomainServiceKind
from dazzle.sentinel.agents.integration_dependency import IntegrationDependencyAgent
from dazzle.sentinel.models import Severity

from .conftest import assert_findings, make_appspec

# ---------------------------------------------------------------------------
# Builders
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


def _id(n: int, severity: Severity, title_has: str | tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"heuristic_id": f"ID-0{n}", "severity": severity, "title_has": title_has}]


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # ID-01  external API without authentication
    pytest.param(
        "api_without_auth",
        lambda: make_appspec(apis=[_api("stripe", auth_kind=AuthKind.NONE)]),
        _id(1, Severity.HIGH, "stripe"),
        id="ID-01-flags-api-without-auth",
    ),
    *[
        pytest.param(
            "api_without_auth",
            lambda k=kind: make_appspec(apis=[_api("stripe", auth_kind=k)]),
            [],
            id=f"ID-01-{kind.value}-satisfies",
        )
        for kind in (AuthKind.API_KEY_HEADER, AuthKind.OAUTH2_PKCE)
    ],
    pytest.param("api_without_auth", make_appspec, [], id="ID-01-no-apis"),
    # ID-02  integration naming an API that is not declared
    pytest.param(
        "integration_unknown_api",
        lambda: make_appspec(integrations=[_integration("stripe_sync", api_refs=["stripe"])]),
        _id(2, Severity.HIGH, "stripe"),
        id="ID-02-flags-unknown-api",
    ),
    pytest.param(
        "integration_unknown_api",
        lambda: make_appspec(
            apis=[_api("stripe")],
            integrations=[_integration("multi_sync", api_refs=["stripe", "paypal"])],
        ),
        _id(2, Severity.HIGH, "paypal"),
        id="ID-02-flags-only-missing-ref",
    ),
    pytest.param(
        "integration_unknown_api",
        lambda: make_appspec(
            apis=[_api("stripe")], integrations=[_integration("stripe_sync", api_refs=["stripe"])]
        ),
        [],
        id="ID-02-api-exists",
    ),
    pytest.param("integration_unknown_api", make_appspec, [], id="ID-02-no-integrations"),
    pytest.param(
        "integration_unknown_api",
        lambda: make_appspec(integrations=[_integration("empty_sync")]),
        [],
        id="ID-02-empty-refs",
    ),
    # ID-03  integration naming a foreign model that is not declared
    pytest.param(
        "integration_unknown_foreign_model",
        lambda: make_appspec(
            integrations=[_integration("stripe_sync", foreign_model_refs=["StripeCustomer"])]
        ),
        _id(3, Severity.HIGH, "StripeCustomer"),
        id="ID-03-flags-unknown-foreign-model",
    ),
    pytest.param(
        "integration_unknown_foreign_model",
        lambda: make_appspec(
            foreign_models=[_foreign_model("StripeCustomer", key_fields=["stripe_id"])],
            integrations=[
                _integration("multi_sync", foreign_model_refs=["StripeCustomer", "PaypalAccount"])
            ],
        ),
        _id(3, Severity.HIGH, "PaypalAccount"),
        id="ID-03-flags-only-missing-ref",
    ),
    pytest.param(
        "integration_unknown_foreign_model",
        lambda: make_appspec(
            foreign_models=[_foreign_model("StripeCustomer", key_fields=["stripe_id"])],
            integrations=[_integration("stripe_sync", foreign_model_refs=["StripeCustomer"])],
        ),
        [],
        id="ID-03-foreign-model-exists",
    ),
    pytest.param("integration_unknown_foreign_model", make_appspec, [], id="ID-03-no-integrations"),
    pytest.param(
        "integration_unknown_foreign_model",
        lambda: make_appspec(integrations=[_integration("empty_sync")]),
        [],
        id="ID-03-empty-refs",
    ),
    # ID-06  foreign model without key fields
    pytest.param(
        "foreign_model_no_keys",
        lambda: make_appspec(foreign_models=[_foreign_model("StripeCustomer")]),
        _id(6, Severity.MEDIUM, "StripeCustomer"),
        id="ID-06-flags-foreign-model-without-keys",
    ),
    pytest.param(
        "foreign_model_no_keys",
        lambda: make_appspec(
            foreign_models=[_foreign_model("StripeCustomer", key_fields=["stripe_id"])]
        ),
        [],
        id="ID-06-key-fields-present",
    ),
    pytest.param("foreign_model_no_keys", make_appspec, [], id="ID-06-no-foreign-models"),
    # ID-07  sync without match rules (title names sync and integration)
    pytest.param(
        "sync_without_match_rules",
        lambda: make_appspec(
            integrations=[_integration("stripe_sync", syncs=[_sync("sync_customers")])]
        ),
        _id(7, Severity.MEDIUM, ("sync_customers", "stripe_sync")),
        id="ID-07-flags-sync-without-match-rules",
    ),
    pytest.param(
        "sync_without_match_rules",
        lambda: make_appspec(
            integrations=[
                _integration(
                    "stripe_sync", syncs=[_sync("sync_customers", match_rules=[MagicMock()])]
                )
            ]
        ),
        [],
        id="ID-07-match-rules-present",
    ),
    pytest.param(
        "sync_without_match_rules",
        lambda: make_appspec(integrations=[_integration("stripe_sync")]),
        [],
        id="ID-07-no-syncs",
    ),
    pytest.param("sync_without_match_rules", make_appspec, [], id="ID-07-no-integrations"),
    # ID-08  integration-kind domain service without guarantees
    pytest.param(
        "integration_service_no_guarantees",
        lambda: make_appspec(domain_services=[_domain_service("sync_data")]),
        _id(8, Severity.LOW, "sync_data"),
        id="ID-08-flags-integration-service-without-guarantees",
    ),
    pytest.param(
        "integration_service_no_guarantees",
        lambda: make_appspec(
            domain_services=[
                _domain_service("sync_data", guarantees=["Idempotent", "Timeout: 30s"])
            ]
        ),
        [],
        id="ID-08-guarantees-present",
    ),
    *[
        pytest.param(
            "integration_service_no_guarantees",
            lambda k=kind: make_appspec(domain_services=[_domain_service("svc", kind=k)]),
            [],
            id=f"ID-08-ignores-{kind.value}-kind",
        )
        for kind in (DomainServiceKind.VALIDATION, DomainServiceKind.DOMAIN_LOGIC)
    ],
    pytest.param(
        "integration_service_no_guarantees", make_appspec, [], id="ID-08-no-domain-services"
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(IntegrationDependencyAgent(), heuristic)(build()), expected)


def test_run_collects_findings_from_every_heuristic() -> None:
    # Two unauthenticated APIs and one keyless foreign model: run() iterates
    # every offender of every heuristic, in heuristic order.
    apis = [_api("stripe", auth_kind=AuthKind.NONE), _api("github", auth_kind=AuthKind.NONE)]
    fm = _foreign_model("StripeCustomer", key_fields=[])
    result = IntegrationDependencyAgent().run(make_appspec(apis=apis, foreign_models=[fm]))
    assert result.errors == []
    assert [f.heuristic_id for f in result.findings] == ["ID-01", "ID-01", "ID-06"]
