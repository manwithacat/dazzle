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

from typing import Any

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
    entities_by_name: dict[str, Any] | None = None,
) -> ScopePredicate:
    """Convert a :class:`ConditionExpr` to a :data:`ScopePredicate` tree.

    Args:
        condition:   The parsed condition expression, or ``None`` for
                     unrestricted access.
        entity_name: Name of the root entity this condition is scoped to.
                     Used for FK path validation.
        fk_graph:    FK graph built from the application spec.
        entities_by_name: Optional ``{name: EntitySpec}`` map. When provided,
                     a ``field = current_tenant`` check whose ``field`` is an FK
                     to a hierarchical tenant kind (ADR-0036) is expanded into a
                     self-or-ancestor disjunction (aggregate at an ancestor host,
                     single at a leaf host). The linker passes this **only for
                     READ/LIST** scopes; writes keep the single leaf check
                     (aggregate hosts are read-only, ADR-0036). ``None`` (the
                     default) preserves the Layer-1 single-check behaviour.

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

        # current_tenant (#1394) — bare or the explicit `.id` form both bind the
        # host-resolved tenant's id. Modelled as a ColumnCheck carrying a
        # current_tenant ValueRef (reuses the audited ColumnCheck path; the
        # compiler/resolvers branch on ValueRef.current_tenant). Scope equality
        # is id-only — `current_tenant.<other_attr>` is a display-gate concept,
        # rejected here so it can't silently bind the id.
        if isinstance(raw_value, str) and raw_value in ("current_tenant", "current_tenant.id"):
            base = ColumnCheck(field=field, op=op, value=ValueRef(current_tenant=True))
            # ADR-0036 Layer 2: on a READ/LIST scope (caller opts in via
            # entities_by_name) whose `field` is an FK to a tenant kind with an
            # ancestor chain, expand to a self-or-ancestor disjunction so the one
            # scope aggregates at an ancestor host and narrows at a leaf host.
            # ONLY for `=` — a `!=` disjunction would leak — and fail-closed:
            # any resolution uncertainty returns the unexpanded single check.
            if op == CompOp.EQ and entities_by_name:
                return _expand_current_tenant_hierarchy(
                    field, base, entity_name, fk_graph, entities_by_name
                )
            return base

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
            left_pred = build_scope_predicate(
                condition.left, entity_name, fk_graph, entities_by_name
            )
            return BoolComposite.make(BoolOp.NOT, [left_pred])

        # AND / OR — both left and right must be present
        left_pred = build_scope_predicate(condition.left, entity_name, fk_graph, entities_by_name)
        right_pred = build_scope_predicate(condition.right, entity_name, fk_graph, entities_by_name)
        return BoolComposite.make(bool_op, [left_pred, right_pred])

    # Fallback: empty condition with no recognised variant → Tautology
    return Tautology()


# Cycle guard for the tenant-hierarchy walk. NOTE: this expansion runs inside
# `build_appspec` (the linker), which does NOT run
# `validate_tenant_hierarchy_and_membership` — that H2 cycle check is a separate
# `dazzle validate` phase a bare `build_appspec` caller can skip. So this bound +
# the `seen` set below are the SOLE defense against a malformed/cyclic chain
# looping here; do not weaken them on the assumption the validator gated this. A
# cycle collapses fail-closed to the single check (verified adversarially).
_MAX_TENANT_HIERARCHY_DEPTH = 16


def _expand_current_tenant_hierarchy(
    field: str,
    base: ColumnCheck,
    entity_name: str,
    fk_graph: FKGraph,
    entities_by_name: dict[str, Any],
) -> ScopePredicate:
    """ADR-0036 Layer 2 — expand ``field = current_tenant`` into a self-or-ancestor
    disjunction over the declared tenant hierarchy.

    ``field`` is an FK on *entity_name* pointing at a tenant kind ``K``. If ``K``
    has a ``tenant_host.parent`` chain, the row should be visible when the
    host-resolved tenant is ``K`` (single, at a leaf host) **or** any ancestor of
    ``K`` (aggregate, at an ancestor host). This yields::

        field = current_tenant                       -- host kind == K (single)
        OR field.<K.parent>          = current_tenant -- host kind == K's parent
        OR field.<K.parent>.<...>    = current_tenant -- deeper ancestors

    Each ancestor leg is a :class:`PathCheck` that walks ``K``'s ``parent:`` FK
    chain appended to the authored ``field``. The deny cases (host is a descendant
    of ``K``, or unrelated) fall out: no leg's value matches, so the row is
    excluded — fail-closed, no new authority path.

    **Fail-closed:** any resolution uncertainty (field is not an FK, target is not
    a hierarchical tenant kind, a broken/cyclic chain, missing entity) returns the
    unexpanded ``base`` single check — never a broader predicate.
    """
    target = fk_graph.resolve_target(entity_name, field)
    if not target:
        return base  # `field` is not an FK → Layer-1 single check
    kind = entities_by_name.get(target)
    th = getattr(kind, "tenant_host", None) if kind is not None else None
    if th is None or getattr(th, "parent", None) is None:
        return base  # target is not a hierarchical tenant kind → Layer-1

    legs: list[ScopePredicate] = [base]
    path: list[str] = [field]
    seen: set[str] = {entity_name, target}
    cur: Any = kind
    depth = 0
    while True:
        cur_th = getattr(cur, "tenant_host", None)
        parent_fk = getattr(cur_th, "parent", None) if cur_th is not None else None
        if parent_fk is None:
            break  # reached the hierarchy root
        depth += 1
        if depth > _MAX_TENANT_HIERARCHY_DEPTH:
            return base  # runaway / cycle → fail-closed
        path = [*path, str(parent_fk)]
        legs.append(PathCheck(path=list(path), op=CompOp.EQ, value=ValueRef(current_tenant=True)))
        nxt = fk_graph.resolve_target(cur.name, str(parent_fk))
        if not nxt or nxt in seen:
            return base  # broken or cyclic parent chain → fail-closed
        seen.add(nxt)
        nxt_kind = entities_by_name.get(nxt)
        if nxt_kind is None:
            return base  # parent kind missing from the spec → fail-closed
        cur = nxt_kind

    if len(legs) == 1:
        return base  # no ancestor legs added → single check
    return BoolComposite.make(BoolOp.OR, legs)


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
    # current_tenant (#1394) — id-only scope binding (see build_scope_predicate).
    if isinstance(raw, str) and raw in ("current_tenant", "current_tenant.id"):
        return ValueRef(current_tenant=True)
    return ValueRef(literal=raw)


def _build_value_ref(raw: str | int | float | bool | None) -> ValueRef:
    """Build a :class:`ValueRef` from a raw literal value (no current_user logic)."""
    return ValueRef(literal=raw)
