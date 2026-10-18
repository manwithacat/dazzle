"""Link-time resolution of entity invariant references (#1823).

An invariant whose field reference names nothing on its entity used to
evaluate that reference to ``None`` at runtime, so ``status != blocked``
compared ``status`` with null and held for every record. The linker now
resolves every invariant once, before anything downstream sees it:

* a bare identifier compared with an ``enum`` field, and naming one of that
  field's values, becomes a string literal (``status != blocked`` means
  ``status != "blocked"``);
* a negated numeric literal (``-5``) folds to a literal, and ``today`` /
  ``now`` (± a duration) fold to the duration offset the runtime compares a
  date against;
* any field reference whose first segment is still not a field of the entity
  is an error, as is an expression shape the runtime invariant evaluator
  cannot evaluate (function calls other than ``today`` / ``now``, ``if``,
  arithmetic) or an ``in`` list item that is not a literal — those
  used to convert to a truthy literal and never fire either.

The runtime converter therefore only ever sees literals and real field paths.
"""

from __future__ import annotations

from . import ir
from .ir.expressions import (
    BinaryExpr,
    BinaryOp,
    DurationLiteral,
    Expr,
    FieldRef,
    FuncCall,
    InExpr,
    Literal,
    UnaryExpr,
    UnaryOp,
)

_COMPARISON_OPS = frozenset(
    {BinaryOp.EQ, BinaryOp.NE, BinaryOp.LT, BinaryOp.GT, BinaryOp.LE, BinaryOp.GE}
)
_LOGICAL_OPS = frozenset({BinaryOp.AND, BinaryOp.OR})
_DATE_ANCHORS = frozenset({"today", "now"})


def invariant_known_names(entity: ir.EntitySpec) -> set[str]:
    """Names an invariant field reference may start with on ``entity``.

    Declared and computed fields, plus the storage columns a ``money`` field
    expands to (``<name>_minor`` / ``<name>_currency``) since those are real
    columns on the record.
    """
    names = {f.name for f in entity.fields}
    names.update(cf.name for cf in entity.computed_fields)
    for f in entity.fields:
        if f.type.kind == ir.FieldTypeKind.MONEY:
            names.update({f"{f.name}_minor", f"{f.name}_currency"})
    return names


def _enum_values_by_field(entity: ir.EntitySpec) -> dict[str, set[str]]:
    return {
        f.name: set(f.type.enum_values)
        for f in entity.fields
        if f.type.kind == ir.FieldTypeKind.ENUM and f.type.enum_values
    }


def _negated_literal(node: object) -> Literal | None:
    """``-5`` parses as unary minus on a literal; fold it to the literal ``-5``."""
    if not (isinstance(node, UnaryExpr) and node.op == UnaryOp.NEG):
        return None
    value = node.operand.value if isinstance(node.operand, Literal) else None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return Literal(value=-value)
    return None


