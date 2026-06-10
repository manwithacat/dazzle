"""Shared condition-expression helpers used across validation modules.

Split verbatim from dazzle.core.validator per #1361.
"""

from typing import Any

from .. import ir


def _validate_condition_fields(
    condition: ir.ConditionExpr,
    entity: ir.EntitySpec | None,
    context: str,
    appspec: ir.AppSpec | None = None,
) -> list[str]:
    """
    Validate that condition expression references valid entity fields.

    Supports FK traversal: ``assessment_event.department`` resolves
    ``assessment_event`` as a ref field on *entity*, then checks
    ``department`` exists on the referenced entity. Multi-hop paths
    like ``mark_scheme.subject.department`` are also supported.

    Args:
        condition: The condition expression to validate
        entity: The entity to validate fields against (may be None)
        context: Context string for error messages
        appspec: Full app spec, needed to resolve FK traversal paths

    Returns:
        List of error messages
    """
    errors: list[str] = []

    if not entity:
        return errors

    entity_field_names = {f.name for f in entity.fields}
    entity_fields_by_name = {f.name: f for f in entity.fields}

    def _resolve_fk_path(field_path: str) -> str | None:
        """Resolve a dotted FK path. Returns an error message or None if valid."""
        parts = field_path.split(".")
        current_entity = entity
        current_fields = entity_fields_by_name

        for i, part in enumerate(parts):
            if part not in current_fields:
                source = current_entity.name if current_entity else "?"
                return (
                    f"{context} references non-existent field '{field_path}' from entity '{source}'"
                )

            # If there are more segments, this part must be a ref field
            if i < len(parts) - 1:
                field_spec = current_fields[part]
                if field_spec.type.kind != ir.FieldTypeKind.REF or not field_spec.type.ref_entity:
                    return (
                        f"{context} field '{'.'.join(parts[: i + 1])}' is not a "
                        f"reference field on entity '{current_entity.name if current_entity else '?'}', "
                        f"cannot traverse to '{'.'.join(parts[i + 1 :])}'"
                    )
                if not appspec:
                    return None  # Can't resolve further without appspec; assume valid
                ref_entity = appspec.get_entity(field_spec.type.ref_entity)
                if not ref_entity:
                    return (
                        f"{context} field '{'.'.join(parts[: i + 1])}' references "
                        f"entity '{field_spec.type.ref_entity}' which does not exist"
                    )
                current_entity = ref_entity
                current_fields = {f.name: f for f in ref_entity.fields}

        return None  # Valid

    def check_comparison(comparison: ir.Comparison) -> None:
        """Validate field references in a comparison expression."""
        if comparison.field:
            if "." in comparison.field:
                err = _resolve_fk_path(comparison.field)
                if err:
                    errors.append(err)
            elif comparison.field not in entity_field_names:
                errors.append(
                    f"{context} references non-existent field '{comparison.field}' "
                    f"from entity '{entity.name}'"
                )
        if comparison.function and comparison.function.argument not in entity_field_names:
            errors.append(
                f"{context} function '{comparison.function.name}' references "
                f"non-existent field '{comparison.function.argument}' from entity '{entity.name}'"
            )

    def check_condition(cond: ir.ConditionExpr) -> None:
        """Recursively validate a condition expression tree."""
        if cond.comparison:
            check_comparison(cond.comparison)
        elif cond.is_compound:
            if cond.left:
                check_condition(cond.left)
            if cond.right:
                check_condition(cond.right)

    check_condition(condition)
    return errors


def _condition_field_references(condition: Any) -> set[str]:
    """Collect every entity field name referenced by a ConditionExpr tree.

    Walks Comparison.field plus FunctionCall.argument on leaves and
    recurses through compound `left`/`right` branches.
    """
    if condition is None:
        return set()
    refs: set[str] = set()
    comparison = getattr(condition, "comparison", None)
    if comparison is not None:
        if comparison.field:
            refs.add(comparison.field)
        if comparison.function and comparison.function.argument:
            refs.add(comparison.function.argument)
    left = getattr(condition, "left", None)
    right = getattr(condition, "right", None)
    if left is not None:
        refs.update(_condition_field_references(left))
    if right is not None:
        refs.update(_condition_field_references(right))
    return refs


# =============================================================================
# Validator hardening — closes #1061
# =============================================================================
#
# Four blindspots that `dazzle validate` silently allowed before #1061:
#   1. `role(<name>)` in permit clauses that doesn't match any User.role
#      enum value (dead permissions — never matches any user).
#   2. `tenancy.partition_key` naming a field that no entity declares
#      (multi-tenancy silently broken).
#   3. Service refs inside `process` step `service:` clauses that don't
#      resolve to a declared `domain_service`.
#   4. RBAC matrix `PolicyWarning`s (redundant_forbid, orphan_role) that
#      `generate_access_matrix` produces but no validator surfaced.
#
# All four are warnings (not errors) so existing CI stays green; promote
# to errors in a future minor once downstream apps have absorbed them.


def _walk_role_names(condition: Any) -> set[str]:
    """Recursively collect role names from a ConditionExpr tree."""
    if condition is None:
        return set()
    roles: set[str] = set()
    if condition.role_check is not None:
        roles.add(condition.role_check.role_name)
    if condition.is_compound:
        roles.update(_walk_role_names(condition.left))
        roles.update(_walk_role_names(condition.right))
    return roles
