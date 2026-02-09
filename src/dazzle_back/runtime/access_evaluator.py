"""
Access rule evaluator with Cedar-style permit/forbid semantics.

Evaluates EntityAccessSpec from BackendSpec at runtime, supporting:
- Cedar three-rule evaluation: FORBID > PERMIT > default-deny
- Role checks: role(admin)
- Persona scoping: restrict rules to specific personas
- Relationship traversal: owner.team_id
- Logical operators: AND/OR
- Comparison operators: =, !=, >, <, >=, <=, in, not in
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from dazzle_back.specs import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
)
from dazzle_back.specs.auth import AccessAuthContext, PermissionRuleSpec

# =============================================================================
# Access Decision
# =============================================================================


class AccessDecision:
    """
    Result of an access evaluation.

    Couples the allow/deny decision with the reason, enabling audit logging.
    """

    __slots__ = ("allowed", "matched_policy", "effect")

    def __init__(
        self,
        allowed: bool,
        matched_policy: str = "",
        effect: str = "",
    ):
        self.allowed = allowed
        self.matched_policy = matched_policy
        self.effect = effect

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"AccessDecision(allowed={self.allowed}, policy={self.matched_policy!r})"


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
    """
    parts = path.split(".")
    current = record

    for part in parts:
        if current is None:
            return None

        if isinstance(current, dict):
            if part in current:
                current = current[part]
            elif f"{part}_id" in current:
                fk_value = current[f"{part}_id"]
                if context.entity_resolver and fk_value:
                    entity_name = part.title()
                    resolved = context.entity_resolver(entity_name, fk_value)
                    current = resolved
                else:
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
        return True

    if "." in field:
        record_value = _resolve_dotted_path(record, field, context)
    else:
        record_value = record.get(field)

    resolved_value = value
    if value == "current_user":
        resolved_value = context.user_id
    elif value == "current_team":
        resolved_value = None

    record_val_str = _normalize_for_comparison(record_value)
    resolved_val_str = _normalize_for_comparison(resolved_value)

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
# Rule Matching
# =============================================================================


def _rule_matches(
    rule: PermissionRuleSpec,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
) -> bool:
    """
    Check if a permission rule matches the current request.

    A rule matches if:
    1. Its operation matches the requested operation
    2. Its persona scope matches (empty = any, otherwise user must have one)
    3. Its auth requirement is met
    4. Its condition evaluates to true against the record
    """
    if rule.operation != operation:
        return False

    # Check persona scope
    if rule.personas:
        if not any(context.has_role(p) for p in rule.personas):
            return False

    # Check auth requirement
    if rule.require_auth and not context.is_authenticated:
        return False

    # If no condition, the rule matches
    if rule.condition is None:
        return True

    # For create operations, handle missing record
    if record is None and operation == AccessOperationKind.CREATE:
        if rule.condition.kind == "role_check":
            return evaluate_access_condition(rule.condition, {}, context)
        return context.is_authenticated

    return evaluate_access_condition(rule.condition, record or {}, context)


def _describe_rule(rule: PermissionRuleSpec) -> str:
    """Generate a human-readable description of a rule for audit logging."""
    parts = [f"{rule.effect.value} {rule.operation.value}"]
    if rule.personas:
        parts.append(f"for [{', '.join(rule.personas)}]")
    if rule.condition:
        parts.append(f"when {rule.condition.kind}")
    return " ".join(parts)


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
    """
    if context.is_superuser:
        return True

    auth_context = (
        AccessAuthContext.AUTHENTICATED if context.is_authenticated else AccessAuthContext.ANONYMOUS
    )

    for rule in access_spec.visibility:
        if rule.context == auth_context:
            return evaluate_access_condition(rule.condition, record, context)

    if access_spec.visibility:
        return False

    return True


# =============================================================================
# Cedar-Style Permission Evaluation
# =============================================================================


def evaluate_permission(
    access_spec: EntityAccessSpec,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
) -> AccessDecision:
    """
    Cedar-style three-rule permission evaluation.

    1. If ANY matching FORBID rule fires -> DENY (return forbid rule description)
    2. If ANY matching PERMIT rule fires -> ALLOW (return permit rule description)
    3. No matching rules -> DENY (default-deny)

    Superusers bypass all checks.

    Args:
        access_spec: Entity access specification
        operation: The operation being attempted
        record: Entity record (None for create operations)
        context: Runtime context with user info

    Returns:
        AccessDecision with allowed flag and matched policy description
    """
    # Superusers bypass all checks
    if context.is_superuser:
        return AccessDecision(
            allowed=True,
            matched_policy="superuser_bypass",
            effect="permit",
        )

    # Collect matching rules
    matching_forbids: list[PermissionRuleSpec] = []
    matching_permits: list[PermissionRuleSpec] = []

    for rule in access_spec.permissions:
        if _rule_matches(rule, operation, record, context):
            if rule.effect == AccessPolicyEffect.FORBID:
                matching_forbids.append(rule)
            else:
                matching_permits.append(rule)

    # Rule 1: Any FORBID match -> DENY
    if matching_forbids:
        rule = matching_forbids[0]
        return AccessDecision(
            allowed=False,
            matched_policy=_describe_rule(rule),
            effect="forbid",
        )

    # Rule 2: Any PERMIT match -> ALLOW
    if matching_permits:
        rule = matching_permits[0]
        return AccessDecision(
            allowed=True,
            matched_policy=_describe_rule(rule),
            effect="permit",
        )

    # Rule 3: No matching rules -> default behavior
    # If there are any rules defined for this entity, default-deny
    if access_spec.permissions:
        return AccessDecision(
            allowed=False,
            matched_policy="default_deny",
            effect="default",
        )

    # No permission rules at all = allow if authenticated (backward compat)
    if operation in (
        AccessOperationKind.CREATE,
        AccessOperationKind.UPDATE,
        AccessOperationKind.DELETE,
    ):
        if context.is_authenticated:
            return AccessDecision(
                allowed=True,
                matched_policy="no_rules_authenticated",
                effect="permit",
            )
        return AccessDecision(
            allowed=False,
            matched_policy="no_rules_unauthenticated",
            effect="default",
        )

    return AccessDecision(
        allowed=True,
        matched_policy="no_rules_default_allow",
        effect="permit",
    )


def evaluate_permission_bool(
    access_spec: EntityAccessSpec,
    operation: AccessOperationKind,
    record: dict[str, Any] | None,
    context: AccessRuntimeContext,
) -> bool:
    """
    Backward-compatible boolean wrapper around evaluate_permission.

    Returns True if operation is permitted, False otherwise.
    """
    return evaluate_permission(access_spec, operation, record, context).allowed


# =============================================================================
# Convenience Functions
# =============================================================================


def can_read(
    access_spec: EntityAccessSpec,
    record: dict[str, Any],
    context: AccessRuntimeContext,
) -> bool:
    """Check if user can read a record (uses visibility rules + READ permissions)."""
    # First check visibility rules (backward compat)
    if not evaluate_visibility(access_spec, record, context):
        return False
    # Also check READ permission rules if any exist
    has_read_rules = any(r.operation == AccessOperationKind.READ for r in access_spec.permissions)
    if has_read_rules:
        return evaluate_permission(access_spec, AccessOperationKind.READ, record, context).allowed
    return True


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
    ).allowed


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
    ).allowed


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
    ).allowed


def filter_visible_records(
    access_spec: EntityAccessSpec,
    records: list[dict[str, Any]],
    context: AccessRuntimeContext,
) -> list[dict[str, Any]]:
    """Filter a list of records to only those visible to user."""
    return [r for r in records if can_read(access_spec, r, context)]
