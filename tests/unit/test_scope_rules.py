"""
Unit tests for ScopeRule IR type and AccessSpec.scopes field,
plus parser tests for scope: blocks and permit: field-condition rejection.
Includes converter tests for _convert_scope_rule (Task 3).
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, ScopeRule
from dazzle_back.converters.entity_converter import _convert_scope_rule
from dazzle_back.specs.auth import AccessOperationKind, ScopeRuleSpec


def _make_condition() -> ConditionExpr:
    """Helper: build a simple field condition (owner_id = current_user)."""
    return ConditionExpr(
        comparison=Comparison(
            field="owner_id",
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal="current_user"),
        )
    )


def _parse(dsl: str):
    """Parse DSL text and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestScopeRule:
    """Tests for ScopeRule dataclass / Pydantic model."""

    def test_scope_rule_with_field_condition(self):
        """ScopeRule stores operation and condition correctly."""
        condition = _make_condition()
        rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=condition,
            personas=["manager"],
        )

        assert rule.operation == PermissionKind.READ
        assert rule.condition == condition
        assert rule.personas == ["manager"]

    def test_scope_rule_condition_none_means_all(self):
        """condition=None means 'all records' — no row filter applied."""
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,
            personas=["admin"],
        )

        assert rule.operation == PermissionKind.LIST
        assert rule.condition is None
        assert rule.personas == ["admin"]

    def test_scope_rule_wildcard_personas(self):
        """personas=['*'] means all authorized roles."""
        rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["*"],
        )

        assert rule.personas == ["*"]

    def test_scope_rule_default_personas_empty(self):
        """personas defaults to empty list when not supplied."""
        rule = ScopeRule(operation=PermissionKind.DELETE)

        assert rule.personas == []

    def test_scope_rule_all_permission_kinds(self):
        """ScopeRule accepts every PermissionKind value."""
        for kind in PermissionKind:
            rule = ScopeRule(operation=kind)
            assert rule.operation == kind


class TestAccessSpecScopes:
    """Tests for the scopes field on AccessSpec."""

    def test_access_spec_scopes_defaults_to_empty_list(self):
        """AccessSpec.scopes must default to an empty list."""
        spec = AccessSpec()

        assert spec.scopes == []

    def test_access_spec_scopes_accepts_scope_rule_list(self):
        """AccessSpec.scopes accepts a list of ScopeRule instances."""
        rules = [
            ScopeRule(operation=PermissionKind.READ, personas=["*"]),
            ScopeRule(
                operation=PermissionKind.LIST,
                condition=_make_condition(),
                personas=["manager"],
            ),
        ]
        spec = AccessSpec(scopes=rules)

        assert len(spec.scopes) == 2
        assert spec.scopes[0].operation == PermissionKind.READ
        assert spec.scopes[1].operation == PermissionKind.LIST
        assert spec.scopes[1].personas == ["manager"]

    def test_access_spec_existing_fields_unaffected(self):
        """Adding scopes does not disturb visibility or permissions fields."""
        spec = AccessSpec()

        assert spec.visibility == []
        assert spec.permissions == []
        assert spec.scopes == []


class TestParseScopeBlock:
    """Parser tests for scope: blocks in entity definitions."""

    def test_parse_scope_block_basic(self):
        """scope: block with a field condition and a for: clause is parsed correctly."""
        dsl = """\
module test

entity School "School":
  id: uuid pk
  school: ref School optional

  permit:
    list: role(teacher)
    read: role(teacher)

  scope:
    list: school = current_user.school
      for: teacher, school_admin
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        rule = scopes[0]
        assert rule.operation == PermissionKind.LIST
        assert rule.condition is not None
        assert rule.condition.comparison is not None
        assert rule.condition.comparison.field == "school"
        assert rule.personas == ["teacher", "school_admin"]

    def test_parse_scope_all(self):
        """scope: list: all for: admin produces condition=None."""
        dsl = """\
module test

entity Report "Report":
  id: uuid pk

  permit:
    list: role(admin)

  scope:
    list: all
      for: admin
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        rule = scopes[0]
        assert rule.operation == PermissionKind.LIST
        assert rule.condition is None
        assert rule.personas == ["admin"]

    def test_parse_scope_wildcard_for(self):
        """scope: read: owner = current_user for: * is parsed correctly."""
        dsl = """\
module test

entity Note "Note":
  id: uuid pk

  permit:
    read: authenticated

  scope:
    read: owner = current_user
      for: *
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        assert scopes[0].personas == ["*"]

    def test_parse_scope_multiple_for_roles(self):
        """scope: for: with multiple roles parses all of them."""
        dsl = """\
module test

entity Document "Document":
  id: uuid pk

  permit:
    list: role(sovereign)

  scope:
    list: realm = current_user.realm
      for: sovereign, architect, witness
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 1
        assert scopes[0].personas == ["sovereign", "architect", "witness"]

    def test_parse_scope_multiple_rules(self):
        """Multiple rules in a scope: block are all parsed."""
        dsl = """\
module test

entity Item "Item":
  id: uuid pk

  permit:
    read: role(viewer)
    list: role(viewer)

  scope:
    list: school = current_user.school
      for: teacher
    read: owner = current_user
      for: *
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        scopes = entity.access.scopes
        assert len(scopes) == 2
        assert scopes[0].operation == PermissionKind.LIST
        assert scopes[0].personas == ["teacher"]
        assert scopes[1].operation == PermissionKind.READ
        assert scopes[1].personas == ["*"]

    def test_scope_stored_in_access_spec(self):
        """scope: rules are stored in entity.access.scopes."""
        dsl = """\
