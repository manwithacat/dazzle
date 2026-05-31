"""Link-time validation tests for `scope: create:` predicate shapes (#1124, #1311).

As of #1311 (ADR-0028) the runtime evaluator resolves FK-path
(depth > 1) and ExistsCheck / NotExistsCheck create-scope predicates
via a payload-time SQL probe, so those shapes now LINK CLEANLY (they
were rejected at link time under #1124 v1). The only remaining
link-time rejection is a pathologically deep FK path (more than
`linker._MAX_SCOPE_CREATE_FK_DEPTH` hops), which raises
`RenderValidationError` (subclass of ValueError) naming the path and
pointing at `docs/reference/rbac-scope.md` + ADR-0028.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dazzle.core.ir.predicates import CompOp, PathCheck, ValueRef
from dazzle.core.linker import (
    _MAX_SCOPE_CREATE_FK_DEPTH,
    RenderValidationError,
    _assert_scope_create_predicate_depth_bounded,
    build_appspec,
)
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
# #1311 (ADR-0028): FK-path + EXISTS create-scope now link cleanly — the
# runtime resolves them via a payload-time SQL probe.
# ---------------------------------------------------------------------------


def test_fk_path_predicate_on_create_is_supported() -> None:
    """`scope: create: team.name = "Engineering" as: member` is a
    depth-2 PathCheck (one FK hop). #1311 resolves it via a payload-time
    probe, so it links cleanly (was rejected under #1124 v1)."""
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


def test_exists_check_on_create_is_supported() -> None:
    """`scope: create: via TeamMembership(user = current_user,
    team = team) as: member` is an ExistsCheck. #1311 resolves it via a
    payload-time EXISTS probe, so it links cleanly (was rejected under
    #1124 v1)."""
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
# Bounded FK-path depth — a pathologically deep path still rejects at link time.
# ---------------------------------------------------------------------------


def test_fk_path_within_depth_cap_is_accepted() -> None:
    """A path at exactly the hop cap is accepted (no raise).

    The depth assertion only reads ``rule.personas``, so a lightweight
    stub stands in for a full ScopeRule.
    """
    from types import SimpleNamespace

    path = [f"hop{i}" for i in range(_MAX_SCOPE_CREATE_FK_DEPTH)] + ["name"]
    pred = PathCheck(path=path, op=CompOp.EQ, value=ValueRef(literal="x"))
    rule = SimpleNamespace(personas=["member"])
    # Exactly _MAX hops — must not raise.
    _assert_scope_create_predicate_depth_bounded(pred, "Task", rule)


def test_fk_path_beyond_depth_cap_is_rejected() -> None:
    """A path exceeding the hop cap raises a clear depth error."""
    from types import SimpleNamespace

    # _MAX + 1 hops → path length _MAX + 2.
    path = [f"hop{i}" for i in range(_MAX_SCOPE_CREATE_FK_DEPTH + 1)] + ["name"]
    pred = PathCheck(path=path, op=CompOp.EQ, value=ValueRef(literal="x"))
    rule = SimpleNamespace(personas=["member"])
    with pytest.raises(RenderValidationError, match="too deep"):
        _assert_scope_create_predicate_depth_bounded(pred, "Task", rule)


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
