"""Static access matrix generator — Layer 1 of the RBAC verification framework.

Given a parsed AppSpec, generates the complete access matrix: for every
(role, entity, operation), determines whether access is PERMIT, DENY,
PERMIT_FILTERED, or PERMIT_UNPROTECTED.

Cedar semantics:
  - FORBID overrides PERMIT (forbid > permit > default-deny)
  - Default with no matching rule → DENY
  - No rules at all on entity → PERMIT_UNPROTECTED (backward-compat warning)
"""

from __future__ import annotations  # required: forward reference

import csv
import io
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.conditions import ConditionExpr
from dazzle.core.ir.domain import (
    AccessSpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
    ScopeRule,
)

if TYPE_CHECKING:
    from dazzle.core.ir.atomic_flows import FlowInvariant


class PolicyDecision(StrEnum):
    """The resolved access decision for a (role, entity, operation) triple."""

    PERMIT = "PERMIT"
    """Access granted via a pure role gate — no row-level filter."""

    PERMIT_SCOPED = "PERMIT_SCOPED"
    """Access granted and a scope rule with a field condition applies — rows are filtered."""

    PERMIT_NO_SCOPE = "PERMIT_NO_SCOPE"
    """Access granted but no matching scope rule found — role will see 0 records (warning)."""

    DENY = "DENY"
    """Access denied — either no matching permit rule or an explicit forbid."""

    PERMIT_FILTERED = "PERMIT_FILTERED"
    """Access granted but rows are filtered by a field-level condition (legacy — no scope: blocks)."""

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


@dataclass(frozen=True)
class AtomicFlowProjection:
    """How an `atomic` flow projects onto the access surface (#1313, ADR-0029).

    A flow's ``permit_execute`` roles can perform each step's operation on the
    step's entity **via the flow** — a grant path distinct from the entity's
    direct CRUD ``permit:``. Surfaced as its own structure (not folded into the
    CRUD ``cells``) so the matrix stays analyzable without conflating the two
    paths: the conformance verifier probes CRUD routes, whereas a flow runs at
    ``POST /api/atomic/<name>`` and enforces ``scope: create:`` /
    ``scope: update:`` per step (the same predicate algebra, #1311/#1312).
    """

    name: str
    label: str
    roles: tuple[str, ...]
    steps: tuple[tuple[str, str], ...]  # ordered (entity, operation) per step
    invariants: tuple[str, ...] = ()
    """#1318 (ADR-0031): the flow's declared aggregate invariants, each rendered
    to a stable human string (e.g. ``"sum(Posting.amount) = 0"``) so the
    transactional guarantee is visible in the matrix (ADR-0029 inv 8)."""


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


# #1318 (ADR-0031): comparison-operator symbols for rendering a flow invariant
# to a stable human string. Restricted to the operators an aggregate invariant
# can use; imported lazily-typed via CompOp at call sites.
_OP_SYM: dict[str, str] = {
    "EQ": "=",
    "LTE": "<=",
    "GTE": ">=",
    "LT": "<",
    "GT": ">",
    "NEQ": "!=",
}


