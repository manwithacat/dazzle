# tests/unit/test_grant_converter.py
"""Test that _convert_access_condition handles grant_check correctly."""

from uuid import uuid4

import pytest

from dazzle.core.ir.conditions import ConditionExpr, GrantCheck
from dazzle.http.converters.entity_converter import _convert_access_condition
from dazzle.http.specs.auth import AccessConditionSpec
from dazzle.render.access_evaluator import (
    AccessRuntimeContext,
    evaluate_access_condition,
)


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
    @pytest.mark.parametrize(
        "scenario,expected",
        [
            ("no_grants", False),
            ("matching_grant", True),
            ("wrong_relation", False),
            ("missing_scope_field", False),
        ],
        ids=[
            "test_grant_check_no_grants_denies",
            "test_grant_check_with_matching_grant_allows",
            "test_grant_check_wrong_relation_denies",
            "test_grant_check_missing_scope_field_denies",
        ],
    )
    def test_evaluate_grant_check(self, scenario: str, expected: bool):
        spec = AccessConditionSpec(
            kind="grant_check",
            grant_relation="acting_hod",
            grant_scope_field="department",
        )
        if scenario == "no_grants":
            ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=["member"])
            record = {"department": str(uuid4())}
        elif scenario == "matching_grant":
            dept_id = str(uuid4())
            ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
            ctx.active_grants = [  # type: ignore[attr-defined]
                {"relation": "acting_hod", "scope_value": dept_id},
            ]
            record = {"department": dept_id}
        elif scenario == "wrong_relation":
            dept_id = str(uuid4())
            ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
            ctx.active_grants = [  # type: ignore[attr-defined]
                {"relation": "observer", "scope_value": dept_id},
            ]
            record = {"department": dept_id}
        else:  # missing_scope_field
            ctx = AccessRuntimeContext(user_id=str(uuid4()), roles=[])
            ctx.active_grants = [  # type: ignore[attr-defined]
                {"relation": "acting_hod", "scope_value": "some-dept"},
            ]
            record = {}
        assert evaluate_access_condition(spec, record, ctx) is expected
