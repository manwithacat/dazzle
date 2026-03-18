"""Tests for the static access matrix generator (Layer 1 RBAC)."""

from __future__ import annotations

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    GrantCheck,
    RoleCheck,
)
from dazzle.core.ir.domain import (
    AccessSpec,
    DomainSpec,
    EntitySpec,
    PermissionKind,
    PermissionRule,
    PolicyEffect,
)
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.personas import PersonaSpec
from dazzle.rbac.matrix import (
    PolicyDecision,
    generate_access_matrix,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field(name: str = "id") -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=FieldTypeKind.UUID))


def _make_entity(
    name: str,
    access: AccessSpec | None = None,
    fields: list[FieldSpec] | None = None,
) -> EntitySpec:
    return EntitySpec(
        name=name,
        fields=fields or [_make_field()],
        access=access,
    )


def _make_persona(pid: str, label: str = "") -> PersonaSpec:
    return PersonaSpec(id=pid, label=label or pid)


def _make_appspec(
    entities: list[EntitySpec],
    personas: list[PersonaSpec] | None = None,
) -> AppSpec:
    return AppSpec(
        name="test_app",
        domain=DomainSpec(entities=entities),
        personas=personas or [],
    )


def _permit_rule(
    operation: PermissionKind,
    personas: list[str] | None = None,
    condition: ConditionExpr | None = None,
) -> PermissionRule:
    return PermissionRule(
        operation=operation,
        effect=PolicyEffect.PERMIT,
        personas=personas or [],
        condition=condition,
    )


def _forbid_rule(
    operation: PermissionKind,
    personas: list[str] | None = None,
    condition: ConditionExpr | None = None,
) -> PermissionRule:
    return PermissionRule(
        operation=operation,
        effect=PolicyEffect.FORBID,
        personas=personas or [],
        condition=condition,
    )


def _role_cond(role_name: str) -> ConditionExpr:
    """Build a pure role-check condition."""
    return ConditionExpr(role_check=RoleCheck(role_name=role_name))


def _field_cond(field: str = "owner_id") -> ConditionExpr:
    """Build a simple field comparison condition."""
    return ConditionExpr(
        comparison=Comparison(
            field=field,
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )


def _grant_cond(relation: str = "viewer", scope_field: str = "department") -> ConditionExpr:
    """Build a grant-check condition (runtime row filter)."""
    return ConditionExpr(grant_check=GrantCheck(relation=relation, scope_field=scope_field))


# ---------------------------------------------------------------------------
# Test: no access rules → PERMIT_UNPROTECTED
# ---------------------------------------------------------------------------


class TestUnprotectedEntity:
    def test_no_access_spec(self) -> None:
        entity = _make_entity("Task", access=None)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        for op in ["list", "read", "create", "update", "delete"]:
            assert matrix.get("admin", "Task", op) == PolicyDecision.PERMIT_UNPROTECTED

    def test_warning_emitted_for_unprotected(self) -> None:
        entity = _make_entity("Task", access=None)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        warn_kinds = [w.kind for w in matrix.warnings]
        assert "unprotected_entity" in warn_kinds

    def test_empty_permissions_list(self) -> None:
        """AccessSpec with empty permissions list is treated as unprotected."""
        entity = _make_entity("Task", access=AccessSpec(permissions=[]))
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT_UNPROTECTED


# ---------------------------------------------------------------------------
# Test: pure role gate
# ---------------------------------------------------------------------------


class TestPureRoleGate:
    def test_permit_for_matching_role(self) -> None:
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT

    def test_deny_for_non_matching_role(self) -> None:
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("guest", "Task", "read") == PolicyDecision.DENY

    def test_permit_empty_personas_matches_all_roles(self) -> None:
        """A rule with empty personas list applies to all roles."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.LIST, personas=[]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "list") == PolicyDecision.PERMIT
        assert matrix.get("guest", "Task", "list") == PolicyDecision.PERMIT

    def test_no_rule_for_operation_is_deny(self) -> None:
        """Only read is permitted; delete should be DENY."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: role-check condition → still PERMIT (not filtered)
# ---------------------------------------------------------------------------


class TestRoleCheckCondition:
    def test_role_check_condition_gives_permit(self) -> None:
        """A permit rule whose condition is a pure role_check is PERMIT, not PERMIT_FILTERED."""
        cond = _role_cond("admin")
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, condition=cond),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
        assert matrix.get("guest", "Task", "read") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: field condition → PERMIT_FILTERED
# ---------------------------------------------------------------------------


