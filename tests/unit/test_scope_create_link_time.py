"""Link-time validation tests for `scope: create:` predicate shapes (#1124).

v1 enforcement supports a narrow subset (ColumnCheck, UserAttrCheck,
PathCheck depth 1, BoolComposite, Tautology, Contradiction). The
linker rejects unsupported shapes — FK-path predicates with depth > 1,
ExistsCheck / NotExistsCheck — at link time so users see the
rejection during `dazzle validate`, not at request time.

The rejection raises `RenderValidationError` (subclass of ValueError)
with a clear message naming the unsupported shape and pointing at
`docs/reference/rbac-scope.md` + #1124.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dazzle.core.linker import RenderValidationError, build_appspec
from dazzle.core.parser import parse_modules

_DSL_BASE = """module test
app sample "Demo"

entity Team "Team":
  id: uuid pk
  name: str(100) required

entity TeamMembership "Membership":
  id: uuid pk
  user: ref User required
  team: ref Team required

entity User "User":
  id: uuid pk
  email: str(200) unique required
  name: str(100) required
  org_id: str(100)
"""


def _link(extra: str):
    full_src = _DSL_BASE + extra
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(full_src)
        tmp_path = Path(f.name)
    modules = parse_modules([tmp_path])
    return build_appspec(modules, root_module_name="test", known_renderers=None)


# ---------------------------------------------------------------------------
# v1 supported shapes — must parse cleanly
# ---------------------------------------------------------------------------


def test_simple_column_check_on_create_is_supported() -> None:
    """`scope: create: status = 'draft' as: member` → ColumnCheck.
    This is the bread-and-butter v1 case."""
    _link(
        """
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: str(50)
  created_by: ref User
  permit:
    create: role(member) or role(admin)
  scope:
    create: status = "draft"
      as: member
    create: all
      as: admin
"""
    )


def test_user_attr_check_on_create_is_supported() -> None:
    """`scope: create: created_by = current_user as: member` →
    UserAttrCheck. Most common write-op shape."""
    _link(
        """
entity Task "Task":
  id: uuid pk
  title: str(200) required
  created_by: ref User
  permit:
    create: role(member)
  scope:
    create: created_by = current_user
      as: member
"""
    )


def test_bool_composite_on_create_is_supported() -> None:
    """`scope: create: A and B as: member` → BoolComposite over two
    supported children."""
    _link(
        """
entity Task "Task":
  id: uuid pk
  title: str(200) required
  status: str(50)
  created_by: ref User
  permit:
    create: role(member)
  scope:
    create: created_by = current_user and status = "draft"
      as: member
"""
    )


# ---------------------------------------------------------------------------
# v1 unsupported shapes — must raise at link time
# ---------------------------------------------------------------------------


def test_fk_path_predicate_on_create_is_rejected_at_link_time() -> None:
    """`scope: create: team.org_id = current_user.org_id as: member`
    is a depth-2 PathCheck (FK traversal). v1 rejects with a clear
    message naming the path and pointing at the docs."""
    with pytest.raises(RenderValidationError, match="FK-path"):
        _link(
            """
entity TaskWithFK "Task":
  id: uuid pk
  title: str(200) required
  team: ref Team required
  permit:
    create: role(member)
  scope:
    create: team.name = "Engineering"
      as: member
"""
        )


def test_exists_check_on_create_is_rejected_at_link_time() -> None:
    """`scope: create: via TeamMembership(user_id = current_user,
    team_id = id) as: member` is an ExistsCheck. v1 rejects with a
    clear message."""
    with pytest.raises(RenderValidationError, match="ExistsCheck"):
        _link(
            """
entity TaskWithExists "Task":
  id: uuid pk
  title: str(200) required
  team: ref Team required
  permit:
    create: role(member)
  scope:
    create: via TeamMembership(user = current_user, team = team)
      as: member
"""
        )


# ---------------------------------------------------------------------------
# Update/delete are unaffected — FK-path predicates work there (the
# update/delete enforcement path uses SQL, not the v1 walker).
# ---------------------------------------------------------------------------


def test_fk_path_on_update_is_supported() -> None:
    """Sanity: the link-time rejection is specifically for `create:`.
    `update:` and `delete:` rules with FK-path predicates remain
    valid because they enforce via the SQL refetch path, not the
    v1 walker."""
    _link(
        """
entity TaskFKUpdate "Task":
  id: uuid pk
  title: str(200) required
  team: ref Team required
  permit:
    update: role(member)
  scope:
    update: team.name = "Engineering"
      as: member
"""
    )
