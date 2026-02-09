"""Tests for MCP policy analysis handler.

Validates the analyze, conflicts, coverage, and simulate operations
against in-memory AppSpec objects with various access configurations.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.core.ir.domain import (
    AccessSpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.mcp.server.handlers.policy import (
    _analyze,
    _coverage_matrix,
    _evaluate_rules,
    _find_conflicts,
    _personas_overlap,
    _rule_matches_persona,
    _simulate,
)

# =============================================================================
# Fixtures
# =============================================================================


def _entity(
    name: str,
    permissions: list[PermissionRule] | None = None,
    access: AccessSpec | None = None,
):
    """Create a minimal mock entity with optional access rules."""
    if permissions is not None and access is None:
        access = AccessSpec(permissions=permissions)
    entity = MagicMock()
    entity.name = name
    entity.title = name.title()
    entity.access = access
    return entity


def _permit(op: PermissionKind, personas: list[str] | None = None) -> PermissionRule:
    return PermissionRule(
        operation=op,
        effect=PolicyEffect.PERMIT,
        personas=personas or [],
    )


def _forbid(op: PermissionKind, personas: list[str] | None = None) -> PermissionRule:
    return PermissionRule(
        operation=op,
        effect=PolicyEffect.FORBID,
        personas=personas or [],
    )


def _appspec(entities: list, persona_ids: list[str] | None = None):
    """Create a minimal mock AppSpec."""
    spec = MagicMock()
    spec.domain.entities = entities

    # Create mock personas
    personas = []
    for pid in persona_ids or []:
        p = MagicMock()
        p.id = pid
        p.name = pid
        personas.append(p)
    spec.personas = personas

    return spec


# =============================================================================
# _rule_matches_persona
# =============================================================================


class TestRuleMatchesPersona:
    def test_empty_personas_matches_any(self) -> None:
        rule = _permit(PermissionKind.READ)
        assert _rule_matches_persona(rule, "admin")
        assert _rule_matches_persona(rule, "viewer")

    def test_specific_persona_matches(self) -> None:
        rule = _permit(PermissionKind.READ, personas=["admin"])
        assert _rule_matches_persona(rule, "admin")
        assert not _rule_matches_persona(rule, "viewer")

    def test_multiple_personas(self) -> None:
        rule = _permit(PermissionKind.READ, personas=["admin", "editor"])
        assert _rule_matches_persona(rule, "admin")
        assert _rule_matches_persona(rule, "editor")
        assert not _rule_matches_persona(rule, "viewer")


# =============================================================================
# _personas_overlap
# =============================================================================


class TestPersonasOverlap:
    def test_both_empty_overlap(self) -> None:
        a = _permit(PermissionKind.READ)
        b = _forbid(PermissionKind.READ)
        assert _personas_overlap(a, b)

    def test_one_empty_overlaps(self) -> None:
        a = _permit(PermissionKind.READ, personas=["admin"])
        b = _forbid(PermissionKind.READ)
        assert _personas_overlap(a, b)

    def test_same_persona_overlaps(self) -> None:
        a = _permit(PermissionKind.READ, personas=["admin"])
        b = _forbid(PermissionKind.READ, personas=["admin"])
        assert _personas_overlap(a, b)

    def test_disjoint_no_overlap(self) -> None:
        a = _permit(PermissionKind.READ, personas=["admin"])
        b = _forbid(PermissionKind.READ, personas=["intern"])
        assert not _personas_overlap(a, b)


# =============================================================================
# _evaluate_rules
# =============================================================================


class TestEvaluateRules:
    def test_no_access_returns_default_deny(self) -> None:
        entity = _entity("Task")
        assert _evaluate_rules(entity, "admin", PermissionKind.READ) == "default-deny"

    def test_permit_returns_allow(self) -> None:
        entity = _entity("Task", permissions=[_permit(PermissionKind.READ)])
        assert _evaluate_rules(entity, "admin", PermissionKind.READ) == "allow"

    def test_forbid_returns_deny(self) -> None:
        entity = _entity("Task", permissions=[_forbid(PermissionKind.DELETE)])
        assert _evaluate_rules(entity, "admin", PermissionKind.DELETE) == "deny"

    def test_forbid_overrides_permit(self) -> None:
        entity = _entity(
            "Task",
            permissions=[
                _permit(PermissionKind.DELETE),
                _forbid(PermissionKind.DELETE, personas=["intern"]),
            ],
        )
        assert _evaluate_rules(entity, "intern", PermissionKind.DELETE) == "deny"

    def test_no_matching_rule_returns_default_deny(self) -> None:
        entity = _entity("Task", permissions=[_permit(PermissionKind.READ, personas=["admin"])])
        assert _evaluate_rules(entity, "viewer", PermissionKind.READ) == "default-deny"

    def test_different_operation_not_matched(self) -> None:
        entity = _entity("Task", permissions=[_permit(PermissionKind.CREATE)])
        assert _evaluate_rules(entity, "admin", PermissionKind.DELETE) == "default-deny"


# =============================================================================
# analyze
# =============================================================================


class TestAnalyze:
    def test_entity_without_rules(self) -> None:
        entities = [_entity("Task")]
        appspec = _appspec(entities)
        result = _analyze(appspec, None)
        assert "Task" in result["entities_without_rules"]
        assert result["total_entities"] == 1

    def test_entity_with_full_coverage(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.CREATE),
                    _permit(PermissionKind.READ),
                    _permit(PermissionKind.UPDATE),
                    _permit(PermissionKind.DELETE),
                    _permit(PermissionKind.LIST),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _analyze(appspec, None)
        assert result["entities_without_rules"] == []
        assert result["uncovered_operations"] == []
        assert result["entities_with_full_coverage"] == 1

    def test_entity_with_partial_coverage(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.READ),
                    _permit(PermissionKind.LIST),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _analyze(appspec, None)
        assert len(result["uncovered_operations"]) == 1
        missing = result["uncovered_operations"][0]["missing_permit_for"]
        assert "create" in missing
        assert "update" in missing
        assert "delete" in missing

    def test_filter_by_entity_names(self) -> None:
        entities = [_entity("Task"), _entity("Invoice")]
        appspec = _appspec(entities)
        result = _analyze(appspec, ["Task"])
        assert result["total_entities"] == 1


# =============================================================================
# conflicts
# =============================================================================


class TestFindConflicts:
    def test_no_conflicts(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.READ),
                    _permit(PermissionKind.CREATE),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _find_conflicts(appspec, None)
        assert result["conflict_count"] == 0

    def test_permit_forbid_conflict(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.DELETE),
                    _forbid(PermissionKind.DELETE, personas=["intern"]),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _find_conflicts(appspec, None)
        assert result["conflict_count"] == 1
        assert result["conflicts"][0]["resolution"] == "FORBID wins (Cedar semantics)"

    def test_disjoint_personas_no_conflict(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.DELETE, personas=["admin"]),
                    _forbid(PermissionKind.DELETE, personas=["intern"]),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _find_conflicts(appspec, None)
        assert result["conflict_count"] == 0

    def test_same_effect_no_conflict(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.DELETE, personas=["admin"]),
                    _permit(PermissionKind.DELETE, personas=["editor"]),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _find_conflicts(appspec, None)
        assert result["conflict_count"] == 0


# =============================================================================
# coverage
# =============================================================================


class TestCoverageMatrix:
    def test_basic_matrix(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.READ),
                ],
            )
        ]
        appspec = _appspec(entities, persona_ids=["admin"])
        result = _coverage_matrix(appspec, None)
        assert result["summary"]["total_combinations"] == len(PermissionKind)
        # READ should be allowed, others default-deny
        read_entry = next(m for m in result["matrix"] if m["operation"] == "read")
        assert read_entry["decision"] == "allow"
        create_entry = next(m for m in result["matrix"] if m["operation"] == "create")
        assert create_entry["decision"] == "default-deny"

    def test_no_personas_uses_anonymous(self) -> None:
        entities = [_entity("Task")]
        appspec = _appspec(entities, persona_ids=[])
        result = _coverage_matrix(appspec, None)
        assert result["matrix"][0]["persona"] == "anonymous"

    def test_multiple_personas(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.DELETE, personas=["admin"]),
                    _forbid(PermissionKind.DELETE, personas=["intern"]),
                ],
            )
        ]
        appspec = _appspec(entities, persona_ids=["admin", "intern", "viewer"])
        result = _coverage_matrix(appspec, None)
        # admin DELETE = allow
        admin_del = next(
            m for m in result["matrix"] if m["persona"] == "admin" and m["operation"] == "delete"
        )
        assert admin_del["decision"] == "allow"
        # intern DELETE = deny
        intern_del = next(
            m for m in result["matrix"] if m["persona"] == "intern" and m["operation"] == "delete"
        )
        assert intern_del["decision"] == "deny"
        # viewer DELETE = default-deny
        viewer_del = next(
            m for m in result["matrix"] if m["persona"] == "viewer" and m["operation"] == "delete"
        )
        assert viewer_del["decision"] == "default-deny"


# =============================================================================
# simulate
# =============================================================================


class TestSimulate:
    def test_entity_not_found(self) -> None:
        appspec = _appspec([])
        result = _simulate(appspec, "NonExistent", "admin", "read")
        assert "error" in result

    def test_invalid_operation_kind(self) -> None:
        appspec = _appspec([_entity("Task")])
        result = _simulate(appspec, "Task", "admin", "fly")
        assert "error" in result

    def test_no_access_spec(self) -> None:
        appspec = _appspec([_entity("Task")])
        result = _simulate(appspec, "Task", "admin", "read")
        assert result["decision"] == "default-deny"
        assert result["reason"] == "Entity has no access spec defined"

    def test_permit_match(self) -> None:
        entities = [_entity("Task", permissions=[_permit(PermissionKind.READ)])]
        appspec = _appspec(entities)
        result = _simulate(appspec, "Task", "admin", "read")
        assert result["decision"] == "allow"
        assert len(result["matching_rules"]) == 1

    def test_forbid_overrides_permit(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.DELETE),
                    _forbid(PermissionKind.DELETE),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _simulate(appspec, "Task", "admin", "delete")
        assert result["decision"] == "deny"
        assert "FORBID" in result["reason"]
        assert len(result["matching_rules"]) == 2

    def test_skipped_rules_reported(self) -> None:
        entities = [
            _entity(
                "Task",
                permissions=[
                    _permit(PermissionKind.CREATE),
                    _permit(PermissionKind.READ, personas=["admin"]),
                ],
            )
        ]
        appspec = _appspec(entities)
        result = _simulate(appspec, "Task", "viewer", "read")
        assert result["decision"] == "default-deny"
        # Should have evaluated both rules
        assert len(result["rules_evaluated"]) == 2
        # First rule skipped (different operation), second skipped (persona mismatch)
        statuses = [r["status"] for r in result["rules_evaluated"]]
        assert "skipped (different operation)" in statuses
        assert "skipped (persona mismatch)" in statuses