class TestFieldCondition:
    def test_field_condition_gives_permit_filtered(self) -> None:
        cond = _field_cond("owner_id")
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["user"], condition=cond),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("user")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("user", "Task", "read") == PolicyDecision.PERMIT_FILTERED

    def test_grant_check_gives_permit_filtered(self) -> None:
        cond = _grant_cond()
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.LIST, personas=["staff"], condition=cond),
            ]
        )
        entity = _make_entity("Doc", access=access)
        appspec = _make_appspec([entity], [_make_persona("staff")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("staff", "Doc", "list") == PolicyDecision.PERMIT_FILTERED


# ---------------------------------------------------------------------------
# Test: FORBID override
# ---------------------------------------------------------------------------


class TestForbidOverride:
    def test_forbid_overrides_permit_same_role(self) -> None:
        """FORBID beats PERMIT for the same role on the same operation."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.DELETE, personas=["admin"]),
                _forbid_rule(PermissionKind.DELETE, personas=["admin"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY

    def test_forbid_wildcard_overrides_all_permit(self) -> None:
        """A FORBID with empty personas overrides a PERMIT for any role."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.DELETE, personas=["admin"]),
                _forbid_rule(PermissionKind.DELETE, personas=[]),  # wildcard
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY
        assert matrix.get("guest", "Task", "delete") == PolicyDecision.DENY

    def test_forbid_one_role_does_not_affect_others(self) -> None:
        """Forbidding one role should not deny others that have a permit."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin"]),
                _permit_rule(PermissionKind.READ, personas=["editor"]),
                _forbid_rule(PermissionKind.READ, personas=["editor"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("editor")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
        assert matrix.get("editor", "Task", "read") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: mixed OR condition (role + field)
# ---------------------------------------------------------------------------


class TestMixedOrCondition:
    def test_or_role_and_field_is_permit_filtered(self) -> None:
        """OR of role_check and field comparison should be PERMIT_FILTERED."""
        from dazzle.core.ir.conditions import LogicalOperator

        cond = ConditionExpr(
            left=_role_cond("admin"),
            operator=LogicalOperator.OR,
            right=_field_cond("owner_id"),
        )
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.UPDATE, personas=[], condition=cond),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("user")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "update") == PolicyDecision.PERMIT_FILTERED
        assert matrix.get("user", "Task", "update") == PolicyDecision.PERMIT_FILTERED


# ---------------------------------------------------------------------------
# Test: multiple entities / operations
# ---------------------------------------------------------------------------


class TestMultiEntityMatrix:
    def test_unrelated_entities_independent(self) -> None:
        task_access = AccessSpec(
            permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])]
        )
        note_entity = _make_entity("Note", access=None)
        task_entity = _make_entity("Task", access=task_access)
        appspec = _make_appspec([task_entity, note_entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("admin", "Task", "read") == PolicyDecision.PERMIT
        assert matrix.get("admin", "Task", "delete") == PolicyDecision.DENY
        assert matrix.get("admin", "Note", "read") == PolicyDecision.PERMIT_UNPROTECTED


# ---------------------------------------------------------------------------
# Test: matrix.get() default
# ---------------------------------------------------------------------------


class TestMatrixGet:
    def test_get_unknown_triple_returns_deny(self) -> None:
        appspec = _make_appspec([], [])
        matrix = generate_access_matrix(appspec)

        assert matrix.get("ghost", "Missing", "list") == PolicyDecision.DENY


# ---------------------------------------------------------------------------
# Test: to_table()
# ---------------------------------------------------------------------------


class TestToTable:
    def test_table_contains_roles_and_entities(self) -> None:
        access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)
        table = matrix.to_table()

        assert "admin" in table
        assert "Task" in table
        assert "PERMIT" in table
        assert "DENY" in table

    def test_empty_matrix_returns_placeholder(self) -> None:
        appspec = _make_appspec([], [])
        matrix = generate_access_matrix(appspec)
        table = matrix.to_table()

        assert "empty" in table.lower()


# ---------------------------------------------------------------------------
# Test: to_json()
# ---------------------------------------------------------------------------


class TestToJson:
    def test_json_structure(self) -> None:
        access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)
        data = matrix.to_json()

        assert "roles" in data
        assert "entities" in data
        assert "operations" in data
        assert "cells" in data
        assert "warnings" in data
        assert "admin" in data["roles"]
        assert "Task" in data["entities"]

    def test_json_cells_have_required_keys(self) -> None:
        access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)
        data = matrix.to_json()

        for cell in data["cells"]:
            assert "role" in cell
            assert "entity" in cell
            assert "operation" in cell
            assert "decision" in cell


# ---------------------------------------------------------------------------
# Test: to_csv()
# ---------------------------------------------------------------------------


class TestToCsv:
    def test_csv_has_header(self) -> None:
        access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)
        csv_text = matrix.to_csv()
        lines = csv_text.strip().splitlines()

        assert lines[0].startswith("entity,operation")
        assert "admin" in lines[0]

    def test_csv_has_correct_row_count(self) -> None:
        access = AccessSpec(permissions=[_permit_rule(PermissionKind.READ, personas=["admin"])])
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin")])
        matrix = generate_access_matrix(appspec)
        csv_text = matrix.to_csv()
        lines = csv_text.strip().splitlines()

        # 1 header + 5 operations × 1 entity = 6 lines
        assert len(lines) == 6


# ---------------------------------------------------------------------------
# Test: warnings
# ---------------------------------------------------------------------------


class TestWarnings:
    def test_redundant_forbid_warning(self) -> None:
        """Warn when FORBID exists but no PERMIT for that role on that operation."""
        access = AccessSpec(
            permissions=[
                _forbid_rule(PermissionKind.DELETE, personas=["guest"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("guest")])
        matrix = generate_access_matrix(appspec)

        warn_kinds = [w.kind for w in matrix.warnings]
        assert "redundant_forbid" in warn_kinds

    def test_orphan_role_warning(self) -> None:
        """Persona not referenced in any rule emits orphan_role warning."""
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("orphan")])
        matrix = generate_access_matrix(appspec)

        orphan_warns = [w for w in matrix.warnings if w.kind == "orphan_role"]
        assert any(w.role == "orphan" for w in orphan_warns)

    def test_no_orphan_when_all_roles_used(self) -> None:
        access = AccessSpec(
            permissions=[
                _permit_rule(PermissionKind.READ, personas=["admin", "editor"]),
            ]
        )
        entity = _make_entity("Task", access=access)
        appspec = _make_appspec([entity], [_make_persona("admin"), _make_persona("editor")])
        matrix = generate_access_matrix(appspec)

        orphan_warns = [w for w in matrix.warnings if w.kind == "orphan_role"]
        assert len(orphan_warns) == 0
