"""ADR-0036 (#1394 Layer 2) — tenant hierarchy `parent:` on `tenant_host:`.

Phase 1: IR + parser. A `tenant_host:` block may declare `parent: <fk_field>`
naming a `ref` field on the same entity whose target is another tenant-kind
entity. Parsed into `TenantHostSpec.parent`; validation + runtime are later phases.
"""

from __future__ import annotations

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

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
