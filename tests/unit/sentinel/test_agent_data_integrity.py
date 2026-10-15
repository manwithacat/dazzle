"""Tests for the Data Integrity detection agent (DI-01 through DI-07).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity, heuristic order and the
clean-spec run live in ``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir import FieldTypeKind
from dazzle.core.ir.domain import Constraint, ConstraintKind, EntitySpec
from dazzle.core.ir.fields import RelationshipBehavior
from dazzle.core.ir.governance import DataClassification
from dazzle.sentinel.agents.data_integrity import DataIntegrityAgent
from dazzle.sentinel.models import Severity

from .conftest import (
    assert_findings,
    make_appspec,
    make_entity,
    make_field,
    mock_entity,
    pk_field,
    ref_field,
    str_field,
)

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _one(*fields: Any, name: str = "Order") -> Any:
    return make_appspec([make_entity(name, [pk_field(), *fields])])


def _relationship(kind: FieldTypeKind, behavior: RelationshipBehavior | None = None) -> Any:
    return _one(make_field("rel", kind, ref_entity="Other", relationship_behavior=behavior))


def _machine(name: str, states: list[str], transitions: list[tuple[str, str]]) -> Any:
    sm = MagicMock()
    sm.states = states
    sm.transitions = []
    for from_s, to_s in transitions:
        t = MagicMock()
        t.from_state = from_s
        t.to_state = to_s
        sm.transitions.append(t)
    return make_appspec([mock_entity(name, state_machine=sm)])


def _computed(*deps: str) -> Any:
    cf = MagicMock()
    cf.name = "total"
    cf.dependencies = list(deps)
    cf.expression = f"compute({', '.join(deps)})"
    return make_appspec([mock_entity("Order", computed_fields=[cf])])


def _pii_email(audit: object | None = None) -> Any:
    cls_spec = MagicMock()
    cls_spec.entity = "Customer"
    cls_spec.field = "email"
    cls_spec.classification = DataClassification.PII_DIRECT
    policies = MagicMock()
    policies.classifications = [cls_spec]
    entity = mock_entity("Customer", [pk_field(), str_field("email")], audit=audit)
    return make_appspec([entity], policies=policies)


def _audit_enabled() -> MagicMock:
    audit = MagicMock()
    audit.enabled = True
    return audit


def _di(n: int, **extra: Any) -> list[dict[str, Any]]:
    return [{"heuristic_id": f"DI-0{n}", **extra}]


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # DI-01  relationship with no delete behaviour
    *[
        pytest.param(
            "check_cascade_delete_missing",
            lambda kind=kind: _relationship(kind),
            _di(1, severity=Severity.HIGH),
            id=f"DI-01-flags-{kind.value}-without-behavior",
        )
        for kind in (FieldTypeKind.HAS_MANY, FieldTypeKind.HAS_ONE)
    ],
    pytest.param(
        "check_cascade_delete_missing",
        lambda: _relationship(FieldTypeKind.HAS_MANY, RelationshipBehavior.CASCADE),
        [],
        id="DI-01-behavior-set",
    ),
    pytest.param(
        "check_cascade_delete_missing",
        lambda: _one(str_field("title")),
        [],
        id="DI-01-ignores-non-relationship",
    ),
    # DI-02  ref to an entity that does not exist
    pytest.param(
        "check_orphaned_ref",
        lambda: _one(ref_field("customer", "Customer")),
        _di(2, title_has="Customer"),
        id="DI-02-flags-ref-to-unknown-entity",
    ),
    pytest.param(
        "check_orphaned_ref",
        lambda: make_appspec(
            [
                make_entity("Customer", [pk_field()]),
                make_entity("Order", [pk_field(), ref_field("customer", "Customer")]),
            ]
        ),
        [],
        id="DI-02-target-exists",
    ),
    pytest.param(
        "check_orphaned_ref", lambda: _one(str_field("title")), [], id="DI-02-ignores-non-ref"
    ),
    # DI-03  entity without a primary key
    pytest.param(
        "check_missing_primary_key",
        lambda: make_appspec([make_entity("Task", [str_field("title", required=True)])]),
        _di(3, severity=Severity.CRITICAL),
        id="DI-03-flags-entity-without-pk",
    ),
    pytest.param(
        "check_missing_primary_key",
        lambda: _one(str_field("title")),
        [],
        id="DI-03-pk-present",
    ),
    # DI-04  unique-worthy field without UNIQUE
    *[
        pytest.param(
            "check_missing_unique_constraint",
            lambda name=name: _one(str_field(name), name="User"),
            _di(4, severity=Severity.MEDIUM),
            id=f"DI-04-flags-{name}",
        )
        for name in ("email", "slug", "username", "phone")
    ],
    pytest.param(
        "check_missing_unique_constraint",
        lambda: _one(str_field("email", unique=True), name="User"),
        [],
        id="DI-04-already-unique",
    ),
    pytest.param(
        "check_missing_unique_constraint",
        lambda: _one(str_field("description")),
        [],
        id="DI-04-ignores-ordinary-name",
    ),
    # #1356: `code` is the SECOND column of a composite unique and still covered.
    pytest.param(
        "check_missing_unique_constraint",
        lambda: make_appspec(
            [
                EntitySpec(
                    name="Product",
                    title="Product",
                    fields=[pk_field(), str_field("code")],
                    constraints=[Constraint(kind=ConstraintKind.UNIQUE, fields=["tenant", "code"])],
                )
            ]
        ),
        [],
        id="DI-04-composite-unique-any-position-1356",
    ),
    # #1356: a SessionInfo-style platform entity cannot be amended by project DSL.
    pytest.param(
        "check_missing_unique_constraint",
        lambda: make_appspec(
            [
                EntitySpec(
                    name="SessionInfo",
                    title="Session Info",
                    fields=[pk_field(), str_field("email")],
                    domain="platform",
                )
            ]
        ),
        [],
        id="DI-04-platform-injected-entity-skipped-1356",
    ),
    # DI-05  reachable state with no way out and a non-terminal name
    pytest.param(
        "check_dead_end_states",
        lambda: _machine(
            "Article",
            ["draft", "review", "awaiting_review", "published"],
            [("draft", "review"), ("review", "published"), ("review", "awaiting_review")],
        ),
        _di(5, title_has="awaiting_review"),
        id="DI-05-flags-transient-named-dead-end",
    ),
    # #1004: clearly terminal names (rejected, resolved, wont_fix, the last state
    # of a linear flow) are outcomes, not dead ends.
    pytest.param(
        "check_dead_end_states",
        lambda: _machine(
            "Article",
            ["draft", "review", "rejected", "published"],
            [("draft", "review"), ("review", "published"), ("review", "rejected")],
        ),
        [],
        id="DI-05-terminal-named-state-silent-1004",
    ),
    pytest.param(
        "check_dead_end_states",
        lambda: _machine(
            "FeedbackReport",
            ["new", "triaged", "in_progress", "resolved", "verified", "wont_fix", "duplicate"],
            [
                ("new", "triaged"),
                ("triaged", "in_progress"),
                ("in_progress", "resolved"),
                ("resolved", "verified"),
                ("triaged", "wont_fix"),
                ("triaged", "duplicate"),
            ],
        ),
        [],
        id="DI-05-multiple-terminal-outcomes-silent-1004",
    ),
    pytest.param(
        "check_dead_end_states",
        lambda: _machine("Article", ["draft", "published"], [("draft", "published")]),
        [],
        id="DI-05-last-state-terminal-silent-1004",
    ),
    pytest.param(
        "check_dead_end_states",
        lambda: make_appspec([mock_entity("Task", state_machine=None)]),
        [],
        id="DI-05-no-state-machine",
    ),
    # DI-06  computed field reaching across entities
    pytest.param(
        "check_cross_entity_computed",
        lambda: _computed("items.price"),
        _di(6, severity=Severity.INFO),
        id="DI-06-flags-cross-entity-dependency",
    ),
    pytest.param(
        "check_cross_entity_computed",
        lambda: _computed("price", "quantity"),
        [],
        id="DI-06-local-dependencies",
    ),
    pytest.param(
        "check_cross_entity_computed",
        lambda: make_appspec([mock_entity("Task", computed_fields=[])]),
        [],
        id="DI-06-no-computed-fields",
    ),
    # DI-07  PII/financial field on an entity without audit
    pytest.param(
        "check_sensitive_fields_without_audit",
        _pii_email,
        _di(7, severity=Severity.HIGH),
        id="DI-07-flags-pii-without-audit",
    ),
    pytest.param(
        "check_sensitive_fields_without_audit",
        lambda: _pii_email(audit=_audit_enabled()),
        [],
        id="DI-07-audit-enabled",
    ),
    pytest.param(
        "check_sensitive_fields_without_audit",
        lambda: make_appspec([mock_entity("Task")]),
        [],
        id="DI-07-no-policies",
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(DataIntegrityAgent(), heuristic)(build()), expected)
