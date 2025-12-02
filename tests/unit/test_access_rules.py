"""
Unit tests for inline access rules (v0.5.0 DSL feature).

Tests the `access:` block syntax with `read:` and `write:` rules.
"""

from pathlib import Path

import pytest

from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.ir import (
    AccessSpec,
    AuthContext,
    ComparisonOperator,
    LogicalOperator,
    PermissionKind,
    PermissionRule,
    VisibilityRule,
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 1
        assert len(task.access.permissions) == 0

        # Check visibility rule
        vis = task.access.visibility[0]
        assert vis.context == AuthContext.AUTHENTICATED
        assert vis.condition.comparison is not None
        assert vis.condition.comparison.field == "owner_id"
        assert vis.condition.comparison.operator == ComparisonOperator.EQUALS
        assert vis.condition.comparison.value.literal == "current_user"

    def test_access_block_write_only(self):
        """Test parsing entity with only write: rule."""
        dsl = """
module test

entity Task "Task":
  id: uuid pk
  title: str(200)
  owner_id: ref User

  access:
    write: owner_id = current_user
"""
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 0
        assert len(task.access.permissions) == 3

        # Check permission rules are created for all write operations
        operations = {r.operation for r in task.access.permissions}
        assert operations == {
            PermissionKind.CREATE,
            PermissionKind.UPDATE,
            PermissionKind.DELETE,
        }

        # All should require auth and have the same condition
        for perm in task.access.permissions:
            assert perm.require_auth is True
            assert perm.condition is not None
            assert perm.condition.comparison.field == "owner_id"

    def test_access_block_read_and_write(self):
        """Test parsing entity with both read: and write: rules."""
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        assert len(task.access.visibility) == 1
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        doc = fragment.entities[0]

        assert doc.access is not None

        # Read has chained OR conditions
        vis = doc.access.visibility[0]
        assert vis.condition.operator == LogicalOperator.OR

        # Write has AND with NOT_EQUALS
        perm = doc.access.permissions[0]
        assert perm.condition.operator == LogicalOperator.AND


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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        # Should have 2 visibility rules: anonymous from visible: and authenticated from access:
        assert len(task.access.visibility) == 2

        contexts = {r.context for r in task.access.visibility}
        assert AuthContext.ANONYMOUS in contexts
        assert AuthContext.AUTHENTICATED in contexts

    def test_access_with_permissions_block(self):
        """Test that access: can be combined with permissions: block."""
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
        _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        task = fragment.entities[0]

        assert task.access is not None
        # Should have 4 permission rules: 1 from permissions: + 3 from access:
        # But delete is duplicated, so it depends on implementation
        # Currently we don't deduplicate, so we get 4
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
        with pytest.raises(Exception):
            parse_dsl(dsl, Path("test.dsl"))
