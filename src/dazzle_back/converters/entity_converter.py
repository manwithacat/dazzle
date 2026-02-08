"""
Entity converter - converts Dazzle IR EntitySpec to DNR BackendSpec EntitySpec.

This module handles the transformation of Dazzle's domain entities into
DNR's framework-agnostic BackendSpec format.
"""

from dazzle.core import ir
from dazzle_back.specs import (
    AccessAuthContext,
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AggregateFunctionKind,
    ArithmeticOperatorKind,
    AutoTransitionSpec,
    ComputedExprSpec,
    ComputedFieldSpec,
    DurationUnitKind,
    EntityAccessSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
    PermissionRuleSpec,
    RelationKind,
    RelationSpec,
    ScalarType,
    StateMachineSpec,
    StateTransitionSpec,
    TimeUnit,
    TransitionGuardSpec,
    TransitionTrigger,
    ValidatorKind,
    ValidatorSpec,
    VisibilityRuleSpec,
)

# =============================================================================
# Type Mapping
# =============================================================================


def _map_field_type(dazzle_type: ir.FieldType) -> FieldType:
    """
    Map Dazzle IR FieldType to DNR BackendSpec FieldType.

    Handles scalar types, enums, and references.
    """
    kind = dazzle_type.kind

    # Map scalar types
    scalar_map = {
        ir.FieldTypeKind.STR: ScalarType.STR,
        ir.FieldTypeKind.TEXT: ScalarType.TEXT,
        ir.FieldTypeKind.INT: ScalarType.INT,
        ir.FieldTypeKind.DECIMAL: ScalarType.DECIMAL,
        ir.FieldTypeKind.BOOL: ScalarType.BOOL,
        ir.FieldTypeKind.DATE: ScalarType.DATE,
        ir.FieldTypeKind.DATETIME: ScalarType.DATETIME,
        ir.FieldTypeKind.UUID: ScalarType.UUID,
        ir.FieldTypeKind.EMAIL: ScalarType.EMAIL,
        ir.FieldTypeKind.JSON: ScalarType.JSON,  # v0.9.4
        ir.FieldTypeKind.TIMEZONE: ScalarType.TIMEZONE,  # v0.10.3
    }

    if kind == ir.FieldTypeKind.ENUM:
        # Enum type
        return FieldType(
            kind="enum",
            enum_values=dazzle_type.enum_values or [],
        )
    elif kind == ir.FieldTypeKind.REF:
        # Reference type
        return FieldType(
            kind="ref",
            ref_entity=dazzle_type.ref_entity,
        )
    elif kind in scalar_map:
        # Scalar type
        return FieldType(
            kind="scalar",
            scalar_type=scalar_map[kind],
            max_length=dazzle_type.max_length,
            precision=dazzle_type.precision,
            scale=dazzle_type.scale,
        )
    else:
        # Default to string for unknown types
        return FieldType(kind="scalar", scalar_type=ScalarType.STR)


def _extract_validators(field: ir.FieldSpec) -> list[ValidatorSpec]:
    """
    Extract validators from field modifiers and type constraints.
    """
    validators: list[ValidatorSpec] = []

    # Add validators based on field type
    if field.type.kind == ir.FieldTypeKind.EMAIL:
        validators.append(ValidatorSpec(kind=ValidatorKind.EMAIL))

    # Add max_length validator for string types
    if field.type.max_length:
        validators.append(ValidatorSpec(kind=ValidatorKind.MAX_LENGTH, value=field.type.max_length))

    # Add precision/scale for decimal (not validators, but useful metadata)
    # These would be handled by the type itself

    return validators


# =============================================================================
# Field Conversion
# =============================================================================


