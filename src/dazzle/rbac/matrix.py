"""Static access matrix generator — Layer 1 of the RBAC verification framework.

Given a parsed AppSpec, generates the complete access matrix: for every
(role, entity, operation), determines whether access is PERMIT, DENY,
PERMIT_FILTERED, or PERMIT_UNPROTECTED.

Cedar semantics:
  - FORBID overrides PERMIT (forbid > permit > default-deny)
  - Default with no matching rule → DENY
  - No rules at all on entity → PERMIT_UNPROTECTED (backward-compat warning)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from enum import StrEnum

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.conditions import ConditionExpr
from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule, PolicyEffect


class PolicyDecision(StrEnum):
    """The resolved access decision for a (role, entity, operation) triple."""

    PERMIT = "PERMIT"
    """Access granted via a pure role gate — no row-level filter."""

    DENY = "DENY"
    """Access denied — either no matching permit rule or an explicit forbid."""

    PERMIT_FILTERED = "PERMIT_FILTERED"
    """Access granted but rows are filtered by a field-level condition."""

    PERMIT_UNPROTECTED = "PERMIT_UNPROTECTED"
    """No access rules defined at all — backward-compat open access."""


@dataclass(frozen=True)
class PolicyWarning:
    """A diagnostic emitted during matrix generation."""

    kind: str
    """Machine-readable warning category."""

    entity: str
    """Entity name the warning relates to."""

    role: str
    """Role name the warning relates to (may be '*' for entity-level warnings)."""

    operation: str
    """Operation name the warning relates to (may be '*' for entity-level warnings)."""

    message: str
    """Human-readable description."""


# Canonical operation list — order matters for table rendering.
OPERATIONS: list[str] = ["list", "read", "create", "update", "delete"]

# Map PermissionKind string values to our canonical op names.
_OPERATION_NAMES: dict[str, str] = {
    PermissionKind.LIST: "list",
    PermissionKind.READ: "read",
    PermissionKind.CREATE: "create",
    PermissionKind.UPDATE: "update",
    PermissionKind.DELETE: "delete",
}


def _condition_has_field_filter(condition: ConditionExpr | None) -> bool:
    """Return True if the condition includes any field comparison (row-level filter).

    Pure role checks (role_check nodes) do NOT make it filtered — they are
    still a gate, not a filter.  Grant checks are treated as field-filtered
    because they scope access by a relationship field.
    """
    if condition is None:
        return False

    # Grant checks are runtime-evaluated and scope to a relationship field.
    if condition.grant_check is not None:
        return True

    # A plain comparison is a field filter.
    if condition.comparison is not None:
        return True

    # Pure role check — not a filter.
    if condition.role_check is not None:
        return False

    # Compound: filtered if either side is filtered.
    if condition.is_compound:
        return _condition_has_field_filter(condition.left) or _condition_has_field_filter(
            condition.right
        )

    return False


def _condition_is_pure_role(condition: ConditionExpr | None, role: str) -> bool:
    """Return True if condition is purely a role check matching *role*."""
    if condition is None:
        return False
    if condition.role_check is not None:
        return condition.role_check.role_name == role
    return False


def _condition_matches_role(condition: ConditionExpr | None, role: str) -> bool:
    """Return True if condition contains a role check matching *role* anywhere.

    Walks compound expressions recursively.
    """
    if condition is None:
        return False
    if condition.role_check is not None:
        return condition.role_check.role_name == role
    if condition.is_compound:
        return _condition_matches_role(condition.left, role) or _condition_matches_role(
            condition.right, role
        )
    return False


def _condition_is_pure_role_only(condition: ConditionExpr | None) -> bool:
    """Return True if the condition consists only of role_check nodes (no field checks).

    Used to determine whether an empty-personas rule should be treated as a
    role gate (where the condition itself restricts which roles match) rather
    than a wildcard open to all authenticated users.
    """
    if condition is None:
        return False
    if condition.role_check is not None:
        return True
    if condition.comparison is not None:
        return False
    if condition.grant_check is not None:
        return False
    if condition.is_compound:
        left_pure = _condition_is_pure_role_only(condition.left)
        right_pure = _condition_is_pure_role_only(condition.right)
        return left_pure and right_pure
    return False


def _rule_matches_role(rule: PermissionRule, role: str) -> bool:
    """Return True if *rule* applies to *role*.

    A rule applies when:
      1. rule.personas is empty AND the condition is not a pure role gate
         (applies to any authenticated user), OR
      2. rule.personas is empty AND the condition is a pure role gate AND
         the condition's role checks match *role*, OR
      3. role is explicitly listed in rule.personas, OR
      4. the rule's condition contains a role_check for *role*.
    """
    if not rule.personas:
        # If the condition is exclusively role_checks, treat it as a role gate.
        if _condition_is_pure_role_only(rule.condition):
            return _condition_matches_role(rule.condition, role)
        # Otherwise empty personas = open to all authenticated users.
        return True
    if role in rule.personas:
        return True
    if _condition_matches_role(rule.condition, role):
        return True
    return False


def _resolve_decision(
    access: AccessSpec,
    role: str,
    operation: str,
) -> PolicyDecision:
    """Resolve the access decision for (role, operation) against *access*.

    Cedar semantics: FORBID beats PERMIT; no matching rule → DENY.
    """
    # Collect rules for this operation.
    op_kind = PermissionKind(operation)
    op_rules = [r for r in access.permissions if r.operation == op_kind]

    forbid_matched = False
    permit_rule: PermissionRule | None = None

    for rule in op_rules:
        if not _rule_matches_role(rule, role):
            continue
        if rule.effect == PolicyEffect.FORBID:
            forbid_matched = True
        elif rule.effect == PolicyEffect.PERMIT:
            if permit_rule is None:
                permit_rule = rule

    # Cedar: forbid > permit.
    if forbid_matched:
        return PolicyDecision.DENY

    if permit_rule is None:
        return PolicyDecision.DENY

    # We have a permit.  Decide whether it's filtered.
    if _condition_has_field_filter(permit_rule.condition):
        return PolicyDecision.PERMIT_FILTERED

    return PolicyDecision.PERMIT


class AccessMatrix:
    """The resolved access matrix for an AppSpec.

    Cells is a mapping:  (role, entity, operation) → PolicyDecision
    """

    def __init__(
        self,
        cells: dict[tuple[str, str, str], PolicyDecision],
        warnings: list[PolicyWarning],
        roles: list[str],
        entities: list[str],
        operations: list[str],
    ) -> None:
        self._cells = cells
        self.warnings = warnings
        self.roles = roles
        self.entities = entities
        self.operations = operations

    def get(self, role: str, entity: str, operation: str) -> PolicyDecision:
        """Return the decision for (role, entity, operation).

        Returns DENY if the triple is not in the matrix.
        """
        return self._cells.get((role, entity, operation), PolicyDecision.DENY)

    def to_table(self) -> str:
        """Render the matrix as a Markdown table.

        Columns: entity | operation | <role1> | <role2> | ...
        """
        if not self.roles or not self.entities or not self.operations:
            return "*(empty matrix)*"

        col_sep = " | "
        header_parts = ["entity", "operation"] + self.roles
        header = col_sep.join(header_parts)
        separator = " | ".join(["---"] * len(header_parts))

        lines = [f"| {header} |", f"| {separator} |"]

        for entity in self.entities:
            for operation in self.operations:
                row_parts = [entity, operation]
                for role in self.roles:
                    decision = self.get(role, entity, operation)
                    row_parts.append(decision.value)
                lines.append(f"| {col_sep.join(row_parts)} |")

        return "\n".join(lines)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable representation of the matrix."""
        cells_serialized: list[dict[str, str]] = []
        for (role, entity, operation), decision in self._cells.items():
            cells_serialized.append(
                {
                    "role": role,
                    "entity": entity,
                    "operation": operation,
                    "decision": decision.value,
                }
            )

        warnings_serialized: list[dict[str, str | None]] = [
            {
                "kind": w.kind,
                "entity": w.entity,
                "role": w.role,
                "operation": w.operation,
                "message": w.message,
            }
            for w in self.warnings
        ]

        return {
            "roles": self.roles,
            "entities": self.entities,
            "operations": self.operations,
            "cells": cells_serialized,
            "warnings": warnings_serialized,
        }

    def to_csv(self) -> str:
        """Return the matrix as a CSV string.

        Columns: entity, operation, <role1>, <role2>, ...
        """
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["entity", "operation"] + self.roles)

        for entity in self.entities:
            for operation in self.operations:
                row = [entity, operation]
                for role in self.roles:
                    row.append(self.get(role, entity, operation).value)
                writer.writerow(row)

        return output.getvalue()