class _Resolver:
    """Rewrites one entity's invariants and collects unresolved references."""

    def __init__(self, entity: ir.EntitySpec) -> None:
        self.entity = entity
        self.known = invariant_known_names(entity)
        self.enums = _enum_values_by_field(entity)
        self.problems: list[str] = []

    # -- unified Expr -----------------------------------------------------

    def _enum_literal(self, field_side: object, other: object) -> Literal | None:
        """``other`` as a string literal when it is a bare value of ``field_side``'s enum."""
        if not (isinstance(field_side, FieldRef) and isinstance(other, FieldRef)):
            return None
        if len(field_side.path) != 1 or len(other.path) != 1:
            return None
        name = other.path[0]
        if name in self.known:
            return None  # a real field always wins over an enum value
        if name in self.enums.get(field_side.path[0], set()):
            return Literal(value=name)
        return None

    def _date_anchor(self, node: object) -> DurationLiteral | None:
        """``today`` / ``now`` (± a duration) as the offset-from-today the runtime compares.

        The invariant runtime reads ``date_field > <duration>`` as
        ``date_field > today + <duration>``, so ``today`` is a zero offset and
        ``today + 7d`` a seven-day one. A field named ``today`` still wins.
        """
        if isinstance(node, FieldRef) and len(node.path) == 1 and node.path[0] in _DATE_ANCHORS:
            return None if node.path[0] in self.known else DurationLiteral(value=0, unit="d")
        if isinstance(node, FuncCall) and node.name in _DATE_ANCHORS and not node.args:
            return DurationLiteral(value=0, unit="d")
        if (
            isinstance(node, BinaryExpr)
            and node.op in (BinaryOp.ADD, BinaryOp.SUB)
            and isinstance(node.right, DurationLiteral)
            and self._date_anchor(node.left) is not None
        ):
            sign = 1 if node.op == BinaryOp.ADD else -1
            return DurationLiteral(value=sign * node.right.value, unit=node.right.unit)
        return None

    def expr(self, node: Expr) -> Expr:
        if isinstance(node, Literal | DurationLiteral):
            return node
        folded = self._date_anchor(node) or _negated_literal(node)
        if folded is not None:
            return folded
        if isinstance(node, FieldRef):
            self._check_ref(node.path)
            return node
        if isinstance(node, BinaryExpr) and node.op in _COMPARISON_OPS:
            left = self._enum_literal(node.right, node.left) or self.expr(node.left)
            right = self._enum_literal(node.left, node.right) or self.expr(node.right)
            return BinaryExpr(op=node.op, left=left, right=right)
        if isinstance(node, BinaryExpr) and node.op in _LOGICAL_OPS:
            return BinaryExpr(op=node.op, left=self.expr(node.left), right=self.expr(node.right))
        if isinstance(node, UnaryExpr) and node.op == UnaryOp.NOT:
            return UnaryExpr(op=node.op, operand=self.expr(node.operand))
        if isinstance(node, InExpr):
            return self._in_expr(node)
        self.problems.append(f"'{node}' cannot be evaluated by the invariant runtime")
        return node

    def _in_expr(self, node: InExpr) -> InExpr:
        """``value in [a, b]``: every item must end up a literal (bare enum values resolve)."""
        items: list[Expr] = []
        for item in node.items:
            resolved = self._enum_literal(node.value, item) or _negated_literal(item) or item
            if not isinstance(resolved, Literal):
                self.problems.append(
                    f"'{item}' in `{node}` is not a literal or a value of the compared enum field"
                )
            items.append(resolved)
        return InExpr(value=self.expr(node.value), items=items, negated=node.negated)

    def _check_ref(self, path: list[str]) -> None:
        if path and path[0] not in self.known:
            self.problems.append(f"'{path[0]}' is not a field of {self.entity.name}")

    # -- legacy archetype InvariantExpr -------------------------------------

    def legacy(self, node: ir.InvariantExpr) -> ir.InvariantExpr:
        if isinstance(node, ir.InvariantFieldRef):
            self._check_ref(node.path)
            return node
        if isinstance(node, ir.ComparisonExpr):
            left = self._legacy_enum(node.right, node.left) or self.legacy(node.left)
            right = self._legacy_enum(node.left, node.right) or self.legacy(node.right)
            return ir.ComparisonExpr(left=left, operator=node.operator, right=right)
        if isinstance(node, ir.LogicalExpr):
            return ir.LogicalExpr(
                left=self.legacy(node.left), operator=node.operator, right=self.legacy(node.right)
            )
        if isinstance(node, ir.NotExpr):
            return ir.NotExpr(operand=self.legacy(node.operand))
        return node

    def _legacy_enum(self, field_side: object, other: object) -> ir.InvariantLiteral | None:
        if not (
            isinstance(field_side, ir.InvariantFieldRef) and isinstance(other, ir.InvariantFieldRef)
        ):
            return None
        literal = self._enum_literal(FieldRef(path=field_side.path), FieldRef(path=other.path))
        return ir.InvariantLiteral(value=literal.value) if literal is not None else None


def _resolve_one(resolver: _Resolver, inv: ir.InvariantSpec, errors: list[str]) -> ir.InvariantSpec:
    resolver.problems = []
    update: dict[str, object] = {}
    if inv.invariant_expr is not None:
        update["invariant_expr"] = resolver.expr(inv.invariant_expr)
    if inv.expression is not None:
        update["expression"] = resolver.legacy(inv.expression)
    source = inv.invariant_expr if inv.invariant_expr is not None else inv.expression
    errors.extend(
        f"Entity '{resolver.entity.name}' invariant `{source}`: {problem}"
        for problem in resolver.problems
    )
    return inv.model_copy(update=update)


def resolve_invariant_refs(
    entities: list[ir.EntitySpec],
) -> tuple[list[ir.EntitySpec], list[str]]:
    """Resolve bare enum identifiers in every entity invariant; report dead refs.

    Returns the rewritten entities and one error per field reference that names
    nothing on its entity (or per expression shape the runtime cannot evaluate).
    """
    errors: list[str] = []
    resolved: list[ir.EntitySpec] = []
    for entity in entities:
        if not entity.invariants:
            resolved.append(entity)
            continue
        resolver = _Resolver(entity)
        invariants = [_resolve_one(resolver, inv, errors) for inv in entity.invariants]
        resolved.append(entity.model_copy(update={"invariants": invariants}))
    return resolved, errors
