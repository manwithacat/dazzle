"""
Policy analysis tool for RBAC access control.

Operations:
  analyze   — Find entities without access rules, operations without permit coverage
  conflicts — Detect contradictory permit/forbid rules
  coverage  — Permission matrix: persona x entity x operation -> allow/deny
  simulate  — Trace which rules fire for a given persona + entity + operation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.domain import (
    AccessSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

logger = logging.getLogger("dazzle.mcp.policy")

# All CRUD operations we expect coverage for
ALL_OPS = list(PermissionKind)


def handle_policy(project_path: Path, arguments: dict[str, Any]) -> str:
    """Handle policy analysis operations."""
    operation = arguments.get("operation")
    entity_names: list[str] | None = arguments.get("entity_names")
    persona: str | None = arguments.get("persona")
    operation_kind: str | None = arguments.get("operation_kind")

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"}, indent=2)

    if operation == "analyze":
        return json.dumps(_analyze(appspec, entity_names), indent=2)
    elif operation == "conflicts":
        return json.dumps(_find_conflicts(appspec, entity_names), indent=2)
    elif operation == "coverage":
        return json.dumps(_coverage_matrix(appspec, entity_names), indent=2)
    elif operation == "simulate":
        if not persona or not entity_names or not operation_kind:
            return json.dumps(
                {"error": ("simulate requires persona, entity_names (single), and operation_kind")}
            )
        return json.dumps(
            _simulate(appspec, entity_names[0], persona, operation_kind),
            indent=2,
        )
    else:
        return json.dumps({"error": f"Unknown policy operation: {operation}"})


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------


def _analyze(appspec: Any, entity_names: list[str] | None) -> dict[str, Any]:
    """Find entities without access rules and operations without permit coverage."""
    entities = _filter_entities(appspec, entity_names)

    entities_without_rules: list[str] = []
    uncovered_operations: list[dict[str, Any]] = []

    for entity in entities:
        if entity.access is None or (
            not entity.access.permissions and not entity.access.visibility
        ):
            entities_without_rules.append(entity.name)
            continue

        # Check which CRUD operations lack a PERMIT rule
        access: AccessSpec = entity.access
        missing_ops: list[str] = []
        for op in ALL_OPS:
            has_permit = any(
                rule.operation == op and rule.effect == PolicyEffect.PERMIT
                for rule in access.permissions
            )
            if not has_permit:
                missing_ops.append(op.value)

        if missing_ops:
            uncovered_operations.append({"entity": entity.name, "missing_permit_for": missing_ops})

    return {
        "entities_without_rules": entities_without_rules,
        "uncovered_operations": uncovered_operations,
        "total_entities": len(entities),
        "entities_with_full_coverage": (
            len(entities) - len(entities_without_rules) - len(uncovered_operations)
        ),
    }


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------


def _find_conflicts(appspec: Any, entity_names: list[str] | None) -> dict[str, Any]:
    """Detect contradictory permit/forbid rules on the same operation and personas."""
    entities = _filter_entities(appspec, entity_names)
    conflicts: list[dict[str, Any]] = []

    for entity in entities:
        if entity.access is None:
            continue

        permissions = entity.access.permissions
        # Compare every pair of rules
        for i, rule_a in enumerate(permissions):
            for rule_b in permissions[i + 1 :]:
                if rule_a.operation != rule_b.operation:
                    continue
                if rule_a.effect == rule_b.effect:
                    continue
                # One is PERMIT, one is FORBID on the same operation
                if _personas_overlap(rule_a, rule_b):
                    permit_rule = rule_a if rule_a.effect == PolicyEffect.PERMIT else rule_b
                    forbid_rule = rule_a if rule_a.effect == PolicyEffect.FORBID else rule_b
                    conflicts.append(
                        {
                            "entity": entity.name,
                            "operation": rule_a.operation.value,
                            "permit_personas": permit_rule.personas or ["*"],
                            "forbid_personas": forbid_rule.personas or ["*"],
                            "resolution": "FORBID wins (Cedar semantics)",
                        }
                    )

    return {
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
    }


def _personas_overlap(rule_a: PermissionRule, rule_b: PermissionRule) -> bool:
    """Check whether two rules have overlapping persona scopes."""
    # Empty personas list means "any persona" -- overlaps with everything
    if not rule_a.personas or not rule_b.personas:
        return True
    return bool(set(rule_a.personas) & set(rule_b.personas))


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def _coverage_matrix(appspec: Any, entity_names: list[str] | None) -> dict[str, Any]:
    """Build a permission matrix: persona x entity x operation -> allow/deny/unset."""
    entities = _filter_entities(appspec, entity_names)

    # Collect all persona IDs
    persona_ids: list[str] = []
    for p in appspec.personas:
        pid: str = getattr(p, "id", None) or getattr(p, "name", None) or "unknown"
        persona_ids.append(pid)

    if not persona_ids:
        persona_ids = ["anonymous"]

    matrix: list[dict[str, Any]] = []

    for entity in entities:
        for persona_id in persona_ids:
            for op in ALL_OPS:
                decision = _evaluate_rules(entity, persona_id, op)
                matrix.append(
                    {
                        "persona": persona_id,
                        "entity": entity.name,
                        "operation": op.value,
                        "decision": decision,
                    }
                )

    # Build a summary
    allow_count = sum(1 for m in matrix if m["decision"] == "allow")
    deny_count = sum(1 for m in matrix if m["decision"] == "deny")
    unset_count = sum(1 for m in matrix if m["decision"] == "default-deny")

    return {
        "matrix": matrix,
        "summary": {
            "total_combinations": len(matrix),
            "allow": allow_count,
            "explicit_deny": deny_count,
            "default_deny": unset_count,
        },
    }


def _evaluate_rules(entity: EntitySpec, persona_id: str, op: PermissionKind) -> str:
    """Evaluate permission rules for a given entity/persona/operation combo.

    Returns "allow", "deny", or "default-deny".
    Cedar semantics: FORBID > PERMIT > default-deny.
    """
    if entity.access is None:
        return "default-deny"

    has_permit = False
    for rule in entity.access.permissions:
        if rule.operation != op:
            continue
        if not _rule_matches_persona(rule, persona_id):
            continue
        if rule.effect == PolicyEffect.FORBID:
            return "deny"
        if rule.effect == PolicyEffect.PERMIT:
            has_permit = True

    return "allow" if has_permit else "default-deny"


# ---------------------------------------------------------------------------
# simulate
# ---------------------------------------------------------------------------


def _simulate(
    appspec: Any,
    entity_name: str,
    persona: str,
    operation_kind: str,
) -> dict[str, Any]:
    """Trace which rules fire for a specific persona + entity + operation."""
    entity = next((e for e in appspec.domain.entities if e.name == entity_name), None)
    if entity is None:
        return {"error": f"Entity '{entity_name}' not found"}

    try:
        op = PermissionKind(operation_kind)
    except ValueError:
        valid = [k.value for k in PermissionKind]
        return {"error": f"Invalid operation_kind '{operation_kind}'. Valid: {valid}"}

    if entity.access is None:
        return {
            "entity": entity_name,
            "persona": persona,
            "operation": operation_kind,
            "rules_evaluated": [],
            "matching_rules": [],
            "decision": "default-deny",
            "reason": "Entity has no access spec defined",
        }

    rules_evaluated: list[dict[str, Any]] = []
    matching_rules: list[dict[str, Any]] = []
    has_permit = False
    has_forbid = False

    for idx, rule in enumerate(entity.access.permissions):
        rule_info: dict[str, Any] = {
            "index": idx,
            "operation": rule.operation.value,
            "effect": rule.effect.value,
            "personas": rule.personas or ["*"],
            "require_auth": rule.require_auth,
            "has_condition": rule.condition is not None,
        }

        # Does this rule even apply to the requested operation?
        if rule.operation != op:
            rule_info["status"] = "skipped (different operation)"
            rules_evaluated.append(rule_info)
            continue

        # Does this rule apply to the requested persona?
        if not _rule_matches_persona(rule, persona):
            rule_info["status"] = "skipped (persona mismatch)"
            rules_evaluated.append(rule_info)
            continue

        # Rule matches
        rule_info["status"] = "matched"
        rules_evaluated.append(rule_info)
        matching_rules.append(rule_info)

        if rule.effect == PolicyEffect.FORBID:
            has_forbid = True
        elif rule.effect == PolicyEffect.PERMIT:
            has_permit = True

    # Cedar decision: FORBID > PERMIT > default-deny
    if has_forbid:
        decision = "deny"
        reason = "Explicit FORBID rule matched (FORBID overrides PERMIT in Cedar semantics)"
    elif has_permit:
        decision = "allow"
        reason = "PERMIT rule matched, no FORBID rules override"
    else:
        decision = "default-deny"
        reason = "No matching rules found (default-deny)"

    return {
        "entity": entity_name,
        "persona": persona,
        "operation": operation_kind,
        "rules_evaluated": rules_evaluated,
        "matching_rules": matching_rules,
        "decision": decision,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_entities(appspec: Any, entity_names: list[str] | None) -> list[EntitySpec]:
    """Filter entities by name list, or return all."""
    entities: list[EntitySpec] = appspec.domain.entities
    if entity_names:
        entities = [e for e in entities if e.name in entity_names]
    return entities


def _rule_matches_persona(rule: PermissionRule, persona_id: str) -> bool:
    """Check whether a rule applies to the given persona."""
    # Empty personas list means the rule applies to any persona
    if not rule.personas:
        return True
    return persona_id in rule.personas
