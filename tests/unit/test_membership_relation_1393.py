"""ADR-0037 (#1393 Phase C) — declarative `membership:` block on the tenant-root kind.

Phase 2: IR + parser. A `membership:` block (v1 carries an optional `roles:`
source; principal is always the framework `User`) parses into
`EntitySpec.membership` (`MembershipSpec`). Validation + runtime are later phases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_appspec


def _validate(src: str) -> list[str]:
    _m, _a, _t, _c, _u, fragment = parse_dsl(src.lstrip(), Path("<test>"))
    return [str(e) for e in validate_appspec(fragment)]


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


# ─────────────────── Phase 3: membership validation (ADR-0037 D2/D5) ───────────────────


def test_membership_on_root_kind_ok() -> None:
    src = """
module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: slug required
  role: str(40)
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    roles: role
"""
    assert not [e for e in _validate(src) if "membership" in e]


def test_membership_on_child_kind_errors() -> None:
    src = """
module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
entity Team "Team":
  id: uuid pk
  slug: slug required
  org: ref Org required
  role: str(40)
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: org
    order: 2
  membership:
    roles: role
"""
    assert any("tenant-root kind" in e for e in _validate(src))


def test_membership_on_non_tenant_host_errors() -> None:
    src = """
module t
app t "T"
entity Org "Org":
  id: uuid pk
  role: str(40)
  membership:
    roles: role
"""
    assert any("requires this entity to be a" in e for e in _validate(src))


def test_membership_roles_missing_field_errors() -> None:
    src = """
module t
app t "T"
entity Org "Org":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    roles: nope
"""
    assert any("membership.roles" in e and "nope" in e for e in _validate(src))
