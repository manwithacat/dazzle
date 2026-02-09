"""
Unit tests for inline access rules (v0.5.0 DSL feature).

Tests the `access:` block syntax with `read:` and `write:` rules.
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import (
    AuthContext,
    ComparisonOperator,
    LogicalOperator,
    PermissionKind,
)


class TestAccessBlockParsing:
    """Tests for the access: block syntax."""

    def test_access_block_read_only(self):
        """Test parsing entity with only read: rule."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    read: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 1
        # read: now also creates a PERMIT READ permission (Cedar-style)
        assert len(task.access.permissions) == 1
        assert task.access.permissions[0].operation == PermissionKind.READ

        # Check visibility rule
        vis = task.access.visibility[0]
        assert vis.context == AuthContext.AUTHENTICATED
        assert vis.condition.comparison is not None
        assert vis.condition.comparison.field == "owner_id"
        assert vis.condition.comparison.operator == ComparisonOperator.EQUALS
        assert vis.condition.comparison.value.literal == "current_user"

    def test_access_block_write_only(self):
        """Test parsing entity with only write: rule.

        Note: In v0.7.0, write: only creates CREATE and UPDATE permissions.
        Use delete: for DELETE permission.
        """
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    write: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 0
        # v0.7.0: write: only creates CREATE and UPDATE (not DELETE)
        assert len(task.access.permissions) == 2

        # Check permission rules are created for CREATE and UPDATE only
        operations = {r.operation for r in task.access.permissions}
        assert operations == {
            PermissionKind.CREATE,
            PermissionKind.UPDATE,
        }

        # All should require auth and have the same condition
        for perm in task.access.permissions:
            assert perm.require_auth is True
            assert perm.condition is not None
            assert perm.condition.comparison.field == "owner_id"

    def test_access_block_read_and_write(self):
        """Test parsing entity with both read: and write: rules.

        Note: In v0.7.0, write: only creates CREATE and UPDATE permissions.
        """
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User
  is_public: bool=false

  access:
    read: owner_id = current_user or is_public = true
    write: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 1
        # read: creates PERMIT READ + write: creates CREATE and UPDATE = 3 permissions
        assert len(task.access.permissions) == 3

        # Check read rule has compound condition
        vis = task.access.visibility[0]
        assert vis.context == AuthContext.AUTHENTICATED
        assert vis.condition.operator == LogicalOperator.OR
        assert vis.condition.left is not None
        assert vis.condition.right is not None

    def test_access_block_complex_conditions(self):
        """Test parsing complex conditions in access rules."""
        dsl = """
module test

entity Document "Document":
  id: uuid pk
  owner_id: ref User
  team_id: ref Team
  status: enum[draft,review,published]

  access:
    read: owner_id = current_user or team_id = current_team or status = published
    write: owner_id = current_user and status != published
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]

        assert doc.access is not None

        # Read has chained OR conditions
        vis = doc.access.visibility[0]
        assert vis.condition.operator == LogicalOperator.OR

        # Write has AND with NOT_EQUALS (permissions[0] is PERMIT READ from read:)
        write_perms = [p for p in doc.access.permissions if p.operation != PermissionKind.READ]
        assert write_perms[0].condition.operator == LogicalOperator.AND


class TestAccessBlockWithExistingRules:
    """Test access: block can coexist with visible:/permissions: blocks."""

    def test_access_with_visible_block(self):
        """Test that access: can be combined with visible: block."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  owner_id: ref User
  is_public: bool=false

  visible:
    when anonymous: is_public = true

  access:
    read: owner_id = current_user
    write: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        # Should have 2 visibility rules: anonymous from visible: and authenticated from access:
        assert len(task.access.visibility) == 2

        contexts = {r.context for r in task.access.visibility}
        assert AuthContext.ANONYMOUS in contexts
        assert AuthContext.AUTHENTICATED in contexts

    def test_access_with_permissions_block(self):
        """Test that access: can be combined with permissions: block.

        Note: In v0.7.0, write: only creates CREATE and UPDATE permissions.
        """
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  owner_id: ref User

  permissions:
    delete: owner_id = current_user

  access:
    read: owner_id = current_user
    write: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        # Should have 4 permission rules:
        # - 1 from permissions: (DELETE)
        # - 1 from access: read: (READ)
        # - 2 from access: write: (CREATE, UPDATE)
        assert len(task.access.permissions) == 4


