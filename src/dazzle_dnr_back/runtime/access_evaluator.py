"""
Access rule evaluator for v0.7.0 enhanced access control.

Evaluates EntityAccessSpec from BackendSpec at runtime, supporting:
- Role checks: role(admin)
- Relationship traversal: owner.team_id
- Logical operators: AND/OR
- Comparison operators: =, !=, >, <, >=, <=, in, not in
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from dazzle_dnr_back.specs import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    EntityAccessSpec,
)
from dazzle_dnr_back.specs.auth import AccessAuthContext

# =============================================================================
# Access Runtime Context
# =============================================================================


class AccessRuntimeContext:
    """
    Runtime context for access rule evaluation.

    Provides user identity, roles, and entity resolution for relationship traversal.
    """

    def __init__(
        self,
        user_id: str | UUID | None = None,
        roles: list[str] | None = None,
        is_superuser: bool = False,
        entity_resolver: Any = None,
    ):
        """
        Initialize access context.

        Args:
            user_id: Current user's ID
            roles: List of user's roles
            is_superuser: Whether user is a superuser (bypasses all checks)
            entity_resolver: Callable to resolve related entities by (entity_name, id)
        """
        self.user_id = str(user_id) if user_id else None
        self.roles = set(roles or [])
        self.is_superuser = is_superuser
        self.entity_resolver = entity_resolver

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.user_id is not None

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles or self.is_superuser


# =============================================================================
# Condition Evaluation
# =============================================================================


def _normalize_for_comparison(value: Any) -> str:
    """Normalize a value for comparison (handles UUID, bool, etc.)."""
    if value is None:
        return "None"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _resolve_dotted_path(
    record: dict[str, Any],
    path: str,
    context: AccessRuntimeContext,
) -> Any:
    """
    Resolve a dotted path like 'owner.team_id' to a value.

    For 'owner.team_id':
    1. Get record['owner'] or record['owner_id'] (the foreign key)
    2. Use entity_resolver to fetch the Owner entity
    3. Return owner_record['team_id']

    Args:
        record: Current entity record
        path: Dotted path like 'owner.team_id'
        context: Access context with entity resolver

    Returns:
        The resolved value, or None if not found
    """
    parts = path.split(".")
    current = record

    for part in parts:
        if current is None:
            return None

        if isinstance(current, dict):
            # Direct field access
            if part in current:
                current = current[part]
            # Try with _id suffix for foreign keys
            elif f"{part}_id" in current:
                fk_value = current[f"{part}_id"]
                # Need to resolve the related entity
                if context.entity_resolver and fk_value:
                    # Try to resolve - entity name is typically PascalCase of the field
                    entity_name = part.title()  # "owner" -> "Owner"
                    resolved = context.entity_resolver(entity_name, fk_value)
                    current = resolved
                else:
                    # Can't resolve, return the FK value
                    current = fk_value
            else:
                return None
        else:
            return None

    return current


def _evaluate_comparison_condition(
    condition: AccessConditionSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """
    Evaluate a comparison condition.

    Supports:
    - Simple field comparisons: status = "active"
    - Special values: owner_id = current_user
    - Dotted paths: owner.team_id = current_team
    """
    field = condition.field
    op = condition.comparison_op
    value = condition.value
    value_list = condition.value_list

    if not field or not op:
        return True  # No condition = always true

    # Resolve the field value (may be dotted path)
    if "." in field:
        record_value = _resolve_dotted_path(record, field, context)
    else:
        record_value = record.get(field)

    # Resolve special values
    resolved_value = value
    if value == "current_user":
        resolved_value = context.user_id
    elif value == "current_team":
        # Could be extended for team context
        resolved_value = None

    # Normalize for comparison
    record_val_str = _normalize_for_comparison(record_value)
    resolved_val_str = _normalize_for_comparison(resolved_value)

    # Perform comparison
    if op == AccessComparisonKind.EQUALS:
        return record_val_str == resolved_val_str
    elif op == AccessComparisonKind.NOT_EQUALS:
        return record_val_str != resolved_val_str
    elif op == AccessComparisonKind.GREATER_THAN:
        try:
            if record_value is None or resolved_value is None:
                return False
            return float(record_value) > float(resolved_value)
        except (TypeError, ValueError):
            return False
    elif op == AccessComparisonKind.LESS_THAN:
        try:
            if record_value is None or resolved_value is None:
                return False
            return float(record_value) < float(resolved_value)
        except (TypeError, ValueError):
            return False
    elif op == AccessComparisonKind.GREATER_EQUAL:
        try:
            if record_value is None or resolved_value is None:
                return False
            return float(record_value) >= float(resolved_value)
        except (TypeError, ValueError):
            return False
    elif op == AccessComparisonKind.LESS_EQUAL:
        try:
            if record_value is None or resolved_value is None:
                return False
            return float(record_value) <= float(resolved_value)
        except (TypeError, ValueError):
            return False
    elif op == AccessComparisonKind.IN:
        if value_list:
            normalized_list = [_normalize_for_comparison(v) for v in value_list]
            return record_val_str in normalized_list
        return False
    elif op == AccessComparisonKind.NOT_IN:
        if value_list:
            normalized_list = [_normalize_for_comparison(v) for v in value_list]
            return record_val_str not in normalized_list
        return True
    elif op == AccessComparisonKind.IS:
        # IS is typically for null checks
        if resolved_value is None:
            return record_value is None
        return bool(record_value == resolved_value)
    elif op == AccessComparisonKind.IS_NOT:
        if resolved_value is None:
            return record_value is not None
        return bool(record_value != resolved_value)

    return False


def evaluate_access_condition(
    condition: AccessConditionSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """
    Evaluate an AccessConditionSpec against a record.

    Handles:
    - comparison: field op value
    - role_check: role(name)
    - logical: left AND/OR right

    Args:
        condition: The condition to evaluate
        record: Entity record to check against
        context: Runtime context with user info

    Returns:
        True if condition is satisfied
    """
    if condition.kind == "comparison":
        return _evaluate_comparison_condition(condition, record, context)

    elif condition.kind == "role_check":
        role_name = condition.role_name
        if role_name:
            return context.has_role(role_name)
        return False

    elif condition.kind == "logical":
        left_result = True
        right_result = True

        if condition.logical_left:
            left_result = evaluate_access_condition(condition.logical_left, record, context)

        if condition.logical_right:
            right_result = evaluate_access_condition(condition.logical_right, record, context)

        if condition.logical_op == AccessLogicalKind.AND:
            return left_result and right_result
        elif condition.logical_op == AccessLogicalKind.OR:
            return left_result or right_result

    return True  # Unknown condition type = allow


# =============================================================================
# Visibility Evaluation
# =============================================================================


def evaluate_visibility(
    access_spec: EntityAccessSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """
    Evaluate if a record is visible to the user.

    Checks visibility rules based on authentication context.

    Args:
        access_spec: Entity access specification
        record: Entity record to check
        context: Runtime context with user info

    Returns:
        True if record is visible to user
    """
    # Superusers can see everything
    if context.is_superuser:
        return True

    # Determine auth context
    auth_context = (
        AccessAuthContext.AUTHENTICATED if context.is_authenticated else AccessAuthContext.ANONYMOUS
    )

    # Find matching visibility rule
    for rule in access_spec.visibility:
        if rule.context == auth_context:
            return evaluate_access_condition(rule.condition, record, context)

    # No matching rule - check if any rule exists
    # If there are visibility rules but none match, deny access
    if access_spec.visibility:
        return False

    # No visibility rules = public access
    return True


# =============================================================================
# Permission Evaluation
# =============================================================================


def evaluate_permission(
    access_spec: EntityAccessSpec,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
) -> bool:
    """
    Evaluate if user has permission for an operation.

    Args:
        access_spec: Entity access specification
        operation: The operation being attempted
        record: Entity record (None for create operations)
        context: Runtime context with user info

    Returns:
        True if operation is permitted
    """
    # Superusers can do anything
    if context.is_superuser:
        return True

    # Find matching permission rule
    for rule in access_spec.permissions:
        if rule.operation == operation:
            # Check if authentication is required
            if rule.require_auth and not context.is_authenticated:
                return False

            # If no condition, just auth requirement matters
            if rule.condition is None:
                return True

            # Evaluate condition
            # For create, we may not have a record yet
            if record is None and operation == AccessOperationKind.CREATE:
                # For create, conditions are evaluated differently
                # Most conditions can't be checked without a record
                # Role checks can still be evaluated
                if rule.condition.kind == "role_check":
                    return evaluate_access_condition(rule.condition, {}, context)
                # For other conditions on create, allow if authenticated
                return context.is_authenticated

            return evaluate_access_condition(rule.condition, record or {}, context)

    # No matching rule - check if there are any permission rules
    if access_spec.permissions:
        # If there are rules but none for this operation, deny
        return False

    # No permission rules = allow if authenticated (for write operations)
    if operation in (
        AccessOperationKind.CREATE,
        AccessOperationKind.UPDATE,
        AccessOperationKind.DELETE,
    ):
        return context.is_authenticated

    return True


# =============================================================================
# Convenience Functions
# =============================================================================


def can_read(
    access_spec: EntityAccessSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """Check if user can read a record."""
    return evaluate_visibility(access_spec, record, context)


def can_create(
    access_spec: EntityAccessSpec,
    context: AccessRuntimeContext,
) -> bool:
    """Check if user can create a new record."""
    return evaluate_permission(
        access_spec,
        AccessOperationKind.CREATE,
        None,
        context,
    )


def can_update(
    access_spec: EntityAccessSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """Check if user can update a record."""
    return evaluate_permission(
        access_spec,
        AccessOperationKind.UPDATE,
        record,
        context,
    )


def can_delete(
    access_spec: EntityAccessSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """Check if user can delete a record."""
    return evaluate_permission(
        access_spec,
        AccessOperationKind.DELETE,
        record,
        context,
    )


def filter_visible_records(
    access_spec: EntityAccessSpec,
    records: list[dict[str, Any]],
    context: AccessRuntimeContext,
) -> list[dict[str, Any]]:
    """
    Filter a list of records to only those visible to user.

    Args:
        access_spec: Entity access specification
        records: List of entity records
        context: Runtime context with user info

    Returns:
        Filtered list of visible records
    """
    return [r for r in records if can_read(access_spec, r, context)]
