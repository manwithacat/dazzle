"""ADR-0036 (#1394 Layer 2) — tenant hierarchy `parent:` on `tenant_host:`.

Phase 1: IR + parser. A `tenant_host:` block may declare `parent: <fk_field>`
naming a `ref` field on the same entity whose target is another tenant-kind
entity. Parsed into `TenantHostSpec.parent`; validation + runtime are later phases.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
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
  tenant_host:
    domain: app.example
    slug_field: slug
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


def test_parent_parsed_onto_tenant_host(tmp_path) -> None:
    appspec = _appspec(tmp_path)
    team = _entity(appspec, "Team")
    assert team.tenant_host is not None
    assert team.tenant_host.parent == "org"


def test_root_kind_has_no_parent(tmp_path) -> None:
    appspec = _appspec(tmp_path)
    org = _entity(appspec, "Org")
    assert org.tenant_host is not None
    assert org.tenant_host.parent is None


def test_parent_is_optional_backwards_compatible(tmp_path) -> None:
    """A tenant_host block without parent: still parses (flat tenancy)."""
    dsl = """module t
app t "T"
entity Shop "Shop":
  id: uuid pk
  slug: str(60) unique required
  tenant_host:
    domain: app.example
    slug_field: slug
"""
    appspec = _appspec(tmp_path, dsl)
    assert _entity(appspec, "Shop").tenant_host.parent is None


# ─────────────────────── Phase 3: hierarchy validation (ADR-0036 D2) ───────────────────────


def test_valid_hierarchy_has_no_errors() -> None:
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
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: org
    order: 2
"""
    errors = _validate(src)
    assert not [e for e in errors if "parent" in e], errors


def test_parent_naming_missing_field_errors() -> None:
    src = """
module t
app t "T"
entity Team "Team":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: nope
"""
    assert any("parent" in e and "nope" in e for e in _validate(src))


def test_parent_pointing_at_non_tenant_host_errors() -> None:
    src = """
module t
app t "T"
entity Plain "Plain":
  id: uuid pk
  name: str(40)
entity Team "Team":
  id: uuid pk
  slug: slug required
  plain: ref Plain required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: plain
"""
    assert any("not a `tenant_host` entity" in e for e in _validate(src))


def test_parent_on_non_ref_field_errors() -> None:
    src = """
module t
app t "T"
entity Team "Team":
  id: uuid pk
  slug: slug required
  org: str(40)
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: org
"""
    assert any("must be a `ref`" in e for e in _validate(src))


def test_parent_cycle_errors() -> None:
    src = """
module t
app t "T"
entity A "A":
  id: uuid pk
  slug: slug required
  b: ref B required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: b
    order: 1
entity B "B":
  id: uuid pk
  slug: slug required
  a: ref A required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: a
    order: 2
"""
    assert any("cycle" in e.lower() for e in _validate(src))