def _serialize_date_expr(default: object) -> object:
    """
    Serialize a date expression to a dictionary format for runtime evaluation.

    Handles:
        - DateLiteral (today, now) -> {"kind": "today"} or {"kind": "now"}
        - DateArithmeticExpr -> {"kind": "today", "op": "+", "value": 7, "unit": "days"}
        - Scalar values pass through unchanged

    v0.10.2: Added for date arithmetic field defaults.
    """
    if isinstance(default, ir.DateLiteral):
        return {"kind": default.kind.value}
    elif isinstance(default, ir.DateArithmeticExpr):
        # Get base kind from left operand
        if isinstance(default.left, ir.DateLiteral):
            base_kind = default.left.kind.value
        else:
            # Field reference (string) - not yet supported as base
            base_kind = str(default.left)

        return {
            "kind": base_kind,
            "op": default.operator.value,
            "value": default.right.value,
            "unit": default.right.unit.value,
        }
    else:
        # Scalar value - pass through
        return default


def _expand_money_field(dazzle_field: ir.FieldSpec) -> list[FieldSpec]:
    """Expand a money field into _minor (INT) and _currency (STR) column pair.

    Args:
        dazzle_field: Dazzle IR field with kind=MONEY.

    Returns:
        Two FieldSpecs: {name}_minor as INT, {name}_currency as STR(3).
    """
    currency_code = dazzle_field.type.currency_code or "GBP"
    base_name = dazzle_field.name
    is_required = dazzle_field.is_required

    minor_field = FieldSpec(
        name=f"{base_name}_minor",
        label=f"{base_name.replace('_', ' ').title()} (Minor Units)",
        type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
        required=is_required,
        default=None,
        validators=[],
        indexed=dazzle_field.is_primary_key,
        unique=dazzle_field.is_unique,
        auto_add=ir.FieldModifier.AUTO_ADD in dazzle_field.modifiers,
        auto_update=ir.FieldModifier.AUTO_UPDATE in dazzle_field.modifiers,
    )

    currency_field = FieldSpec(
        name=f"{base_name}_currency",
        label=f"{base_name.replace('_', ' ').title()} Currency",
        type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=3),
        required=False,
        default=currency_code,
        validators=[ValidatorSpec(kind=ValidatorKind.MAX_LENGTH, value=3)],
        indexed=False,
        unique=False,
        auto_add=False,
        auto_update=False,
    )

    return [minor_field, currency_field]


def convert_field(dazzle_field: ir.FieldSpec) -> FieldSpec:
    """
    Convert a Dazzle IR FieldSpec to DNR BackendSpec FieldSpec.

    Args:
        dazzle_field: Dazzle IR field specification

    Returns:
        DNR BackendSpec field specification
    """
    # Serialize default value, handling date expressions
    default = _serialize_date_expr(dazzle_field.default)

    return FieldSpec(
        name=dazzle_field.name,
        label=dazzle_field.name.replace("_", " ").title(),
        type=_map_field_type(dazzle_field.type),
        required=dazzle_field.is_required or dazzle_field.is_primary_key,
        default=default,
        validators=_extract_validators(dazzle_field),
        indexed=dazzle_field.is_primary_key,
        unique=dazzle_field.is_unique or dazzle_field.is_primary_key,
        auto_add=ir.FieldModifier.AUTO_ADD in dazzle_field.modifiers,
        auto_update=ir.FieldModifier.AUTO_UPDATE in dazzle_field.modifiers,
    )


# =============================================================================
# State Machine Conversion
# =============================================================================


def _convert_time_unit(ir_unit: ir.TimeUnit) -> TimeUnit:
    """Map IR TimeUnit to BackendSpec TimeUnit."""
    mapping = {
        ir.TimeUnit.MINUTES: TimeUnit.MINUTES,
        ir.TimeUnit.HOURS: TimeUnit.HOURS,
        ir.TimeUnit.DAYS: TimeUnit.DAYS,
    }
    return mapping[ir_unit]


