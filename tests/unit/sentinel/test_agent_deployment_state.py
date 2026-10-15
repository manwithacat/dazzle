"""Tests for the Deployment & State detection agent (DS-05 and DS-08).

One table: each case builds the governance policies, runs one heuristic and
pins the exact findings (see ``assert_findings``). Agent identity, heuristic
order and the clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.governance import DataClassification as DC
from dazzle.sentinel.agents.deployment_state import DeploymentStateAgent
from dazzle.sentinel.models import Severity

from .conftest import assert_findings, make_appspec

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _policies(
    *classified: tuple[str, str, DC],
    erasures: tuple[str, ...] = (),
    audit_access: bool = True,
) -> Any:
    """An AppSpec whose policies classify ``(entity, field, classification)`` triples."""
    policies = MagicMock()
    policies.classifications = []
    for entity, field, classification in classified:
        cls_spec = MagicMock()
        cls_spec.entity = entity
        cls_spec.field = field
        cls_spec.classification = classification
        policies.classifications.append(cls_spec)
    policies.erasures = []
    for entity in erasures:
        erasure = MagicMock()
        erasure.entity = entity
        policies.erasures.append(erasure)
    policies.audit_access = audit_access
    return make_appspec(policies=policies)


def _ds05(entity: str) -> list[dict[str, Any]]:
    return [{"heuristic_id": "DS-05", "severity": Severity.HIGH, "title_has": entity}]


_DS08 = {"heuristic_id": "DS-08", "severity": Severity.HIGH, "title_has": "Audit access disabled"}


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # DS-05  PII classification with no erasure policy
    *[
        pytest.param(
            "pii_without_erasure",
            lambda e=entity, f=field, c=cls: _policies((e, f, c)),
            _ds05(entity),
            id=f"DS-05-flags-{cls.value}",
        )
        for entity, field, cls in (
            ("Customer", "email", DC.PII_DIRECT),
            ("User", "ip_addr", DC.PII_INDIRECT),
            ("Patient", "diagnosis", DC.PII_SENSITIVE),
        )
    ],
    pytest.param(
        "pii_without_erasure",
        lambda: _policies(("Customer", "email", DC.PII_DIRECT), erasures=("Customer",)),
        [],
        id="DS-05-erasure-exists",
    ),
    pytest.param("pii_without_erasure", make_appspec, [], id="DS-05-no-policies"),
    pytest.param(
        "pii_without_erasure",
        lambda: _policies(("Order", "amount", DC.FINANCIAL_TXN)),
        [],
        id="DS-05-non-pii-classification",
    ),
    pytest.param("pii_without_erasure", _policies, [], id="DS-05-empty-classifications"),
    # One finding per entity, naming every PII field on it.
    pytest.param(
        "pii_without_erasure",
        lambda: _policies(
            ("Customer", "email", DC.PII_DIRECT), ("Customer", "phone", DC.PII_DIRECT)
        ),
        [{**_ds05("Customer")[0], "description_has": ("email", "phone")}],
        id="DS-05-one-finding-per-entity-names-every-field",
    ),
    pytest.param(
        "pii_without_erasure",
        lambda: _policies(
            ("Customer", "email", DC.PII_DIRECT),
            ("Employee", "ssn", DC.PII_SENSITIVE),
            erasures=("Customer",),
        ),
        _ds05("Employee"),
        id="DS-05-flags-only-entity-without-erasure",
    ),
    # DS-08  audit_access disabled while sensitive data is classified
    *[
        pytest.param(
            "audit_access_disabled_sensitive",
            lambda e=entity, f=field, c=cls: _policies((e, f, c), audit_access=False),
            [_DS08],
            id=f"DS-08-flags-{cls.value}",
        )
        for entity, field, cls in (
            ("Customer", "email", DC.PII_DIRECT),
            ("Payment", "amount", DC.FINANCIAL_TXN),
            ("Account", "card_number", DC.FINANCIAL_ACCOUNT),
        )
    ],
    pytest.param(
        "audit_access_disabled_sensitive",
        lambda: _policies(("Customer", "email", DC.PII_DIRECT), audit_access=True),
        [],
        id="DS-08-audit-enabled",
    ),
    pytest.param("audit_access_disabled_sensitive", make_appspec, [], id="DS-08-no-policies"),
    pytest.param(
        "audit_access_disabled_sensitive",
        lambda: _policies(audit_access=False),
        [],
        id="DS-08-no-sensitive-data",
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(DeploymentStateAgent(), heuristic)(build()), expected)


def test_ds08_aggregates_sensitive_entities_sorted() -> None:
    (finding,) = DeploymentStateAgent().audit_access_disabled_sensitive(
        _policies(
            ("Zebra", "ssn", DC.PII_SENSITIVE),
            ("Alpha", "card", DC.FINANCIAL_ACCOUNT),
            audit_access=False,
        )
    )
    assert 0 <= finding.description.index("Alpha") < finding.description.index("Zebra")
