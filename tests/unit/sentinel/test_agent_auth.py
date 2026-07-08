"""Tests for the Auth & Authorization detection agent (AA-01 through AA-08)."""

from unittest.mock import MagicMock

import pytest

from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule, PolicyEffect
from dazzle.sentinel.agents.auth_authorization import AuthAuthorizationAgent
from dazzle.sentinel.models import AgentId, Severity

from .conftest import make_appspec, make_entity


@pytest.fixture
def agent() -> AuthAuthorizationAgent:
    return AuthAuthorizationAgent()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _access(permissions: list[PermissionRule] | None = None) -> AccessSpec:
    return AccessSpec(permissions=permissions or [])


def _permission(
    op: PermissionKind,
    effect: PolicyEffect = PolicyEffect.PERMIT,
    personas: list[str] | None = None,
) -> PermissionRule:
    return PermissionRule(operation=op, effect=effect, personas=personas or [])


def _surface(
    name: str,
    entity_ref: str | None = None,
    access: object | None = None,
    title: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.name = name
    s.title = title or name
    s.entity_ref = entity_ref
    s.access = access
    return s


def _surface_access(
    require_auth: bool = False,
    allow_personas: list[str] | None = None,
) -> MagicMock:
    a = MagicMock()
    a.require_auth = require_auth
    a.allow_personas = allow_personas or []
    a.deny_personas = []
    return a


def _persona(pid: str, label: str = "") -> MagicMock:
    p = MagicMock()
    p.id = pid
    p.label = label or pid
    return p


def _story(story_id: str, actor: str) -> MagicMock:
    s = MagicMock()
    s.story_id = story_id
    s.persona = actor
    return s


def _webhook(name: str, *, auth: object | None = None, entity: str = "Task") -> MagicMock:
    w = MagicMock()
    w.name = name
    w.title = name
    w.entity = entity
    w.auth = auth
    return w


# =============================================================================
# AA-01  Surface without access control
# =============================================================================


class TestAA01SurfaceWithoutAccessControl:
    def test_flags_surface_with_no_access(self, agent: AuthAuthorizationAgent) -> None:
        entity = make_entity("Task")
        surface = _surface("task_list", entity_ref="Task")
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.surface_without_access_control(appspec)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_passes_when_surface_has_access(self, agent: AuthAuthorizationAgent) -> None:
        entity = make_entity("Task")
        surface = _surface(
            "task_list", entity_ref="Task", access=_surface_access(require_auth=True)
        )
        assert (
            agent.surface_without_access_control(make_appspec([entity], surfaces=[surface])) == []
        )

    def test_passes_when_entity_has_access(self, agent: AuthAuthorizationAgent) -> None:
        entity = make_entity("Task", access=_access())
        surface = _surface("task_list", entity_ref="Task")
        assert (
            agent.surface_without_access_control(make_appspec([entity], surfaces=[surface])) == []
        )

    def test_skips_surfaces_without_entity_ref(self, agent: AuthAuthorizationAgent) -> None:
        surface = _surface("dashboard")
        surface.entity_ref = None
        assert agent.surface_without_access_control(make_appspec(surfaces=[surface])) == []


# =============================================================================
# AA-02  Entity with no access spec
# =============================================================================


class TestAA02EntityNoAccessSpec:
    def test_flags_entity_without_access(self, agent: AuthAuthorizationAgent) -> None:
        entity = make_entity("Task")
        findings = agent.entity_no_access_spec(make_appspec([entity]))
        assert len(findings) == 1
        assert findings[0].heuristic_id == "AA-02"

    def test_passes_with_access(self, agent: AuthAuthorizationAgent) -> None:
        entity = make_entity("Task", access=_access())
        assert agent.entity_no_access_spec(make_appspec([entity])) == []


# =============================================================================
# AA-03  Unused persona
# =============================================================================


class TestAA03UnusedPersona:
    def test_flags_persona_not_in_stories(self, agent: AuthAuthorizationAgent) -> None:
        persona = _persona("reviewer")
        story = _story("ST-001", "admin")
        appspec = make_appspec(personas=[persona], stories=[story])
        findings = agent.unused_persona(appspec)
        assert len(findings) == 1
        assert "reviewer" in findings[0].title

    def test_passes_when_persona_used(self, agent: AuthAuthorizationAgent) -> None:
        persona = _persona("admin")
        story = _story("ST-001", "admin")
        assert agent.unused_persona(make_appspec(personas=[persona], stories=[story])) == []

    def test_empty_personas(self, agent: AuthAuthorizationAgent) -> None:
        assert agent.unused_persona(make_appspec()) == []


# =============================================================================
# AA-04  Empty personas on classified data
# =============================================================================


class TestAA04EmptyPersonasClassifiedData:
    def test_flags_empty_personas_on_classified_entity(self, agent: AuthAuthorizationAgent) -> None:
        perm = _permission(PermissionKind.READ)
        entity = make_entity("Customer", access=_access(permissions=[perm]))
        cls_spec = MagicMock()
        cls_spec.entity = "Customer"
        cls_spec.classification = MagicMock()
        cls_spec.classification.value = "pii_direct"
        policies = MagicMock()
        policies.classifications = [cls_spec]
        appspec = make_appspec([entity], policies=policies)
        findings = agent.empty_personas_classified_data(appspec)
        assert len(findings) == 1

    def test_passes_no_policies(self, agent: AuthAuthorizationAgent) -> None:
        assert agent.empty_personas_classified_data(make_appspec()) == []

    # -- #1354: condition-based permits are role gates, not wide-open rules --

    def _classified_appspec(self, perm: PermissionRule):
        entity = make_entity("Customer", access=_access(permissions=[perm]))
        cls_spec = MagicMock()
        cls_spec.entity = "Customer"
        cls_spec.classification = MagicMock()
        cls_spec.classification.value = "pii_direct"
        policies = MagicMock()
        policies.classifications = [cls_spec]
        return make_appspec([entity], policies=policies)

    def test_role_or_tree_condition_not_flagged(self, agent: AuthAuthorizationAgent) -> None:
        # `permit: read: role(clinician) or role(admin)` → personas=[] but the
        # role gate lives in the condition tree — the #1354 false positive.
        from dazzle.core.ir.conditions import ConditionExpr, LogicalOperator, RoleCheck

        cond = ConditionExpr(
            left=ConditionExpr(role_check=RoleCheck(role_name="clinician")),
            operator=LogicalOperator.OR,
            right=ConditionExpr(role_check=RoleCheck(role_name="admin")),
        )
        perm = PermissionRule(operation=PermissionKind.READ, condition=cond)
        assert agent.empty_personas_classified_data(self._classified_appspec(perm)) == []

    def test_grant_check_condition_not_flagged(self, agent: AuthAuthorizationAgent) -> None:
        from dazzle.core.ir.conditions import ConditionExpr, GrantCheck

        cond = ConditionExpr(grant_check=GrantCheck(relation="viewer", scope_field="dept"))
        perm = PermissionRule(operation=PermissionKind.READ, condition=cond)
        assert agent.empty_personas_classified_data(self._classified_appspec(perm)) == []

    def test_deny_all_rule_not_flagged(self, agent: AuthAuthorizationAgent) -> None:
        perm = PermissionRule(operation=PermissionKind.DELETE, deny_all=True)
        assert agent.empty_personas_classified_data(self._classified_appspec(perm)) == []

    def test_field_only_condition_downgraded_to_likely(self, agent: AuthAuthorizationAgent) -> None:
        # Row filter without any principal check: still a finding, but the
        # "any authenticated user" CONFIRMED claim is wrong — LIKELY + reword.
        from dazzle.core.ir.conditions import (
            Comparison,
            ComparisonOperator,
            ConditionExpr,
            ConditionValue,
        )
        from dazzle.sentinel.models import Confidence

        cond = ConditionExpr(
            comparison=Comparison(
                field="status",
                operator=ComparisonOperator.EQUALS,
                value=ConditionValue(literal="draft"),
            )
        )
        perm = PermissionRule(operation=PermissionKind.READ, condition=cond)
        findings = agent.empty_personas_classified_data(self._classified_appspec(perm))
        assert len(findings) == 1
        assert findings[0].confidence == Confidence.LIKELY
        assert "WHICH ROWS" in findings[0].description

    def test_bare_empty_rule_stays_confirmed(self, agent: AuthAuthorizationAgent) -> None:
        from dazzle.sentinel.models import Confidence

        perm = PermissionRule(operation=PermissionKind.READ)
        findings = agent.empty_personas_classified_data(self._classified_appspec(perm))
        assert len(findings) == 1
        assert findings[0].confidence == Confidence.CONFIRMED


# =============================================================================
# AA-05  Non-admin DELETE without FORBID
# =============================================================================


class TestAA05NonAdminDeleteWithoutForbid:
    @pytest.mark.parametrize(
        ("permissions", "expected_count"),
        [
            (
                [_permission(PermissionKind.DELETE, PolicyEffect.PERMIT, ["editor", "admin"])],
                1,
            ),
            (
                [
                    _permission(PermissionKind.DELETE, PolicyEffect.PERMIT, ["editor"]),
                    _permission(PermissionKind.DELETE, PolicyEffect.FORBID),
                ],
                0,
            ),
            (
                [_permission(PermissionKind.DELETE, PolicyEffect.PERMIT, ["admin"])],
                0,
            ),
            (
                [],
                0,
            ),
        ],
        ids=[
            "test_flags_non_admin_delete",
            "test_passes_when_forbid_present",
            "test_passes_admin_only",
            "test_no_access",
        ],
    )
    def test_non_admin_delete_without_forbid(
        self,
        agent: AuthAuthorizationAgent,
        permissions: list,
        expected_count: int,
    ) -> None:
        """non_admin_delete_without_forbid flags only when non-admin delete lacks a forbid."""
        access = _access(permissions=permissions) if permissions else None
        entity = make_entity("Task", access=access) if access is not None else make_entity("Task")
        findings = agent.non_admin_delete_without_forbid(make_appspec([entity]))
        assert len(findings) == expected_count


# =============================================================================
# AA-06  Weak security with sensitive data
# =============================================================================


class TestAA06WeakSecuritySensitiveData:
    def _basic_security(self) -> MagicMock:
        from dazzle.core.ir.security import SecurityProfile

        sec = MagicMock()
        sec.profile = SecurityProfile.BASIC
        return sec

    def test_flags_basic_with_pii(self, agent: AuthAuthorizationAgent) -> None:
        cls_spec = MagicMock()
        cls_spec.classification = MagicMock()
        cls_spec.classification.value = "pii_direct"
        cls_spec.entity = "Customer"
        policies = MagicMock()
        policies.classifications = [cls_spec]
        appspec = make_appspec(
            security=self._basic_security(),
            policies=policies,
        )
        findings = agent.weak_security_sensitive_data(appspec)
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_passes_no_security(self, agent: AuthAuthorizationAgent) -> None:
        assert agent.weak_security_sensitive_data(make_appspec()) == []

    def test_passes_strict_profile(self, agent: AuthAuthorizationAgent) -> None:
        from dazzle.core.ir.security import SecurityProfile

        sec = MagicMock()
        sec.profile = SecurityProfile.STRICT
        cls_spec = MagicMock()
        cls_spec.classification = MagicMock()
        cls_spec.classification.value = "pii_direct"
        cls_spec.entity = "Customer"
        policies = MagicMock()
        policies.classifications = [cls_spec]
        assert (
            agent.weak_security_sensitive_data(make_appspec(security=sec, policies=policies)) == []
        )


# =============================================================================
# AA-07  Surface/entity persona mismatch
# =============================================================================


class TestAA07PersonaMismatch:
    def test_flags_surface_only_personas(self, agent: AuthAuthorizationAgent) -> None:
        perm = _permission(PermissionKind.READ, personas=["admin"])
        entity = make_entity("Task", access=_access(permissions=[perm]))
        s_access = _surface_access(allow_personas=["admin", "viewer"])
        surface = _surface("task_list", entity_ref="Task", access=s_access)
        appspec = make_appspec([entity], surfaces=[surface])
        findings = agent.surface_entity_persona_mismatch(appspec)
        assert len(findings) == 1
        assert "viewer" in findings[0].description

    def test_passes_matching_personas(self, agent: AuthAuthorizationAgent) -> None:
        perm = _permission(PermissionKind.READ, personas=["admin"])
        entity = make_entity("Task", access=_access(permissions=[perm]))
        s_access = _surface_access(allow_personas=["admin"])
        surface = _surface("task_list", entity_ref="Task", access=s_access)
        assert (
            agent.surface_entity_persona_mismatch(make_appspec([entity], surfaces=[surface])) == []
        )

    def test_skips_when_entity_has_no_persona_restrictions(
        self, agent: AuthAuthorizationAgent
    ) -> None:
        perm = _permission(PermissionKind.READ, personas=[])
        entity = make_entity("Task", access=_access(permissions=[perm]))
        s_access = _surface_access(allow_personas=["admin"])
        surface = _surface("task_list", entity_ref="Task", access=s_access)
        assert (
            agent.surface_entity_persona_mismatch(make_appspec([entity], surfaces=[surface])) == []
        )


# =============================================================================
# AA-08  Webhook without auth
# =============================================================================


class TestAA08WebhookWithoutAuth:
    def test_flags_webhook_no_auth(self, agent: AuthAuthorizationAgent) -> None:
        wh = _webhook("order_created")
        findings = agent.webhook_without_auth(make_appspec(webhooks=[wh]))
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH

    def test_passes_with_auth(self, agent: AuthAuthorizationAgent) -> None:
        wh = _webhook("order_created", auth=MagicMock())
        assert agent.webhook_without_auth(make_appspec(webhooks=[wh])) == []


# =============================================================================
# Full agent run
# =============================================================================


class TestAuthAgentRun:
    def test_agent_id(self, agent: AuthAuthorizationAgent) -> None:
        assert agent.agent_id == AgentId.AA

    def test_has_8_heuristics(self, agent: AuthAuthorizationAgent) -> None:
        assert len(agent.get_heuristics()) == 8

    def test_heuristic_ids(self, agent: AuthAuthorizationAgent) -> None:
        ids = [meta.heuristic_id for meta, _ in agent.get_heuristics()]
        assert ids == [f"AA-0{i}" for i in range(1, 9)]