def _convert_trigger(ir_trigger: ir.TransitionTrigger) -> TransitionTrigger:
    """Map IR TransitionTrigger to BackendSpec TransitionTrigger."""
    mapping = {
        ir.TransitionTrigger.MANUAL: TransitionTrigger.MANUAL,
        ir.TransitionTrigger.AUTO: TransitionTrigger.AUTO,
    }
    return mapping[ir_trigger]


def _convert_guard(ir_guard: ir.TransitionGuard) -> TransitionGuardSpec:
    """Convert IR TransitionGuard to BackendSpec TransitionGuardSpec."""
    return TransitionGuardSpec(
        requires_field=ir_guard.requires_field,
        requires_role=ir_guard.requires_role,
    )


def _convert_auto_spec(ir_auto: ir.AutoTransitionSpec) -> AutoTransitionSpec:
    """Convert IR AutoTransitionSpec to BackendSpec AutoTransitionSpec."""
    return AutoTransitionSpec(
        delay_value=ir_auto.delay_value,
        delay_unit=_convert_time_unit(ir_auto.delay_unit),
        allow_manual=ir_auto.allow_manual,
    )


def _convert_transition(ir_trans: ir.StateTransition) -> StateTransitionSpec:
    """Convert IR StateTransition to BackendSpec StateTransitionSpec."""
    return StateTransitionSpec(
        from_state=ir_trans.from_state,
        to_state=ir_trans.to_state,
        trigger=_convert_trigger(ir_trans.trigger),
        guards=[_convert_guard(g) for g in ir_trans.guards],
        auto_spec=_convert_auto_spec(ir_trans.auto_spec) if ir_trans.auto_spec else None,
    )


def _convert_state_machine(ir_sm: ir.StateMachineSpec) -> StateMachineSpec:
    """Convert IR StateMachineSpec to BackendSpec StateMachineSpec."""
    return StateMachineSpec(
        status_field=ir_sm.status_field,
        states=ir_sm.states,
        transitions=[_convert_transition(t) for t in ir_sm.transitions],
    )


# =============================================================================
# Computed Field Conversion
# =============================================================================


def _convert_aggregate_function(func: ir.AggregateFunction) -> AggregateFunctionKind:
    """Map IR AggregateFunction to BackendSpec AggregateFunctionKind."""
    mapping = {
        ir.AggregateFunction.COUNT: AggregateFunctionKind.COUNT,
        ir.AggregateFunction.SUM: AggregateFunctionKind.SUM,
        ir.AggregateFunction.AVG: AggregateFunctionKind.AVG,
        ir.AggregateFunction.MIN: AggregateFunctionKind.MIN,
        ir.AggregateFunction.MAX: AggregateFunctionKind.MAX,
        ir.AggregateFunction.DAYS_UNTIL: AggregateFunctionKind.DAYS_UNTIL,
        ir.AggregateFunction.DAYS_SINCE: AggregateFunctionKind.DAYS_SINCE,
    }
    return mapping[func]


def _convert_arithmetic_operator(op: ir.ArithmeticOperator) -> ArithmeticOperatorKind:
    """Map IR ArithmeticOperator to BackendSpec ArithmeticOperatorKind."""
    mapping = {
        ir.ArithmeticOperator.ADD: ArithmeticOperatorKind.ADD,
        ir.ArithmeticOperator.SUBTRACT: ArithmeticOperatorKind.SUBTRACT,
        ir.ArithmeticOperator.MULTIPLY: ArithmeticOperatorKind.MULTIPLY,
        ir.ArithmeticOperator.DIVIDE: ArithmeticOperatorKind.DIVIDE,
    }
    return mapping[op]


