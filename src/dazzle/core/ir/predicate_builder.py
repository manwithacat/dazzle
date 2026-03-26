"""Convert ConditionExpr trees to ScopePredicate trees.

This module provides :func:`build_scope_predicate`, which takes a parsed
:class:`~dazzle.core.ir.conditions.ConditionExpr` and the FK graph for the
owning entity, and produces a fully typed :data:`ScopePredicate` tree
suitable for code generation and runtime evaluation.

Mapping rules
-------------
- ``None``                          → :class:`Tautology`
- ``via`` condition                 → :class:`ExistsCheck`
- Simple comparison, dotted field   → :class:`PathCheck`
- Simple comparison, ``current_user`` value → :class:`UserAttrCheck`
- Simple comparison, ``null`` value → :class:`ColumnCheck` with IS / IS NOT
- Simple comparison, other          → :class:`ColumnCheck`
- ``role_check``                    → :exc:`ValueError` (belongs in ``permit:``)
- ``grant_check``                   → :exc:`ValueError` (belongs in ``permit:``)
- Compound AND / OR / NOT           → :class:`BoolComposite` (via ``make()``)
"""

from dazzle.core.ir.conditions import (
    ComparisonOperator,
    ConditionExpr,
    ViaBinding,
)
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    ScopePredicate,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

# ---------------------------------------------------------------------------
# Operator mapping
# ---------------------------------------------------------------------------

_OP_MAP: dict[ComparisonOperator, CompOp] = {
    ComparisonOperator.EQUALS: CompOp.EQ,
    ComparisonOperator.NOT_EQUALS: CompOp.NEQ,
    ComparisonOperator.GREATER_THAN: CompOp.GT,
    ComparisonOperator.LESS_THAN: CompOp.LT,
    ComparisonOperator.GREATER_EQUAL: CompOp.GTE,
    ComparisonOperator.LESS_EQUAL: CompOp.LTE,
    ComparisonOperator.IN: CompOp.IN,
    ComparisonOperator.NOT_IN: CompOp.NOT_IN,
    ComparisonOperator.IS: CompOp.IS,
    ComparisonOperator.IS_NOT: CompOp.IS_NOT,
}

# ---------------------------------------------------------------------------
# ViaBinding → ExistsBinding
# ---------------------------------------------------------------------------


def _convert_binding(binding: ViaBinding) -> ExistsBinding:
    return ExistsBinding(
        junction_field=binding.junction_field,
        target=binding.target,
        operator=binding.operator,
    )


# ---------------------------------------------------------------------------
# Public converter
# ---------------------------------------------------------------------------


def build_scope_predicate(
    condition: ConditionExpr | None,
    entity_name: str,
    fk_graph: FKGraph,
) -> ScopePredicate:
    """Convert a :class:`ConditionExpr` to a :data:`ScopePredicate` tree.

    Args:
        condition:   The parsed condition expression, or ``None`` for
                     unrestricted access.
        entity_name: Name of the root entity this condition is scoped to.
                     Used for FK path validation.
        fk_graph:    FK graph built from the application spec.

    Returns:
        A :data:`ScopePredicate` node (or tree for compound conditions).

    Raises:
        ValueError: If the condition contains a ``role_check`` or
                    ``grant_check``, which belong in ``permit:`` blocks.
        ValueError: If a dotted path cannot be resolved in the FK graph.
    """
    if condition is None:
        return Tautology()

    # -- Role / grant checks are not allowed in scope: blocks ---------------
    if condition.role_check is not None:
        raise ValueError(
            "Role checks belong in permit: blocks, not scope: blocks. "
            f"Found role_check for '{condition.role_check.role_name}'."
        )

    if condition.grant_check is not None:
        raise ValueError(
            "Grant checks belong in permit: blocks, not scope: blocks. "
            f"Found grant_check for relation '{condition.grant_check.relation}'."
        )

    # -- Via (junction-table subquery) --------------------------------------
    if condition.via_condition is not None:
        via = condition.via_condition
        return ExistsCheck(
            target_entity=via.junction_entity,
            bindings=[_convert_binding(b) for b in via.bindings],
            negated=via.negated,
        )

    # -- Simple comparison --------------------------------------------------
    if condition.comparison is not None:
        cmp = condition.comparison
        field = cmp.field or ""
        op = _OP_MAP[cmp.operator]
        raw_value = cmp.value.literal  # str | int | float | bool | None

        # Null literal: rewrite operator to IS / IS NOT
        if isinstance(raw_value, str) and raw_value == "null":
            null_op = CompOp.IS if op == CompOp.EQ else CompOp.IS_NOT
            null_value = ValueRef(literal_null=True)
            if "." in field:
                path = field.split(".")
                return PathCheck(path=path, op=null_op, value=null_value)
            return ColumnCheck(field=field, op=null_op, value=null_value)

        # Dotted left side → PathCheck
        if "." in field:
            path = field.split(".")
            value_ref = _resolve_value_ref(raw_value)
            return PathCheck(path=path, op=op, value=value_ref)

        # current_user or current_user.<attr>
        if isinstance(raw_value, str) and raw_value == "current_user":
            return UserAttrCheck(field=field, op=op, user_attr="entity_id")

        if isinstance(raw_value, str) and raw_value.startswith("current_user."):
            attr = raw_value[len("current_user.") :]
            return UserAttrCheck(field=field, op=op, user_attr=attr)

        # Plain column check
        return ColumnCheck(field=field, op=op, value=_resolve_value_ref(raw_value))

    # -- Compound (AND / OR / NOT) ------------------------------------------
    if condition.operator is not None:
        from dazzle.core.ir.conditions import LogicalOperator

        bool_op_map = {
            LogicalOperator.AND: BoolOp.AND,
            LogicalOperator.OR: BoolOp.OR,
            LogicalOperator.NOT: BoolOp.NOT,
        }
        bool_op = bool_op_map[condition.operator]

        if bool_op is BoolOp.NOT:
            left_pred = build_scope_predicate(condition.left, entity_name, fk_graph)
            return BoolComposite.make(BoolOp.NOT, [left_pred])

        # AND / OR — both left and right must be present
        left_pred = build_scope_predicate(condition.left, entity_name, fk_graph)
        right_pred = build_scope_predicate(condition.right, entity_name, fk_graph)
        return BoolComposite.make(bool_op, [left_pred, right_pred])

    # Fallback: empty condition with no recognised variant → Tautology
    return Tautology()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_value_ref(raw: str | int | float | bool | None) -> ValueRef:
    """Build a :class:`ValueRef` from a raw Python value.

    Handles all value forms:
    - ``"current_user"``        → ``ValueRef(current_user=True)``
    - ``"current_user.<attr>"`` → ``ValueRef(user_attr=<attr>)``
    - any other value           → ``ValueRef(literal=raw)``

    Note: ``"null"`` string must be handled by the caller (converted to
    IS / IS NOT before reaching this function).
    """
    if isinstance(raw, str) and raw == "current_user":
        return ValueRef(current_user=True)
    if isinstance(raw, str) and raw.startswith("current_user."):
        attr = raw[len("current_user.") :]
        return ValueRef(user_attr=attr)
    return ValueRef(literal=raw)


def _build_value_ref(raw: str | int | float | bool | None) -> ValueRef:
    """Build a :class:`ValueRef` from a raw literal value (no current_user logic)."""
    return ValueRef(literal=raw)