def _render_invariant(inv: FlowInvariant) -> str:
    """Render a flow invariant to a stable human string (#1318, ADR-0031).

    Format: ``<agg_fn>(<entity>[.<field>]) <op> <rhs>`` — e.g.
    ``sum(Posting.amount) = 0`` or ``count(LineItem) <= input.budget.max_items``.
    """
    field = f".{inv.field}" if inv.field else ""
    if inv.rhs.literal is not None:
        rhs_str = str(inv.rhs.literal)
    else:
        rhs_str = f"input.{inv.rhs.anchor_input}.{inv.rhs.anchor_field}"
    return f"{inv.agg_fn.value}({inv.entity}{field}) {_OP_SYM[inv.op.name]} {rhs_str}"


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
      1. rule.deny_all is True — the rule explicitly forbids the
         operation for everyone, no role matches (#1281).
      2. rule.personas is empty AND the condition is not a pure role gate
         (applies to any authenticated user), OR
      3. rule.personas is empty AND the condition is a pure role gate AND
         the condition's role checks match *role*, OR
      4. role is explicitly listed in rule.personas, OR
      5. the rule's condition contains a role_check for *role*.
    """
    if rule.deny_all:
        # `permit: <op>: false` — denial is universal; no role matches.
        return False
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


def _find_scope_for_role(
    scopes: list[ScopeRule],
    operation: PermissionKind,
    role: str,
) -> ScopeRule | None:
    """Return the first scope rule matching (operation, role), or None.

    A rule matches when its operation equals *operation* and either '*' is in
    its personas list or *role* is explicitly listed.

    #1071: When *operation* is ``READ`` and no explicit ``read:`` scope rule
    matches, fall back to the ``list:`` scope rule. The dominant convention
    across every Dazzle example app + downstream user app authored to date
    is "one ``list:`` rule governs the row-visibility predicate; read views
    inherit it." Without this fallback, every app that follows the documented
    pattern hits PERMIT_NO_SCOPE on ``read`` ops → returns 0 records → forces
    boilerplate `read:` scope blocks that duplicate the `list:` predicate.

    The fallback only applies to ``read`` (visibility-class op). ``create``,
    ``update``, ``delete`` are mutating-class ops where row-filter semantics
    differ from listing, and they still require explicit scope rules. The
    fallback ALSO loses to an explicit ``read:`` rule — declared overrides
    always win over the implicit inheritance.
    """
    for scope in scopes:
        if scope.operation != operation:
            continue
        if "*" in scope.personas or role in scope.personas:
            return scope

    # #1071 — list: → read: implicit fallback. Re-run the loop against LIST
    # only when the caller asked for READ and the explicit READ pass returned
    # nothing. Never recurses (operation passed in is always LIST after the
    # fallback, never READ again).
    if operation == PermissionKind.READ:
        for scope in scopes:
            if scope.operation != PermissionKind.LIST:
                continue
            if "*" in scope.personas or role in scope.personas:
                return scope
    return None


def _resolve_permit_decision(
    access: AccessSpec,
    role: str,
    op_kind: PermissionKind,
    permit_rule: PermissionRule,
) -> PolicyDecision:
    """Resolve the final decision for a confirmed permit, considering scope rules.

    If *access* has scope rules (new model):
      - Matching scope with condition=None → PERMIT (scope: all)
      - Matching scope with condition → PERMIT_SCOPED
      - No matching scope rule → PERMIT_NO_SCOPE (warning emitted by caller)

    Legacy path (no scopes on entity): use field-condition filtering.
    """
    if access.scopes:
        scope_match = _find_scope_for_role(access.scopes, op_kind, role)
        if scope_match is None:
            return PolicyDecision.PERMIT_NO_SCOPE
        if scope_match.condition is None:
            return PolicyDecision.PERMIT
        return PolicyDecision.PERMIT_SCOPED

    # Legacy path — use PERMIT_FILTERED for field-condition rules.
    if _condition_has_field_filter(permit_rule.condition):
        return PolicyDecision.PERMIT_FILTERED

    return PolicyDecision.PERMIT


def _no_scope_rule_message(entity_name: str, role: str, op: str) -> str:
    """Format the `no_scope_rule` warning differentiated by operation (#1123).

    Pre-v0.71.19 the same "will see 0 records" message fired for every
    operation — which was misleading for write ops (no row is "seen";
    the operation is rejected). v0.71.19 ships runtime enforcement for
    `scope: update:` / `scope: delete:`, so the message now matches
    each operation's actual behaviour. `scope: create:` is parsed but
    enforcement is deferred to v0.72.x — see #1124.
    """
    common = f"Role '{role}' passes permit for {entity_name}.{op} but has no matching scope rule —"
    if op in {"read", "list"}:
        return f"{common} will see 0 records"
    if op in {"update", "delete"}:
        return (
            f"{common} the request will 404 at runtime (scope predicate "
            f"will reject every row for this role; add a `scope: {op}:` "
            "rule or `scope: all as: <persona>`)"
        )
    if op == "create":
        return (
            f"{common} the inserted row will 403 at runtime (predicate "
            f"is evaluated against the payload after framework defaulting; "
            f"see docs/reference/rbac-scope.md for the v1 supported shapes "
            f"— ColumnCheck / UserAttrCheck / BoolComposite — and #1124 "
            f"for the FK-path / EXISTS roadmap)"
        )
    # Future-proof: unknown op falls through to the generic message.
    return f"{common} this operation may default-deny at runtime"


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

    return _resolve_permit_decision(access, role, op_kind, permit_rule)


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
        atomic_flows: list[AtomicFlowProjection] | None = None,
    ) -> None:
        self._cells = cells
        self.warnings = warnings
        self.roles = roles
        self.entities = entities
        self.operations = operations
        # #1313 (ADR-0029): atomic-flow grant paths, projected separately from
        # the CRUD `cells` (see AtomicFlowProjection).
        self.atomic_flows = atomic_flows or []

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

        # #1313 — atomic flows render as their own section (a distinct grant
        # path; not part of the per-(role,entity,op) CRUD grid above).
        if self.atomic_flows:
            lines.append("")
            lines.append("#### Atomic flows")
            lines.append("")
            lines.append("| flow | execute roles | steps (entity:op) | invariants |")
            lines.append("| --- | --- | --- | --- |")
            for f in self.atomic_flows:
                steps = ", ".join(f"{e}:{op}" for (e, op) in f.steps)
                invariants = "; ".join(f.invariants) if f.invariants else "—"
                lines.append(f"| {f.name} | {', '.join(f.roles)} | {steps} | {invariants} |")

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

        atomic_serialized: list[dict[str, object]] = [
            {
                "name": f.name,
                "label": f.label,
                "roles": list(f.roles),
                "steps": [{"entity": e, "operation": op} for (e, op) in f.steps],
                "invariants": list(f.invariants),
            }
            for f in self.atomic_flows
        ]

        return {
            "roles": self.roles,
            "entities": self.entities,
            "operations": self.operations,
            "cells": cells_serialized,
            "warnings": warnings_serialized,
            "atomic_flows": atomic_serialized,
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
    1. Extract roles from appspec.personas (using .effective_role,
       which is .role when set else .id — see #1147).
    2. For each entity × operation × role:
       - No access spec → PERMIT_UNPROTECTED (+ warning).
       - No matching permit rule → DENY.
       - FORBID rule matches → DENY (Cedar override).
       - PERMIT rule with field condition → PERMIT_FILTERED.
       - PERMIT rule without field condition → PERMIT.
    3. Emit diagnostics for unprotected entities and orphan roles.
       The orphan check operates on resolved role names, so a persona
       with ``role: brand_owner`` is considered referenced whenever
       ``brand_owner`` appears in a permit/scope rule — even if the
       persona id is ``commercial``.
    """
    # #1147: build a persona-id → effective-role map so warnings can
    # mention both the persona name (what the user sees) and the role
    # they map to (what the lint actually checks).
    persona_roles: dict[str, str] = {p.id: p.effective_role for p in appspec.personas}
    # Deduplicate while preserving order — two personas sharing one
    # role should produce a single matrix column, not two.
    seen_roles: set[str] = set()
    roles: list[str] = []
    for p in appspec.personas:
        r = p.effective_role
        if r not in seen_roles:
            seen_roles.add(r)
            roles.append(r)
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
                if decision == PolicyDecision.PERMIT_NO_SCOPE:
                    warnings.append(
                        PolicyWarning(
                            kind="no_scope_rule",
                            entity=entity_name,
                            role=role,
                            operation=op,
                            message=_no_scope_rule_message(entity_name, role, op),
                        )
                    )

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

        # #1352: dead scope rules. Both shapes fail closed at runtime (safe),
        # but the author gets no signal that the rule they wrote is inert —
        # the inverse of the no_scope_rule warning above.
        known_bindings = set(roles) | set(persona_roles) | referenced_roles
        for scope in access.scopes:
            scope_op = scope.operation.value
            unknown = [b for b in scope.personas if b != "*" and b not in known_bindings]
            for binding in unknown:
                warnings.append(
                    PolicyWarning(
                        kind="unknown_scope_persona",
                        entity=entity_name,
                        role=binding,
                        operation=scope_op,
                        message=(
                            f"scope rule for {entity_name}.{scope_op} binds "
                            f"'as: {binding}' but no such persona or role is declared "
                            "— the rule can never match (likely a typo)"
                        ),
                    )
                )

            # Reachability: does any bound, known persona pass permit for the
            # rule's operation? A LIST scope also serves READ (fallback in
            # _find_scope_for_role), so check both before calling it dead.
            if "*" in scope.personas:
                bound_roles = list(roles)
            else:
                bound_roles = [persona_roles.get(b, b) for b in scope.personas if b not in unknown]
            if not bound_roles:
                continue  # fully covered by unknown_scope_persona above
            served_ops = [scope_op]
            if scope.operation == PermissionKind.LIST:
                served_ops.append(PermissionKind.READ.value)
            reachable = any(
                _resolve_decision(access, r, o) != PolicyDecision.DENY
                for r in bound_roles
                for o in served_ops
            )
            if not reachable:
                warnings.append(
                    PolicyWarning(
                        kind="scope_without_permit",
                        entity=entity_name,
                        role=", ".join(scope.personas),
                        operation=scope_op,
                        message=(
                            f"scope rule for {entity_name}.{scope_op} "
                            f"(as: {', '.join(scope.personas)}) has no matching "
                            f"permit — default-deny makes the rule unreachable "
                            f"(add `permit: {scope_op}:` for these roles or "
                            "remove the scope rule)"
                        ),
                    )
                )

    # #1147: warn about roles defined in personas but never referenced
    # in any rule. The diff is now over *role names* (resolved via
    # PersonaSpec.effective_role), so a persona named ``commercial``
    # with ``role: brand_owner`` no longer trips orphan_role when
    # ``brand_owner`` is referenced. The warning message names the
    # persona id AND the role so the operator can find both quickly.
    role_set = set(roles)
    orphan_roles = role_set - referenced_roles
    # Build inverse map (role → personas mapped to it) for the message.
    role_to_personas: dict[str, list[str]] = {}
    for pid, prole in persona_roles.items():
        role_to_personas.setdefault(prole, []).append(pid)
    for orphan in sorted(orphan_roles):
        persona_ids = role_to_personas.get(orphan, [])
        if persona_ids and persona_ids != [orphan]:
            persona_label = ", ".join(f"'{pid}'" for pid in sorted(persona_ids))
            message = (
                f"Role '{orphan}' (used by persona {persona_label}) "
                f"is not referenced in any permission rule"
            )
        else:
            message = f"Persona '{orphan}' is not referenced in any permission rule"
        warnings.append(
            PolicyWarning(
                kind="orphan_role",
                entity="*",
                role=orphan,
                operation="*",
                message=message,
            )
        )

    # #1313 (ADR-0029): project atomic flows onto the access surface — a flow's
    # permit_execute roles can do each step's op on the step's entity via the
    # flow. Kept separate from `cells` (distinct grant path; see
    # AtomicFlowProjection) so the CRUD matrix + conformance verifier are
    # unaffected.
    from dazzle.core.ir.atomic_flows import FlowUpdate

    atomic_projections: list[AtomicFlowProjection] = []
    for flow in appspec.atomic_flows or []:
        steps = tuple(
            (step.entity, "update" if isinstance(step, FlowUpdate) else "create")
            for step in flow.steps
        )
        invariants = tuple(_render_invariant(inv) for inv in flow.invariants)
        atomic_projections.append(
            AtomicFlowProjection(
                name=flow.name,
                label=flow.label,
                roles=tuple(flow.permit_execute),
                steps=steps,
                invariants=invariants,
            )
        )

    return AccessMatrix(
        cells=cells,
        warnings=warnings,
        roles=roles,
        entities=entities,
        operations=operations,
        atomic_flows=atomic_projections,
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
