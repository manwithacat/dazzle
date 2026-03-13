"""Tests for GrantCheck IR type on ConditionExpr."""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.conditions import ConditionExpr, GrantCheck, LogicalOperator, RoleCheck


class TestGrantCheckCreation:
    def test_grant_check_creation(self) -> None:
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        assert gc.relation == "acting_hod"
        assert gc.scope_field == "department"

    def test_grant_check_creation_observer(self) -> None:
        gc = GrantCheck(relation="observer", scope_field="department")
        assert gc.relation == "observer"
        assert gc.scope_field == "department"

    def test_grant_check_frozen(self) -> None:
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        with pytest.raises((ValidationError, TypeError)):
            gc.relation = "other"  # type: ignore[misc]

    def test_grant_check_requires_relation(self) -> None:
        with pytest.raises(ValidationError):
            GrantCheck(scope_field="department")  # type: ignore[call-arg]

    def test_grant_check_requires_scope_field(self) -> None:
        with pytest.raises(ValidationError):
            GrantCheck(relation="acting_hod")  # type: ignore[call-arg]


class TestConditionExprWithGrantCheck:
    def test_condition_expr_with_grant_check(self) -> None:
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        expr = ConditionExpr(grant_check=gc)
        assert expr.grant_check is gc
        assert expr.is_grant_check is True
        assert expr.is_compound is False
        assert expr.is_role_check is False

    def test_condition_expr_default_grant_check_is_none(self) -> None:
        expr = ConditionExpr()
        assert expr.grant_check is None
        assert expr.is_grant_check is False

    def test_condition_expr_grant_check_in_compound(self) -> None:
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        rc = RoleCheck(role_name="admin")
        left = ConditionExpr(grant_check=gc)
        right = ConditionExpr(role_check=rc)
        compound = ConditionExpr(left=left, operator=LogicalOperator.OR, right=right)

        assert compound.is_compound is True
        assert compound.left is not None
        assert compound.left.is_grant_check is True
        assert compound.right is not None
        assert compound.right.is_role_check is True

    def test_condition_expr_is_grant_check_false_when_role_check(self) -> None:
        rc = RoleCheck(role_name="admin")
        expr = ConditionExpr(role_check=rc)
        assert expr.is_grant_check is False
        assert expr.is_role_check is True


class TestGrantCheckExportedFromIR:
    def test_grant_check_importable_from_ir(self) -> None:
        from dazzle.core.ir import GrantCheck as IRGrantCheck

        assert IRGrantCheck is GrantCheck

    def test_grant_check_in_all(self) -> None:
        import dazzle.core.ir as ir

        assert "GrantCheck" in ir.__all__
