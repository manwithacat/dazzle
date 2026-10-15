"""Tests for the Auth & Authorization detection agent (AA-01 through AA-07).

One table: each case builds an AppSpec, runs one heuristic and pins the exact
findings (see ``assert_findings``). Agent identity and heuristic order live in
``test_registry.py``.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    GrantCheck,
    LogicalOperator,
    RoleCheck,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule, PolicyEffect
from dazzle.core.ir.security import SecurityProfile
from dazzle.sentinel.agents.auth_authorization import AuthAuthorizationAgent
from dazzle.sentinel.models import Confidence, Severity

from .conftest import assert_findings, make_appspec, make_entity

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _access(permissions: list[PermissionRule] | None = None) -> AccessSpec:
    return AccessSpec(permissions=permissions or [])


def _permission(
    op: PermissionKind,
    effect: PolicyEffect = PolicyEffect.PERMIT,
    personas: list[str] | None = None,
) -> PermissionRule:
    return PermissionRule(operation=op, effect=effect, personas=personas or [])


def _surface(name: str, entity_ref: str | None = None, access: object | None = None) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.title = name
    s.entity_ref = entity_ref
    s.access = access
    return s


def _surface_access(
    require_auth: bool = False, allow_personas: list[str] | None = None
) -> MagicMock:
    a = MagicMock()
    a.require_auth = require_auth
    a.allow_personas = allow_personas or []
    a.deny_personas = []
    return a


def _persona(pid: str) -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.label = pid
    return p


def _story(story_id: str, actor: str) -> MagicMock:
    s = MagicMock()
    s.story_id = story_id
    s.persona = actor
    return s


def _pii_policies(entity: str = "Customer") -> MagicMock:
    cls_spec = MagicMock()
    cls_spec.entity = entity
    cls_spec.classification = MagicMock()
    cls_spec.classification.value = "pii_direct"
    policies = MagicMock()
    policies.classifications = [cls_spec]
    return policies


def _security(profile: SecurityProfile) -> MagicMock:
    sec = MagicMock()
    sec.profile = profile
    return sec


def _classified(perm: PermissionRule) -> Any:
    """A pii_direct-classified Customer whose only permission is ``perm``."""
    entity = make_entity("Customer", access=_access(permissions=[perm]))
    return make_appspec([entity], policies=_pii_policies())


def _surface_on_task(
    entity_personas: list[str], surface_personas: list[str] | None = None, **surface_kw: Any
) -> Any:
    perm = _permission(PermissionKind.READ, personas=entity_personas)
    entity = make_entity("Task", access=_access(permissions=[perm]))
    access = (
        _surface_access(allow_personas=surface_personas) if surface_personas is not None else None
    )
    surface = _surface("task_list", entity_ref="Task", access=access, **surface_kw)
    return make_appspec([entity], surfaces=[surface])


def _delete_rules(permissions: list[PermissionRule]) -> Any:
    entity = (
        make_entity("Task", access=_access(permissions)) if permissions else make_entity("Task")
    )
    return make_appspec([entity])


_ROLE_OR = ConditionExpr(
    left=ConditionExpr(role_check=RoleCheck(role_name="clinician")),
    operator=LogicalOperator.OR,
    right=ConditionExpr(role_check=RoleCheck(role_name="admin")),
)
_GRANT = ConditionExpr(grant_check=GrantCheck(relation="viewer", scope_field="dept"))
_FIELD_ONLY = ConditionExpr(
    comparison=Comparison(
        field="status", operator=ComparisonOperator.EQUALS, value=ConditionValue(literal="draft")
    )
)


def _aa(n: int, **extra: Any) -> list[dict[str, Any]]:
    return [{"heuristic_id": f"AA-0{n}", **extra}]


# ---------------------------------------------------------------------------
# Heuristic table
# ---------------------------------------------------------------------------

CASES = [
    # AA-01  surface without access control
    pytest.param(
        "surface_without_access_control",
        lambda: make_appspec([make_entity("Task")], surfaces=[_surface("t", entity_ref="Task")]),
        _aa(1, severity=Severity.HIGH),
        id="AA-01-flags-surface-and-entity-without-access",
    ),
    pytest.param(
        "surface_without_access_control",
        lambda: make_appspec(
            [make_entity("Task")],
            surfaces=[_surface("t", "Task", access=_surface_access(require_auth=True))],
        ),
        [],
        id="AA-01-surface-access-satisfies",
    ),
    pytest.param(
        "surface_without_access_control",
        lambda: make_appspec(
            [make_entity("Task", access=_access())], surfaces=[_surface("t", entity_ref="Task")]
        ),
        [],
        id="AA-01-entity-access-satisfies",
    ),
    pytest.param(
        "surface_without_access_control",
        lambda: make_appspec(surfaces=[_surface("dashboard")]),
        [],
        id="AA-01-skips-surface-without-entity",
    ),
    # AA-02  entity with no access spec
    pytest.param(
        "entity_no_access_spec",
        lambda: make_appspec([make_entity("Task")]),
        _aa(2),
        id="AA-02-flags-entity-without-access",
    ),
    pytest.param(
        "entity_no_access_spec",
        lambda: make_appspec([make_entity("Task", access=_access())]),
        [],
        id="AA-02-access-satisfies",
    ),
    # AA-03  persona no story acts as
    pytest.param(
        "unused_persona",
        lambda: make_appspec(personas=[_persona("reviewer")], stories=[_story("ST-001", "admin")]),
        _aa(3, title_has="reviewer"),
        id="AA-03-flags-persona-without-story",
    ),
    pytest.param(
        "unused_persona",
        lambda: make_appspec(personas=[_persona("admin")], stories=[_story("ST-001", "admin")]),
        [],
        id="AA-03-persona-used-by-story",
    ),
    pytest.param("unused_persona", make_appspec, [], id="AA-03-no-personas"),
    # AA-04  empty-persona permit on classified data
    pytest.param(
        "empty_personas_classified_data",
        lambda: _classified(PermissionRule(operation=PermissionKind.READ)),
        _aa(4, confidence=Confidence.CONFIRMED),
        id="AA-04-bare-empty-permit-confirmed",
    ),
    pytest.param("empty_personas_classified_data", make_appspec, [], id="AA-04-no-policies"),
    # #1354: condition-based permits are role gates, not wide-open rules.
    pytest.param(
        "empty_personas_classified_data",
        lambda: _classified(PermissionRule(operation=PermissionKind.READ, condition=_ROLE_OR)),
        [],
        id="AA-04-role-or-tree-not-flagged-1354",
    ),
    pytest.param(
        "empty_personas_classified_data",
        lambda: _classified(PermissionRule(operation=PermissionKind.READ, condition=_GRANT)),
        [],
        id="AA-04-grant-check-not-flagged-1354",
    ),
    pytest.param(
        "empty_personas_classified_data",
        lambda: _classified(PermissionRule(operation=PermissionKind.DELETE, deny_all=True)),
        [],
        id="AA-04-deny-all-not-flagged-1354",
    ),
    # A row filter with no principal check is still a finding, but the "any
    # authenticated user" CONFIRMED claim is wrong: LIKELY and reworded.
    pytest.param(
        "empty_personas_classified_data",
        lambda: _classified(PermissionRule(operation=PermissionKind.READ, condition=_FIELD_ONLY)),
        _aa(4, confidence=Confidence.LIKELY, description_has="WHICH ROWS"),
        id="AA-04-field-only-condition-downgraded-1354",
    ),
    # AA-05  non-admin DELETE without a FORBID
    pytest.param(
        "non_admin_delete_without_forbid",
        lambda: _delete_rules([_permission(PermissionKind.DELETE, personas=["editor", "admin"])]),
        _aa(5),
        id="AA-05-flags-non-admin-delete",
    ),
    pytest.param(
        "non_admin_delete_without_forbid",
        lambda: _delete_rules(
            [
                _permission(PermissionKind.DELETE, personas=["editor"]),
                _permission(PermissionKind.DELETE, PolicyEffect.FORBID),
            ]
        ),
        [],
        id="AA-05-forbid-present",
    ),
    pytest.param(
        "non_admin_delete_without_forbid",
        lambda: _delete_rules([_permission(PermissionKind.DELETE, personas=["admin"])]),
        [],
        id="AA-05-admin-only",
    ),
    pytest.param(
        "non_admin_delete_without_forbid",
        lambda: _delete_rules([]),
        [],
        id="AA-05-no-access",
    ),
    # AA-06  basic security profile over sensitive data
    pytest.param(
        "weak_security_sensitive_data",
        lambda: make_appspec(security=_security(SecurityProfile.BASIC), policies=_pii_policies()),
        _aa(6, severity=Severity.HIGH),
        id="AA-06-flags-basic-profile-with-pii",
    ),
    pytest.param("weak_security_sensitive_data", make_appspec, [], id="AA-06-no-security"),
    pytest.param(
        "weak_security_sensitive_data",
        lambda: make_appspec(security=_security(SecurityProfile.STRICT), policies=_pii_policies()),
        [],
        id="AA-06-strict-profile",
    ),
    # AA-07  surface admits personas the entity does not
    pytest.param(
        "surface_entity_persona_mismatch",
        lambda: _surface_on_task(["admin"], ["admin", "viewer"]),
        _aa(7, description_has="viewer"),
        id="AA-07-flags-surface-only-persona",
    ),
    pytest.param(
        "surface_entity_persona_mismatch",
        lambda: _surface_on_task(["admin"], ["admin"]),
        [],
        id="AA-07-matching-personas",
    ),
    pytest.param(
        "surface_entity_persona_mismatch",
        lambda: _surface_on_task([], ["admin"]),
        [],
        id="AA-07-entity-without-persona-restrictions",
    ),
]


@pytest.mark.parametrize(("heuristic", "build", "expected"), CASES)
def test_heuristic(
    heuristic: str, build: Callable[[], Any], expected: list[dict[str, Any]]
) -> None:
    assert_findings(getattr(AuthAuthorizationAgent(), heuristic)(build()), expected)
