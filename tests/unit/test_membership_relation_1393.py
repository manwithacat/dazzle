"""ADR-0037 (#1393 Phase C) — declarative `membership:` block on the tenant-root kind.

Phase 2: IR + parser. A `membership:` block (v1 carries an optional `roles:`
source; principal is always the framework `User`) parses into
`EntitySpec.membership` (`MembershipSpec`). Validation + runtime are later phases.
"""

from __future__ import annotations

import pytest

from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

_DSL = """module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: str(60) unique required
  role: str(40)
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    roles: role
entity Team "Team":
  id: uuid pk
  slug: str(60) unique required
  org: ref Org required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: org
"""


def _appspec(tmp_path, dsl=_DSL):
    p = tmp_path / "a.dsl"
    p.write_text(dsl)
    return build_appspec(parse_modules([p]), "t")


def _entity(appspec, name):
    return next(e for e in appspec.domain.entities if e.name == name)


def test_membership_block_parsed_with_roles(tmp_path) -> None:
    appspec = _appspec(tmp_path)
    org = _entity(appspec, "Org")
    assert org.membership is not None
    assert org.membership.roles == "role"


def test_non_membership_kind_has_none(tmp_path) -> None:
    appspec = _appspec(tmp_path)
    assert _entity(appspec, "Team").membership is None


def test_membership_roles_optional(tmp_path) -> None:
    """An empty `membership:` block parses; roles defaults to None (framework roles)."""
    dsl = """module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: str(60) unique required
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    roles: role
"""
    # roles references a field that need not exist at parse time (validated later).
    appspec = _appspec(tmp_path, dsl)
    assert _entity(appspec, "Org").membership.roles == "role"


def test_unknown_membership_subfield_rejected(tmp_path) -> None:
    dsl = """module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: str(60) unique required
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    bogus: x
"""
    with pytest.raises(ParseError, match="membership"):
        _appspec(tmp_path, dsl)