def _convert_computed_expr(expr: ir.ComputedExpr) -> ComputedExprSpec:
    """Convert IR ComputedExpr to BackendSpec ComputedExprSpec."""
    if isinstance(expr, ir.FieldReference):
        return ComputedExprSpec(
            kind="field_ref",
            path=expr.path,
        )
    elif isinstance(expr, ir.AggregateCall):
        return ComputedExprSpec(
            kind="aggregate",
            function=_convert_aggregate_function(expr.function),
            field=ComputedExprSpec(kind="field_ref", path=expr.field.path),
        )
    elif isinstance(expr, ir.ArithmeticExpr):
        return ComputedExprSpec(
            kind="arithmetic",
            left=_convert_computed_expr(expr.left),
            operator=_convert_arithmetic_operator(expr.operator),
            right=_convert_computed_expr(expr.right),
        )
    elif isinstance(expr, ir.LiteralValue):
        return ComputedExprSpec(
            kind="literal",
            value=expr.value,
        )
    else:
        raise ValueError(f"Unknown computed expression type: {type(expr)}")


def _convert_computed_field(cf: ir.ComputedFieldSpec) -> ComputedFieldSpec:
    """Convert IR ComputedFieldSpec to BackendSpec ComputedFieldSpec."""
    return ComputedFieldSpec(
        name=cf.name,
        expression=_convert_computed_expr(cf.expression),
    )


# =============================================================================
# Invariant Conversion
# =============================================================================


def _convert_comparison_operator(op: ir.InvariantComparisonOperator) -> InvariantComparisonKind:
    """Map IR InvariantComparisonOperator to BackendSpec InvariantComparisonKind."""
    mapping = {
        ir.InvariantComparisonOperator.EQ: InvariantComparisonKind.EQ,
        ir.InvariantComparisonOperator.NE: InvariantComparisonKind.NE,
        ir.InvariantComparisonOperator.GT: InvariantComparisonKind.GT,
        ir.InvariantComparisonOperator.LT: InvariantComparisonKind.LT,
        ir.InvariantComparisonOperator.GE: InvariantComparisonKind.GE,
        ir.InvariantComparisonOperator.LE: InvariantComparisonKind.LE,
    }
    return mapping[op]


def _convert_logical_operator(op: ir.InvariantLogicalOperator) -> InvariantLogicalKind:
    """Map IR InvariantLogicalOperator to BackendSpec InvariantLogicalKind."""
    mapping = {
        ir.InvariantLogicalOperator.AND: InvariantLogicalKind.AND,
        ir.InvariantLogicalOperator.OR: InvariantLogicalKind.OR,
    }
    return mapping[op]


def _convert_duration_unit(unit: ir.DurationUnit) -> DurationUnitKind:
    """Map IR DurationUnit to BackendSpec DurationUnitKind."""
    mapping = {
        ir.DurationUnit.MINUTES: DurationUnitKind.MINUTES,
        ir.DurationUnit.HOURS: DurationUnitKind.HOURS,
        ir.DurationUnit.DAYS: DurationUnitKind.DAYS,
        ir.DurationUnit.WEEKS: DurationUnitKind.WEEKS,  # v0.10.2
        ir.DurationUnit.MONTHS: DurationUnitKind.MONTHS,  # v0.10.2
        ir.DurationUnit.YEARS: DurationUnitKind.YEARS,  # v0.10.2
    }
    return mapping[unit]


def _convert_invariant_expr(expr: ir.InvariantExpr) -> InvariantExprSpec:
    """Convert IR InvariantExpr to BackendSpec InvariantExprSpec."""
    if isinstance(expr, ir.InvariantFieldRef):
        return InvariantExprSpec(
            kind="field_ref",
            path=expr.path,
        )
    elif isinstance(expr, ir.InvariantLiteral):
        return InvariantExprSpec(
            kind="literal",
            value=expr.value,
        )
    elif isinstance(expr, ir.DurationExpr):
        return InvariantExprSpec(
            kind="duration",
            duration_value=expr.value,
            duration_unit=_convert_duration_unit(expr.unit),
        )
    elif isinstance(expr, ir.ComparisonExpr):
        return InvariantExprSpec(
            kind="comparison",
            comparison_left=_convert_invariant_expr(expr.left),
            comparison_op=_convert_comparison_operator(expr.operator),
            comparison_right=_convert_invariant_expr(expr.right),
        )
    elif isinstance(expr, ir.LogicalExpr):
        return InvariantExprSpec(
            kind="logical",
            logical_left=_convert_invariant_expr(expr.left),
            logical_op=_convert_logical_operator(expr.operator),
            logical_right=_convert_invariant_expr(expr.right),
        )
    elif isinstance(expr, ir.NotExpr):
        return InvariantExprSpec(
            kind="not",
            not_operand=_convert_invariant_expr(expr.operand),
        )
    else:
        raise ValueError(f"Unknown invariant expression type: {type(expr)}")