module test

entity Task "Task":
  id: uuid pk

  scope:
    list: all
      for: oracle
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.scopes) == 1
        # permissions and visibility are still empty
        assert entity.access.permissions == []
        assert entity.access.visibility == []


class TestPermitFieldConditionRejection:
    """Tests that field conditions in permit: blocks are rejected."""

    def test_field_condition_in_permit_raises_error(self):
        """A field comparison in a permit: block raises ParseError."""
        dsl = """\
module test

entity Shape "Shape":
  id: uuid pk
  school: ref School optional

  permit:
    list: school = current_user.school
"""
        with pytest.raises(ParseError, match="Field condition in permit: block"):
            _parse(dsl)

    def test_role_check_in_permit_is_allowed(self):
        """role(teacher) in a permit: block is valid — not a field condition."""
        dsl = """\
module test

entity Shape "Shape":
  id: uuid pk

  permit:
    list: role(teacher)
    read: role(teacher) or role(admin)
    create: role(admin)
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.permissions) == 3

    def test_authenticated_in_permit_is_allowed(self):
        """'authenticated' in permit: is a plain auth check — allowed."""
        dsl = """\
module test

entity Log "Log":
  id: uuid pk

  permit:
    read: authenticated
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.permissions) == 1

    def test_mixed_or_in_permit_raises_error(self):
        """role(x) or field = value in permit: is rejected because of the comparison."""
        dsl = """\
module test

entity Thing "Thing":
  id: uuid pk
  realm: str(100) optional

  permit:
    list: role(teacher) or realm = current_user.realm
"""
        with pytest.raises(ParseError, match="Field condition in permit: block"):
            _parse(dsl)

    def test_forbid_with_field_condition_is_allowed(self):
        """Field conditions in forbid: blocks are permitted (only permit: rejects them)."""
        dsl = """\
module test

entity Resource "Resource":
  id: uuid pk
  classification: enum[public,restricted]=public

  permit:
    read: role(admin)

  forbid:
    delete: classification = restricted
"""
        # This is from the existing pra example — must still work
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.permissions) == 2  # permit read + forbid delete

    def test_grant_check_in_permit_is_allowed(self):
        """has_grant(...) in permit: is an authorization check — allowed."""
        dsl = """\
module test

entity Record "Record":
  id: uuid pk
  department: str(50) optional

  permit:
    read: has_grant("observer", department)
"""
        fragment = _parse(dsl)
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.permissions) == 1


# =============================================================================
# Task 3: Converter tests — _convert_scope_rule
# =============================================================================


class TestConvertScopeRule:
    """Tests for the _convert_scope_rule converter function."""

    def test_convert_scope_rule_with_field_condition(self):
        """_convert_scope_rule converts a ScopeRule with a field condition."""
        condition = _make_condition()
        ir_rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=condition,
            personas=["manager"],
        )

        result = _convert_scope_rule(ir_rule)

        assert isinstance(result, ScopeRuleSpec)
        assert result.operation == AccessOperationKind.READ
        assert result.condition is not None
        assert result.condition.kind == "comparison"
        assert result.condition.field == "owner_id"
        assert result.condition.value == "current_user"
        assert result.personas == ["manager"]

    def test_convert_scope_rule_condition_none(self):
        """_convert_scope_rule with condition=None produces condition=None in spec."""
        ir_rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,
            personas=["admin"],
        )

        result = _convert_scope_rule(ir_rule)

        assert isinstance(result, ScopeRuleSpec)
        assert result.operation == AccessOperationKind.LIST
        assert result.condition is None
        assert result.personas == ["admin"]

    def test_convert_scope_rule_all_operations(self):
        """_convert_scope_rule maps every PermissionKind to the correct AccessOperationKind."""
        expected = {
            PermissionKind.CREATE: AccessOperationKind.CREATE,
            PermissionKind.READ: AccessOperationKind.READ,
            PermissionKind.UPDATE: AccessOperationKind.UPDATE,
            PermissionKind.DELETE: AccessOperationKind.DELETE,
            PermissionKind.LIST: AccessOperationKind.LIST,
        }
        for ir_kind, expected_kind in expected.items():
            result = _convert_scope_rule(ScopeRule(operation=ir_kind))
            assert result.operation == expected_kind

    def test_convert_scope_rule_wildcard_personas(self):
        """_convert_scope_rule preserves ['*'] persona list."""
        ir_rule = ScopeRule(
            operation=PermissionKind.READ,
            condition=_make_condition(),
            personas=["*"],
        )

        result = _convert_scope_rule(ir_rule)

        assert result.personas == ["*"]

    def test_convert_scope_rule_empty_personas(self):
        """_convert_scope_rule preserves empty personas list."""
        ir_rule = ScopeRule(operation=PermissionKind.DELETE)

        result = _convert_scope_rule(ir_rule)

        assert result.personas == []
