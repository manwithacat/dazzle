"""
Tests for ScopePredicate algebra types in DAZZLE IR.

Covers construction of all 7 predicate node types and BoolComposite
simplification rules.
"""

from __future__ import annotations

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)


class TestPredicateConstruction:
    """Verify each of the 7 predicate types can be constructed."""

    def test_column_check(self) -> None:
        pred = ColumnCheck(
            field="status",
            op=CompOp.EQ,
            value=ValueRef(literal="active"),
        )
        assert pred.field == "status"
        assert pred.op == CompOp.EQ
        assert pred.value.literal == "active"
        assert pred.kind == "column_check"

    def test_user_attr_check(self) -> None:
        pred = UserAttrCheck(
            field="owner_id",
            op=CompOp.EQ,
            user_attr="id",
        )
        assert pred.field == "owner_id"
        assert pred.op == CompOp.EQ
        assert pred.user_attr == "id"
        assert pred.kind == "user_attr_check"

    def test_path_check_depth_1(self) -> None:
        pred = PathCheck(
            path=["owner_id"],
            op=CompOp.EQ,
            value=ValueRef(current_user=True),
        )
        assert pred.path == ["owner_id"]
        assert pred.value.current_user is True
        assert pred.kind == "path_check"

    def test_path_check_depth_3(self) -> None:
        pred = PathCheck(
            path=["project", "team", "org_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="org_id"),
        )
        assert pred.path == ["project", "team", "org_id"]
        assert pred.value.user_attr == "org_id"

    def test_exists_check_not_negated(self) -> None:
        binding = ExistsBinding(
            junction_field="user_id",
            target="current_user",
            operator="=",
        )
        pred = ExistsCheck(
            target_entity="TeamMembership",
            bindings=[binding],
            negated=False,
        )
        assert pred.target_entity == "TeamMembership"
        assert len(pred.bindings) == 1
        assert pred.negated is False
        assert pred.kind == "exists_check"

    def test_exists_check_negated(self) -> None:
        binding = ExistsBinding(
            junction_field="user_id",
            target="current_user",
            operator="=",
        )
        pred = ExistsCheck(
            target_entity="BanList",
            bindings=[binding],
            negated=True,
        )
        assert pred.negated is True

    def test_bool_composite_and(self) -> None:
        left = ColumnCheck(field="active", op=CompOp.EQ, value=ValueRef(literal=True))
        right = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
        pred = BoolComposite(op=BoolOp.AND, children=[left, right])
        assert pred.op == BoolOp.AND
        assert len(pred.children) == 2
        assert pred.kind == "bool_composite"

    def test_tautology(self) -> None:
        t = Tautology()
        assert t.kind == "tautology"

    def test_contradiction(self) -> None:
        c = Contradiction()
        assert c.kind == "contradiction"

    def test_tautology_and_contradiction_are_distinct(self) -> None:
        t = Tautology()
        c = Contradiction()
        assert t != c
        assert t.kind != c.kind

    def test_value_ref_literal_null(self) -> None:
        ref = ValueRef(literal_null=True)
        assert ref.literal_null is True

    def test_comp_op_values(self) -> None:
        assert CompOp.EQ == "="
        assert CompOp.NEQ == "!="
        assert CompOp.GT == ">"
        assert CompOp.LT == "<"
        assert CompOp.GTE == ">="
        assert CompOp.LTE == "<="
        assert CompOp.IN == "in"
        assert CompOp.NOT_IN == "not in"
        assert CompOp.IS == "is"
        assert CompOp.IS_NOT == "is not"

    def test_bool_op_values(self) -> None:
        assert BoolOp.AND == "and"
        assert BoolOp.OR == "or"
        assert BoolOp.NOT == "not"


class TestSimplification:
    """Verify BoolComposite.make() applies algebraic simplifications."""

    def _col(self) -> ColumnCheck:
        """Helper: a simple column predicate."""
        return ColumnCheck(
            field="status",
            op=CompOp.EQ,
            value=ValueRef(literal="active"),
        )

    def test_and_with_tautology_returns_x(self) -> None:
        x = self._col()
        result = BoolComposite.make(BoolOp.AND, [x, Tautology()])
        assert result == x

    def test_or_with_tautology_returns_tautology(self) -> None:
        x = self._col()
        result = BoolComposite.make(BoolOp.OR, [x, Tautology()])
        assert isinstance(result, Tautology)

    def test_and_with_contradiction_returns_contradiction(self) -> None:
        x = self._col()
        result = BoolComposite.make(BoolOp.AND, [x, Contradiction()])
        assert isinstance(result, Contradiction)

    def test_or_with_contradiction_returns_x(self) -> None:
        x = self._col()
        result = BoolComposite.make(BoolOp.OR, [x, Contradiction()])
        assert result == x

    def test_not_tautology_returns_contradiction(self) -> None:
        result = BoolComposite.make(BoolOp.NOT, [Tautology()])
        assert isinstance(result, Contradiction)

    def test_not_contradiction_returns_tautology(self) -> None:
        result = BoolComposite.make(BoolOp.NOT, [Contradiction()])
        assert isinstance(result, Tautology)

    def test_double_negation_elimination(self) -> None:
        x = self._col()
        not_x = BoolComposite.make(BoolOp.NOT, [x])
        not_not_x = BoolComposite.make(BoolOp.NOT, [not_x])
        assert not_not_x == x

    def test_no_simplification_needed_returns_composite(self) -> None:
        x = self._col()
        y = UserAttrCheck(field="owner_id", op=CompOp.EQ, user_attr="id")
        result = BoolComposite.make(BoolOp.AND, [x, y])
        assert isinstance(result, BoolComposite)
        assert result.op == BoolOp.AND  # type: ignore[union-attr]

    def test_and_identity_both_tautologies(self) -> None:
        # AND(Tautology, Tautology) → Tautology (absorbed from left first)
        result = BoolComposite.make(BoolOp.AND, [Tautology(), Tautology()])
        assert isinstance(result, Tautology)

    def test_or_identity_both_contradictions(self) -> None:
        # OR(Contradiction, Contradiction) → Contradiction
        result = BoolComposite.make(BoolOp.OR, [Contradiction(), Contradiction()])
        assert isinstance(result, Contradiction)