def _convert_invariant(inv: ir.InvariantSpec) -> InvariantSpec:
    """Convert IR InvariantSpec to BackendSpec InvariantSpec."""
    return InvariantSpec(
        expression=_convert_invariant_expr(inv.expression),
        message=inv.message,
    )


# =============================================================================
# Access Rules Conversion (v0.7.0)
# =============================================================================


def _convert_access_condition(cond: ir.ConditionExpr) -> AccessConditionSpec:
    """Convert IR ConditionExpr to BackendSpec AccessConditionSpec."""
    # Role check condition
    if cond.role_check is not None:
        return AccessConditionSpec(
            kind="role_check",
            role_name=cond.role_check.role_name,
        )

    # Simple comparison condition
    if cond.comparison is not None:
        comp = cond.comparison

        # Map comparison operators
        op_map = {
            ir.ComparisonOperator.EQUALS: AccessComparisonKind.EQUALS,
            ir.ComparisonOperator.NOT_EQUALS: AccessComparisonKind.NOT_EQUALS,
            ir.ComparisonOperator.GREATER_THAN: AccessComparisonKind.GREATER_THAN,
            ir.ComparisonOperator.LESS_THAN: AccessComparisonKind.LESS_THAN,
            ir.ComparisonOperator.GREATER_EQUAL: AccessComparisonKind.GREATER_EQUAL,
            ir.ComparisonOperator.LESS_EQUAL: AccessComparisonKind.LESS_EQUAL,
            ir.ComparisonOperator.IN: AccessComparisonKind.IN,
            ir.ComparisonOperator.NOT_IN: AccessComparisonKind.NOT_IN,
            ir.ComparisonOperator.IS: AccessComparisonKind.IS,
            ir.ComparisonOperator.IS_NOT: AccessComparisonKind.IS_NOT,
        }

        # Get value from ConditionValue
        value = comp.value.literal
        value_list = comp.value.values

        return AccessConditionSpec(
            kind="comparison",
            field=comp.field,
            comparison_op=op_map[comp.operator],
            value=value,
            value_list=value_list,
        )

    # Compound logical condition
    if cond.operator is not None and cond.left is not None and cond.right is not None:
        logical_op_map = {
            ir.LogicalOperator.AND: AccessLogicalKind.AND,
            ir.LogicalOperator.OR: AccessLogicalKind.OR,
        }
        return AccessConditionSpec(
            kind="logical",
            logical_op=logical_op_map[cond.operator],
            logical_left=_convert_access_condition(cond.left),
            logical_right=_convert_access_condition(cond.right),
        )

    raise ValueError("Invalid ConditionExpr: no comparison, role_check, or logical operator")


def _convert_visibility_rule(rule: ir.VisibilityRule) -> VisibilityRuleSpec:
    """Convert IR VisibilityRule to BackendSpec VisibilityRuleSpec."""
    context_map = {
        ir.AuthContext.ANONYMOUS: AccessAuthContext.ANONYMOUS,
        ir.AuthContext.AUTHENTICATED: AccessAuthContext.AUTHENTICATED,
    }
    return VisibilityRuleSpec(
        context=context_map[rule.context],
        condition=_convert_access_condition(rule.condition),
    )


