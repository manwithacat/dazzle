"""Integration tests: evaluate_permission emits audit records via the sink."""

from dazzle.rbac.audit import InMemoryAuditSink, get_audit_sink, set_audit_sink
from dazzle_back.runtime.access_evaluator import (
    AccessRuntimeContext,
    evaluate_permission,
)
from dazzle_back.specs import AccessOperationKind, AccessPolicyEffect, EntityAccessSpec
from dazzle_back.specs.auth import AccessConditionSpec, PermissionRuleSpec


def _make_role_rule(
    effect: AccessPolicyEffect, operation: AccessOperationKind, role: str
) -> PermissionRuleSpec:
    return PermissionRuleSpec(
        effect=effect,
        operation=operation,
        condition=AccessConditionSpec(kind="role_check", role_name=role),
    )


def _make_spec(*rules: PermissionRuleSpec) -> EntityAccessSpec:
    return EntityAccessSpec(permissions=list(rules))


class TestAuditEmission:
    def setup_method(self) -> None:
        self._original_sink = get_audit_sink()
        self._sink = InMemoryAuditSink()
        set_audit_sink(self._sink)

    def teardown_method(self) -> None:
        set_audit_sink(self._original_sink)

    def test_emits_permit_record(self) -> None:
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u1", roles=["admin"])

        decision = evaluate_permission(
            spec, AccessOperationKind.READ, {"id": "rec1"}, ctx, entity_name="Task"
        )

        assert decision.allowed is True
        assert len(self._sink.records) == 1
        rec = self._sink.records[0]
        assert rec.allowed is True
        assert rec.effect == "permit"
        assert rec.entity == "Task"
        assert rec.operation == "read"
        assert rec.user_id == "u1"
        assert "admin" in rec.roles
        assert rec.record_id == "rec1"
        assert rec.tier == "row_filter"

    def test_emits_deny_record(self) -> None:
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u2", roles=["student"])

        decision = evaluate_permission(
            spec, AccessOperationKind.READ, None, ctx, entity_name="Course"
        )

        assert decision.allowed is False
        assert len(self._sink.records) == 1
        rec = self._sink.records[0]
        assert rec.allowed is False
        assert rec.effect == "default"
        assert rec.entity == "Course"
        assert rec.operation == "read"
        assert rec.user_id == "u2"
        assert rec.tier == "gate"

    def test_superuser_bypass_emits_record(self) -> None:
        spec = _make_spec()
        ctx = AccessRuntimeContext(user_id="su1", roles=[], is_superuser=True)

        decision = evaluate_permission(
            spec, AccessOperationKind.DELETE, {"id": "rec99"}, ctx, entity_name="Widget"
        )

        assert decision.allowed is True
        assert len(self._sink.records) == 1
        rec = self._sink.records[0]
        assert rec.allowed is True
        assert rec.effect == "permit"
        assert "superuser" in rec.matched_rule
        assert rec.entity == "Widget"

    def test_emits_record_with_no_entity_name(self) -> None:
        """entity_name defaults to empty string when not provided."""
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u3", roles=["admin"])

        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)

        assert len(self._sink.records) == 1
        assert self._sink.records[0].entity == ""

    def test_emits_one_record_per_call(self) -> None:
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u4", roles=["admin"])

        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)
        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)
        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)

        assert len(self._sink.records) == 3

    def test_request_ids_are_unique(self) -> None:
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u5", roles=["admin"])

        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)
        evaluate_permission(spec, AccessOperationKind.READ, None, ctx)

        ids = [r.request_id for r in self._sink.records]
        assert ids[0] != ids[1]

    def test_null_sink_is_default_no_error(self) -> None:
        """With the default NullAuditSink restored, evaluate_permission does not raise."""
        set_audit_sink(self._original_sink)
        spec = _make_spec(
            _make_role_rule(AccessPolicyEffect.PERMIT, AccessOperationKind.READ, "admin")
        )
        ctx = AccessRuntimeContext(user_id="u6", roles=["admin"])
        # Should not raise even though NullAuditSink discards records
        decision = evaluate_permission(spec, AccessOperationKind.READ, None, ctx)
        assert decision.allowed is True
