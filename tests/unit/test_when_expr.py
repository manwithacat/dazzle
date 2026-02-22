"""Tests for surface conditional field visibility (when_expr) (#363)."""

from __future__ import annotations

from dazzle_ui.runtime.template_context import FieldContext
from dazzle_ui.utils.expression_eval import evaluate_when_expr

# =============================================================================
# evaluate_when_expr tests
# =============================================================================


class TestEvaluateWhenExpr:
    """evaluate_when_expr() should evaluate serialized Expr strings against record data."""

    def test_empty_expr_returns_true(self) -> None:
        assert evaluate_when_expr("", {"status": "active"}) is True

    def test_equality_match(self) -> None:
        assert evaluate_when_expr('(status == "shipped")', {"status": "shipped"}) is True

    def test_equality_no_match(self) -> None:
        assert evaluate_when_expr('(status == "shipped")', {"status": "pending"}) is False

    def test_not_equal(self) -> None:
        assert evaluate_when_expr('(status != "cancelled")', {"status": "active"}) is True
        assert evaluate_when_expr('(status != "cancelled")', {"status": "cancelled"}) is False

    def test_numeric_comparison(self) -> None:
        assert evaluate_when_expr("(amount > 100)", {"amount": 200}) is True
        assert evaluate_when_expr("(amount > 100)", {"amount": 50}) is False

    def test_missing_field_returns_false(self) -> None:
        """If the referenced field doesn't exist in data, comparison returns False."""
        assert evaluate_when_expr('(status == "active")', {}) is False

    def test_boolean_literal(self) -> None:
        assert evaluate_when_expr("(is_active == true)", {"is_active": True}) is True
        assert evaluate_when_expr("(is_active == true)", {"is_active": False}) is False

    def test_and_expression(self) -> None:
        expr = '((status == "shipped") and (amount > 100))'
        assert evaluate_when_expr(expr, {"status": "shipped", "amount": 200}) is True
        assert evaluate_when_expr(expr, {"status": "shipped", "amount": 50}) is False
        assert evaluate_when_expr(expr, {"status": "pending", "amount": 200}) is False

    def test_or_expression(self) -> None:
        expr = '((status == "shipped") or (status == "delivered"))'
        assert evaluate_when_expr(expr, {"status": "shipped"}) is True
        assert evaluate_when_expr(expr, {"status": "delivered"}) is True
        assert evaluate_when_expr(expr, {"status": "pending"}) is False

    def test_in_expression(self) -> None:
        expr = '(status in ["active", "pending"])'
        assert evaluate_when_expr(expr, {"status": "active"}) is True
        assert evaluate_when_expr(expr, {"status": "closed"}) is False

    def test_invalid_expr_fails_open(self) -> None:
        """Unparseable expressions should fail open (return True)."""
        assert evaluate_when_expr("!!! invalid !!!", {"status": "x"}) is True

    def test_dotted_path(self) -> None:
        """Nested field references should resolve through dicts."""
        assert (
            evaluate_when_expr(
                '(contact.status == "verified")', {"contact": {"status": "verified"}}
            )
            is True
        )
        assert (
            evaluate_when_expr('(contact.status == "verified")', {"contact": {"status": "pending"}})
            is False
        )


# =============================================================================
# FieldContext model tests
# =============================================================================


class TestFieldContextWhenExpr:
    """FieldContext should support when_expr and visible fields."""

    def test_defaults(self) -> None:
        field = FieldContext(name="title", label="Title")
        assert field.when_expr == ""
        assert field.visible is True

    def test_when_expr_set(self) -> None:
        field = FieldContext(name="tracking", label="Tracking", when_expr='(status == "shipped")')
        assert field.when_expr == '(status == "shipped")'
        assert field.visible is True  # visible until evaluated

    def test_visible_can_be_set_false(self) -> None:
        field = FieldContext(name="refund", label="Refund", visible=False)
        assert field.visible is False


# =============================================================================
# Template compiler integration test
# =============================================================================


class TestBuildFormFieldsWhenExpr:
    """_build_form_fields should pass through when_expr from surface elements."""

    def test_when_expr_propagated(self) -> None:
        from dazzle.core.ir.expressions import BinaryExpr, BinaryOp, FieldRef, Literal
        from dazzle.core.ir.surfaces import SurfaceElement, SurfaceSection, SurfaceSpec
        from dazzle_ui.converters.template_compiler import _build_form_fields

        when = BinaryExpr(
            op=BinaryOp.EQ,
            left=FieldRef(path=["status"]),
            right=Literal(value="shipped"),
        )
        surface = SurfaceSpec(
            name="order_detail",
            mode="view",
            entity_ref="Order",
            sections=[
                SurfaceSection(
                    name="main",
                    elements=[
                        SurfaceElement(field_name="title", label="Title"),
                        SurfaceElement(
                            field_name="tracking",
                            label="Tracking",
                            when_expr=when,
                        ),
                    ],
                )
            ],
        )
        fields = _build_form_fields(surface, None)
        assert len(fields) == 2
        assert fields[0].when_expr == ""
        assert fields[1].when_expr == '(status == "shipped")'

    def test_no_when_expr(self) -> None:
        from dazzle.core.ir.surfaces import SurfaceElement, SurfaceSection, SurfaceSpec
        from dazzle_ui.converters.template_compiler import _build_form_fields

        surface = SurfaceSpec(
            name="task_detail",
            mode="view",
            entity_ref="Task",
            sections=[
                SurfaceSection(
                    name="main",
                    elements=[
                        SurfaceElement(field_name="title", label="Title"),
                    ],
                )
            ],
        )
        fields = _build_form_fields(surface, None)
        assert len(fields) == 1
        assert fields[0].when_expr == ""
        assert fields[0].visible is True