class TestAccessBlockErrors:
    """Test error handling for malformed access blocks."""

    def test_access_invalid_keyword(self):
        """Test that invalid keywords in access block raise error."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk

  access:
    execute: owner_id = current_user
"""
        with pytest.raises(Exception) as exc_info:
            parse_dsl(dsl, Path("test.dsl"))

        assert "read" in str(exc_info.value) or "write" in str(exc_info.value)

    def test_access_missing_condition(self):
        """Test that missing condition raises error."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk

  access:
    read:
    write: owner_id = current_user
"""
        with pytest.raises(ParseError):
            parse_dsl(dsl, Path("test.dsl"))


class TestAccessRulesV070:
    """Tests for v0.7.0 access rules enhancements."""

    def test_delete_permission_separate(self):
        """Test that delete: creates only DELETE permission."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    read: owner_id = current_user
    write: owner_id = current_user
    delete: owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        # 1 visibility + 4 permissions (READ, CREATE, UPDATE, DELETE)
        assert len(task.access.visibility) == 1
        assert len(task.access.permissions) == 4

        operations = {r.operation for r in task.access.permissions}
        assert operations == {
            PermissionKind.READ,
            PermissionKind.CREATE,
            PermissionKind.UPDATE,
            PermissionKind.DELETE,
        }

    def test_delete_different_condition_from_write(self):
        """Test delete: can have different condition than write:."""
        dsl = """
module test

entity Document "Document":
  id: uuid pk
  owner_id: ref User
  is_archived: bool=false

  access:
    write: owner_id = current_user
    delete: owner_id = current_user and is_archived = true
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]

        # Find DELETE permission
        delete_perm = next(
            p for p in doc.access.permissions if p.operation == PermissionKind.DELETE
        )
        assert delete_perm.condition.operator == LogicalOperator.AND

        # Find CREATE/UPDATE permissions
        write_perms = [
            p
            for p in doc.access.permissions
            if p.operation in (PermissionKind.CREATE, PermissionKind.UPDATE)
        ]
        for perm in write_perms:
            # Simple condition, no logical operator
            assert perm.condition.comparison is not None
            assert perm.condition.comparison.field == "owner_id"

    def test_role_check_in_condition(self):
        """Test role() function in access conditions."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)

  access:
    read: role(admin)
    write: role(admin)
    delete: role(admin)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        # Check visibility rule has role check
        vis = task.access.visibility[0]
        assert vis.condition.is_role_check is True
        assert vis.condition.role_check is not None
        assert vis.condition.role_check.role_name == "admin"

        # Check permissions have role check
        for perm in task.access.permissions:
            assert perm.condition.is_role_check is True
            assert perm.condition.role_check.role_name == "admin"

    def test_role_check_combined_with_field_condition(self):
        """Test role() combined with field conditions using OR."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    read: role(admin) or owner_id = current_user
    write: role(admin) or owner_id = current_user
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        # Check visibility rule has compound OR condition
        vis = task.access.visibility[0]
        assert vis.condition.operator == LogicalOperator.OR
        assert vis.condition.left.is_role_check is True
        assert vis.condition.left.role_check.role_name == "admin"
        assert vis.condition.right.comparison is not None
        assert vis.condition.right.comparison.field == "owner_id"

    def test_dotted_path_relationship_traversal(self):
        """Test relationship traversal with dotted paths (owner.team)."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    read: owner.team_id = current_team
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        vis = task.access.visibility[0]
        assert vis.condition.comparison is not None
        assert vis.condition.comparison.field == "owner.team_id"
        assert vis.condition.comparison.value.literal == "current_team"

    def test_multi_level_dotted_path(self):
        """Test multi-level relationship traversal."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  owner_id: ref User

  access:
    read: owner.team.organization_id = current_org
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        vis = task.access.visibility[0]
        assert vis.condition.comparison.field == "owner.team.organization_id"
        assert vis.condition.comparison.value.literal == "current_org"

    def test_role_and_combined_with_and(self):
        """Test role() combined with conditions using AND."""
        dsl = """
module test

entity Document "Document":
  id: uuid pk
  status: enum[draft,published]

  access:
    write: role(editor) and status = draft
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]

        perm = doc.access.permissions[0]
        assert perm.condition.operator == LogicalOperator.AND
        assert perm.condition.left.is_role_check is True
        assert perm.condition.left.role_check.role_name == "editor"
        assert perm.condition.right.comparison.field == "status"
        assert perm.condition.right.comparison.value.literal == "draft"

    def test_multiple_roles_with_or(self):
        """Test multiple role() checks combined with OR."""
        dsl = """
module test

entity AdminPanel "AdminPanel":
  id: uuid pk
  config: str(500)

  access:
    read: role(admin) or role(superuser)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        panel = fragment.entities[0]

        vis = panel.access.visibility[0]
        assert vis.condition.operator == LogicalOperator.OR
        assert vis.condition.left.role_check.role_name == "admin"
        assert vis.condition.right.role_check.role_name == "superuser"
