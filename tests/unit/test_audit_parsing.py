"""Tests for DSL audit: directive parsing.

Validates that the audit: directive in entity definitions is correctly
parsed into AuditConfig on EntitySpec.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import PermissionKind


def _parse_entity(dsl: str):
    """Parse a DSL snippet and return the first entity."""
    full_dsl = f'module test\napp test_app "Test"\n\n{dsl}'
    _, _, _, _, _, fragment = parse_dsl(full_dsl, Path("test.dsl"))
    assert fragment.entities
    return fragment.entities[0]


class TestAuditDirectiveParsing:
    def test_audit_all(self) -> None:
        """audit: all enables auditing for all operations."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
  audit: all
""")
        assert entity.audit is not None
        assert entity.audit.enabled is True
        assert entity.audit.operations == []  # empty = all operations

    def test_audit_true(self) -> None:
        """audit: true is equivalent to audit: all."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
  audit: true
""")
        assert entity.audit is not None
        assert entity.audit.enabled is True

    def test_audit_false(self) -> None:
        """audit: false disables auditing."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
  audit: false
""")
        assert entity.audit is not None
        assert entity.audit.enabled is False

    def test_audit_specific_operations(self) -> None:
        """audit: [create, update, delete] enables for specific ops."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
  audit: [create, update, delete]
""")
        assert entity.audit is not None
        assert entity.audit.enabled is True
        assert PermissionKind.CREATE in entity.audit.operations
        assert PermissionKind.UPDATE in entity.audit.operations
        assert PermissionKind.DELETE in entity.audit.operations
        assert PermissionKind.READ not in entity.audit.operations

    def test_no_audit_directive(self) -> None:
        """Entity without audit directive has None audit."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required
""")
        assert entity.audit is None

    def test_audit_with_access_rules(self) -> None:
        """audit: directive works alongside access: block."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required

  access:
    read: role(admin)
    write: role(admin)

  audit: all
""")
        assert entity.audit is not None
        assert entity.audit.enabled is True
        # Also verify access rules are parsed
        assert entity.access is not None
        assert len(entity.access.permissions) > 0


class TestPermitForbidParsing:
    def test_permit_block(self) -> None:
        """permit: block creates PERMIT rules."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required

  permit:
    read: role(viewer) or role(admin)
    create: role(editor) or role(admin)
    delete: role(admin)
""")
        from dazzle.core.ir import PolicyEffect

        permit_rules = [r for r in entity.access.permissions if r.effect == PolicyEffect.PERMIT]
        assert len(permit_rules) == 3

    def test_forbid_block(self) -> None:
        """forbid: block creates FORBID rules."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required

  forbid:
    delete: role(intern)
""")
        from dazzle.core.ir import PolicyEffect

        forbid_rules = [r for r in entity.access.permissions if r.effect == PolicyEffect.FORBID]
        assert len(forbid_rules) == 1
        assert forbid_rules[0].operation == PermissionKind.DELETE

    def test_mixed_permit_forbid(self) -> None:
        """Both permit and forbid blocks together."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required

  permit:
    read: role(viewer) or role(admin)
    create: role(editor)
    update: role(editor) or role(admin)
    delete: role(admin)

  forbid:
    delete: role(intern)
""")
        from dazzle.core.ir import PolicyEffect

        permits = [r for r in entity.access.permissions if r.effect == PolicyEffect.PERMIT]
        forbids = [r for r in entity.access.permissions if r.effect == PolicyEffect.FORBID]
        assert len(permits) == 4
        assert len(forbids) == 1

    def test_access_block_creates_permit_rules(self) -> None:
        """Existing access: block should create PERMIT rules (backward compat)."""
        entity = _parse_entity("""
entity Task "Task":
  id: uuid pk
  title: str(200) required

  access:
    read: role(admin)
    write: role(admin)
    delete: role(admin)
""")
        from dazzle.core.ir import PolicyEffect

        all_permit = all(r.effect == PolicyEffect.PERMIT for r in entity.access.permissions)
        assert all_permit
        assert len(entity.access.permissions) >= 3  # read, create+update (from write), delete
