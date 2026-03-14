# tests/unit/test_grant_converter.py
"""Test that _convert_access_condition handles grant_check correctly."""

from uuid import uuid4

from dazzle.core.ir.conditions import ConditionExpr, GrantCheck
from dazzle_back.converters.entity_converter import _convert_access_condition
from dazzle_back.runtime.access_evaluator import (
    AccessRuntimeContext,
    evaluate_access_condition,
)
from dazzle_back.specs.auth import AccessConditionSpec


class TestConvertGrantCheck:
    def test_grant_check_converts(self):
        """grant_check IR → AccessConditionSpec with kind='grant_check'."""
        cond = ConditionExpr(
            grant_check=GrantCheck(relation="acting_hod", scope_field="department"),
        )
        spec = _convert_access_condition(cond)
        assert spec.kind == "grant_check"
        assert spec.grant_relation == "acting_hod"
        assert spec.grant_scope_field == "department"

    def test_grant_check_in_compound(self):
        """grant_check inside an OR compound expression converts correctly."""
        from dazzle.core.ir import LogicalOperator
        from dazzle.core.ir.conditions import RoleCheck

        cond = ConditionExpr(
            operator=LogicalOperator.OR,
            left=ConditionExpr(
                role_check=RoleCheck(role_name="admin"),
            ),
            right=ConditionExpr(
                grant_check=GrantCheck(relation="observer", scope_field="team"),
            ),
        )
        spec = _convert_access_condition(cond)
        assert spec.kind == "logical"
        assert spec.logical_left is not None
        assert spec.logical_left.kind == "role_check"
        assert spec.logical_right is not None
        assert spec.logical_right.kind == "grant_check"
        assert spec.logical_right.grant_relation == "observer"

    def test_grant_check_serializes(self):
        """AccessConditionSpec with grant_check serializes to dict."""
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        d = spec.model_dump(exclude_none=True)
        assert d["kind"] == "grant_check"
        assert d["grant_relation"] == "acting_hod"
        assert d["grant_scope_field"] == "department"


class TestEvaluateGrantCheck:
    def test_grant_check_no_grants_denies(self):
        """grant_check with no active grants returns False."""
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=["member"])
        result = evaluate_access_condition(spec, {"department": str(uuid4())}, ctx)
        assert result is False

    def test_grant_check_with_matching_grant_allows(self):
        """grant_check with matching active grant returns True."""
        dept_id = str(uuid4())
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
        # Attach active_grants to context
        ctx.active_grants = [  # type: ignore[attr-defined]
            {"relation": "acting_hod", "scope_value": dept_id},
        ]
        result = evaluate_access_condition(spec, {"department": dept_id}, ctx)
        assert result is True

    def test_grant_check_wrong_relation_denies(self):
        """grant_check with non-matching relation returns False."""
        dept_id = str(uuid4())
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
        ctx.active_grants = [  # type: ignore[attr-defined]
            {"relation": "observer", "scope_value": dept_id},
        ]
        result = evaluate_access_condition(spec, {"department": dept_id}, ctx)
        assert result is False

    def test_grant_check_missing_scope_field_denies(self):
        """grant_check where record lacks scope field returns False."""
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
        ctx.active_grants = [  # type: ignore[attr-defined]
            {"relation": "acting_hod", "scope_value": "some-dept"},
        ]
        result = evaluate_access_condition(spec, {}, ctx)
        assert result is False
