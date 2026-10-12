"""Money-field validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir
from ..ir.aggregates import AggregateExpr, AggregateRef, DerivedMetric
from ..ir.conditions import ComparisonOperator, ConditionExpr, LogicalOperator
from ..ir.fields import FieldTypeKind
from ..ir.workspaces import WorkspaceRegion, WorkspaceSpec


def validate_money_fields(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Warn when an entity money-like field is a bare decimal without a currency.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for entity in appspec.domain.entities:
        for field in entity.fields:
            if not ir.is_money_field_name(field.name):
                continue

            # For entities, using decimal is okay but money is preferred
            if field.type.kind == ir.FieldTypeKind.DECIMAL:
                # Check if there's a corresponding currency field
                field_names = {f.name for f in entity.fields}
                has_currency = any("currency" in name.lower() for name in field_names)
                if not has_currency:
                    warnings.append(
                        f"Entity '{entity.name}' field '{field.name}' uses 'decimal' "
                        f"for monetary value without a currency field. "
                        f"Consider using 'money' type or adding a currency field."
                    )

    return errors, warnings


def validate_legal_entity_money_span(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Refuse unpinned money sum/avg that can span a ``legal_entity`` grain (#1675).

    Plant-total numeric (non-money) sums stay legal. A money measure is
    pinned when ``group_by`` is the legal-entity FK, the aggregate
    ``where`` equals that FK, or the workspace ``context_selector`` is
    that entity.
    """
    errors: list[str] = []
    legal_names = {e.name for e in appspec.domain.entities if e.legal_entity}
    if not legal_names:
        return errors, []

    entities = {e.name: e for e in appspec.domain.entities}
    for ws in appspec.workspaces:
        ctx_pins = _context_selector_pins(ws, legal_names)
        for region in ws.regions:
            for metric_name, ref in region.aggregates.items():
                msg = _unpinned_money_span_error(
                    ws, region, metric_name, ref, entities, legal_names, ctx_pins
                )
                if msg:
                    errors.append(msg)
    return errors, []


def _unpinned_money_span_error(
    ws: WorkspaceSpec,
    region: WorkspaceRegion,
    metric_name: str,
    ref: object,
    entities: dict[str, ir.EntitySpec],
    legal_names: set[str],
    ctx_pins: bool,
) -> str | None:
    if isinstance(ref, DerivedMetric) or not isinstance(ref, AggregateRef):
        return None
    if ref.func not in ("sum", "avg"):
        return None
    entity = entities.get(ref.entity or region.source or "")
    if entity is None or not _ref_touches_money(ref, entity):
        return None
    pin_fields = _pin_fields(entity, legal_names)
    if not pin_fields or ctx_pins or _group_by_pins(region, pin_fields):
        return None
    if _where_pins_fk(ref.where, pin_fields):
        return None
    grain = ", ".join(sorted(legal_names))
    pin = sorted(pin_fields)[0]
    return (
        f"Workspace '{ws.name}' region '{region.name}' metric "
        f"'{metric_name}': {ref.func}() of a money field spans "
        f"legal-entity grain {grain}. Pin with group_by: {pin}, "
        f"a where that equals one {grain} row, or "
        f"context_selector on {grain}. Ungrouped numeric "
        f"(non-money) plant totals are allowed."
    )


def _context_selector_pins(ws: WorkspaceSpec, legal_names: set[str]) -> bool:
    sel = ws.context_selector
    return sel is not None and sel.entity in legal_names


def _pin_fields(entity: ir.EntitySpec, legal_names: set[str]) -> set[str]:
    if entity.name in legal_names:
        return {"id"}
    return {
        f.name
        for f in entity.fields
        if f.type.kind == FieldTypeKind.REF and f.type.ref_entity in legal_names
    }


def _group_by_pins(region: WorkspaceRegion, pin_fields: set[str]) -> bool:
    names: list[str] = []
    if isinstance(region.group_by, str):
        names.append(region.group_by)
    if region.group_by_dims:
        names.extend(n for n in region.group_by_dims if isinstance(n, str))
    return bool(pin_fields.intersection(names))


def _where_pins_fk(where: ConditionExpr | None, pin_fields: set[str]) -> bool:
    if where is None:
        return False
    return bool(_eq_fields(where) & pin_fields)


def _eq_fields(expr: ConditionExpr) -> set[str]:
    if expr.is_compound:
        if expr.operator == LogicalOperator.OR:
            return set()
        left = _eq_fields(expr.left) if expr.left is not None else set()
        right = _eq_fields(expr.right) if expr.right is not None else set()
        return left | right
    cmp = expr.comparison
    if cmp is None or cmp.field is None:
        return set()
    if cmp.operator not in (ComparisonOperator.EQUALS, ComparisonOperator.IS):
        return set()
    if cmp.value.is_list:
        return set()
    return {cmp.field.split(".", 1)[0]}


def _ref_touches_money(ref: AggregateRef, entity: ir.EntitySpec) -> bool:
    cols: list[str] = []
    if ref.column:
        cols.append(ref.column)
    if ref.expression is not None:
        cols.extend(_expr_column_names(ref.expression))
    for col in cols:
        field = entity.get_field(col)
        if field is not None and field.type.kind == FieldTypeKind.MONEY:
            return True
    return False


def _expr_column_names(expr: AggregateExpr) -> list[str]:
    if expr.column_name:
        return [expr.column_name]
    names: list[str] = []
    if expr.cast_operand is not None:
        names.extend(_expr_column_names(expr.cast_operand))
    if expr.binary_left is not None:
        names.extend(_expr_column_names(expr.binary_left))
    if expr.binary_right is not None:
        names.extend(_expr_column_names(expr.binary_right))
    if expr.function_args:
        for arg in expr.function_args:
            names.extend(_expr_column_names(arg))
    return names