def generate_access_matrix(appspec: AppSpec) -> AccessMatrix:
    """Generate the complete static access matrix for *appspec*.

    Algorithm:
    1. Extract roles from appspec.personas (using .id).
    2. For each entity × operation × role:
       - No access spec → PERMIT_UNPROTECTED (+ warning).
       - No matching permit rule → DENY.
       - FORBID rule matches → DENY (Cedar override).
       - PERMIT rule with field condition → PERMIT_FILTERED.
       - PERMIT rule without field condition → PERMIT.
    3. Emit diagnostics for unprotected entities and orphan roles.
    """
    roles: list[str] = [p.id for p in appspec.personas]
    entities: list[str] = [e.name for e in appspec.domain.entities]
    operations: list[str] = list(OPERATIONS)

    # Build set of roles referenced in any permission rule for orphan detection.
    referenced_roles: set[str] = set()
    for entity in appspec.domain.entities:
        if entity.access:
            for rule in entity.access.permissions:
                referenced_roles.update(rule.personas)
                # Also count roles extracted from conditions.
                for cond_role in _extract_roles_from_access(entity.access):
                    referenced_roles.add(cond_role)

    cells: dict[tuple[str, str, str], PolicyDecision] = {}
    warnings: list[PolicyWarning] = []

    for entity in appspec.domain.entities:
        entity_name = entity.name
        has_rules = entity.access is not None and bool(entity.access.permissions)

        if not has_rules:
            # No access spec or empty permissions → PERMIT_UNPROTECTED.
            for role in roles:
                for op in operations:
                    cells[(role, entity_name, op)] = PolicyDecision.PERMIT_UNPROTECTED
            warnings.append(
                PolicyWarning(
                    kind="unprotected_entity",
                    entity=entity_name,
                    role="*",
                    operation="*",
                    message=(
                        f"Entity '{entity_name}' has no permission rules — "
                        "all operations are PERMIT_UNPROTECTED (backward-compat)"
                    ),
                )
            )
            continue

        assert entity.access is not None  # guarded by has_rules check above
        access = entity.access

        for role in roles:
            for op in operations:
                decision = _resolve_decision(access, role, op)
                cells[(role, entity_name, op)] = decision

        # Warn about redundant FORBID (FORBID on a role that has no PERMIT).
        perms = access.permissions
        for op in operations:
            op_kind = PermissionKind(op)
            forbid_roles = {
                r
                for rule in perms
                if rule.operation == op_kind and rule.effect == PolicyEffect.FORBID
                for r in (rule.personas if rule.personas else roles)
            }
            permit_roles = {
                r
                for rule in perms
                if rule.operation == op_kind and rule.effect == PolicyEffect.PERMIT
                for r in (rule.personas if rule.personas else roles)
            }
            for r in forbid_roles:
                if r not in permit_roles:
                    warnings.append(
                        PolicyWarning(
                            kind="redundant_forbid",
                            entity=entity_name,
                            role=r,
                            operation=op,
                            message=(
                                f"FORBID rule for role '{r}' on {entity_name}.{op} "
                                "is redundant — no PERMIT exists for this role"
                            ),
                        )
                    )

    # Warn about roles defined in personas but never referenced in any rule.
    role_set = set(roles)
    orphan_roles = role_set - referenced_roles
    for orphan in sorted(orphan_roles):
        warnings.append(
            PolicyWarning(
                kind="orphan_role",
                entity="*",
                role=orphan,
                operation="*",
                message=(f"Persona '{orphan}' is not referenced in any permission rule"),
            )
        )

    return AccessMatrix(
        cells=cells,
        warnings=warnings,
        roles=roles,
        entities=entities,
        operations=operations,
    )


def _extract_roles_from_condition(condition: ConditionExpr | None) -> list[str]:
    """Recursively extract all role names from a condition expression."""
    if condition is None:
        return []
    roles: list[str] = []
    if condition.role_check is not None:
        roles.append(condition.role_check.role_name)
    if condition.is_compound:
        roles.extend(_extract_roles_from_condition(condition.left))
        roles.extend(_extract_roles_from_condition(condition.right))
    return roles


def _extract_roles_from_access(access: AccessSpec) -> list[str]:
    """Extract all role names referenced in condition expressions within *access*."""
    roles: list[str] = []
    for rule in access.permissions:
        roles.extend(_extract_roles_from_condition(rule.condition))
    return roles