def _convert_permission_rule(rule: ir.PermissionRule) -> PermissionRuleSpec:
    """Convert IR PermissionRule to BackendSpec PermissionRuleSpec."""
    op_map = {
        ir.PermissionKind.CREATE: AccessOperationKind.CREATE,
        ir.PermissionKind.UPDATE: AccessOperationKind.UPDATE,
        ir.PermissionKind.DELETE: AccessOperationKind.DELETE,
    }
    return PermissionRuleSpec(
        operation=op_map[rule.operation],
        require_auth=rule.require_auth,
        condition=_convert_access_condition(rule.condition) if rule.condition else None,
    )


def _convert_access_spec(access: ir.AccessSpec) -> EntityAccessSpec:
    """Convert IR AccessSpec to BackendSpec EntityAccessSpec."""
    return EntityAccessSpec(
        visibility=[_convert_visibility_rule(v) for v in access.visibility],
        permissions=[_convert_permission_rule(p) for p in access.permissions],
    )


# =============================================================================
# Entity Conversion
# =============================================================================


def convert_entity(dazzle_entity: ir.EntitySpec) -> EntitySpec:
    """
    Convert a Dazzle IR EntitySpec to DNR BackendSpec EntitySpec.

    Args:
        dazzle_entity: Dazzle IR entity specification

    Returns:
        DNR BackendSpec entity specification
    """
    # Convert fields, expanding money fields into _minor/_currency pairs
    fields: list[FieldSpec] = []
    for f in dazzle_entity.fields:
        if f.type.kind == ir.FieldTypeKind.MONEY:
            fields.extend(_expand_money_field(f))
        else:
            fields.append(convert_field(f))

    # Note: Relations are inferred from ref fields
    # In a real implementation, we'd need more sophisticated relation detection
    relations: list[RelationSpec] = []

    # Extract relations from ref fields
    for field in dazzle_entity.fields:
        if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
            relations.append(
                RelationSpec(
                    name=field.name,
                    from_entity=dazzle_entity.name,
                    to_entity=field.type.ref_entity,
                    kind=RelationKind.MANY_TO_ONE,  # Assume many-to-one for ref fields
                    required=field.is_required,
                )
            )

    # Build metadata
    metadata: dict[str, object] = {}

    # Convert access rules if present (v0.7.0)
    access: EntityAccessSpec | None = None
    if dazzle_entity.access:
        access = _convert_access_spec(dazzle_entity.access)

    # Convert state machine if present
    state_machine: StateMachineSpec | None = None
    if dazzle_entity.state_machine:
        state_machine = _convert_state_machine(dazzle_entity.state_machine)

    # Convert computed fields if present
    computed_fields: list[ComputedFieldSpec] = []
    if dazzle_entity.computed_fields:
        computed_fields = [_convert_computed_field(cf) for cf in dazzle_entity.computed_fields]

    # Convert invariants if present
    invariants: list[InvariantSpec] = []
    if dazzle_entity.invariants:
        invariants = [_convert_invariant(inv) for inv in dazzle_entity.invariants]

    return EntitySpec(
        name=dazzle_entity.name,
        label=dazzle_entity.title or dazzle_entity.name,
        description=dazzle_entity.title,
        fields=fields,
        computed_fields=computed_fields,
        invariants=invariants,
        relations=relations,
        state_machine=state_machine,
        access=access,
        is_singleton=dazzle_entity.is_singleton,  # v0.10.3
        is_tenant_root=dazzle_entity.is_tenant_root,  # v0.10.3
        metadata=metadata,
    )


def convert_entities(
    dazzle_entities: list[ir.EntitySpec],
) -> list[EntitySpec]:
    """
    Convert a list of Dazzle IR entities to DNR BackendSpec entities.

    Args:
        dazzle_entities: List of Dazzle IR entity specifications

    Returns:
        List of DNR BackendSpec entity specifications
    """
    return [convert_entity(e) for e in dazzle_entities]
