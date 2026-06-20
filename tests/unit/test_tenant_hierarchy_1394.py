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


# ─────────────── Phase 4: runtime current_tenant hierarchy compile (ADR-0036 D3) ───────────────

_HIER_DSL = """
module t
app t "T"
persona viewer "Viewer":
  capabilities: [read]
entity Trust "Trust":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
    order: 1
entity School "School":
  id: uuid pk
  slug: slug required
  trust: ref Trust required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: trust
    order: 2
entity Doc "Doc":
  id: uuid pk
  title: str(80) required
  school: ref School required
  permit:
    read: role(viewer)
    update: role(viewer)
  scope:
    read: school = current_tenant
      as: viewer
    update: school = current_tenant
      as: viewer
"""


def _hier_appspec(tmp_path):
    p = tmp_path / "h.dsl"
    p.write_text(_HIER_DSL.lstrip())
    return build_appspec(parse_modules([p]), "t")


def _scope(appspec, entity, op):
    e = _entity(appspec, entity)
    return next(s for s in e.access.scopes if str(s.operation).endswith(op))


def test_read_scope_expands_to_self_or_ancestor_disjunction(tmp_path) -> None:
    pred = _scope(_hier_appspec(tmp_path), "Doc", "read").predicate
    assert type(pred).__name__ == "BoolComposite"
    assert str(pred.op) == "or"
    kinds = [
        (type(c).__name__, getattr(c, "field", None) or getattr(c, "path", None))
        for c in pred.children
    ]
    # self/leaf leg + one ancestor FK-path leg
    assert ("ColumnCheck", "school") in kinds
    assert ("PathCheck", ["school", "trust"]) in kinds


def test_write_scope_stays_single_leaf_check(tmp_path) -> None:
    """ADR-0036: aggregate (ancestor) host views are read-only — UPDATE keeps the
    single leaf check (which matches no rows at an ancestor host)."""
    pred = _scope(_hier_appspec(tmp_path), "Doc", "update").predicate
    assert type(pred).__name__ == "ColumnCheck"
    assert pred.field == "school"
    assert pred.value.current_tenant is True


def test_read_disjunction_compiles_to_failclosed_policy_sql(tmp_path) -> None:
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.http.runtime.predicate_compiler import compile_predicate_policy

    appspec = _hier_appspec(tmp_path)
    fk = FKGraph.from_entities(list(appspec.domain.entities))
    pred = _scope(appspec, "Doc", "read").predicate
    sql = compile_predicate_policy(pred, "Doc", fk, entity_types=lambda e, f: "uuid")
    # leaf leg: direct FK = host GUC
    assert (
        "\"Doc\".\"school\" = NULLIF(current_setting('dazzle.host_tenant_id', true), '')::uuid"
        in sql
    )
    # ancestor leg: FK-path subquery against the same GUC
    assert 'IN (SELECT "id" FROM "School" WHERE "trust" = NULLIF(current_setting(' in sql
    # both legs NULLIF-wrapped → fail-closed; no unguarded ::uuid cast
    assert sql.count("NULLIF(current_setting('dazzle.host_tenant_id', true), '')::uuid") == 2


def test_flat_tenant_kind_not_expanded(tmp_path) -> None:
    """A scope whose FK points at a tenant kind with NO parent stays a single check."""
    dsl = """
module t
app t "T"
persona viewer "Viewer":
  capabilities: [read]
entity Org "Org":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
entity Doc "Doc":
  id: uuid pk
  title: str(80) required
  org: ref Org required
  permit:
    read: role(viewer)
  scope:
    read: org = current_tenant
      as: viewer
"""
    p = tmp_path / "f.dsl"
    p.write_text(dsl.lstrip())
    appspec = build_appspec(parse_modules([p]), "t")
    pred = _scope(appspec, "Doc", "read").predicate
    assert type(pred).__name__ == "ColumnCheck"  # no ancestor chain → not expanded


def test_non_tenant_fk_not_expanded(tmp_path) -> None:
    """`field = current_tenant` where field is NOT an FK to a tenant kind stays single."""
    dsl = """
module t
app t "T"
persona viewer "Viewer":
  capabilities: [read]
entity Plain "Plain":
  id: uuid pk
  name: str(40)
entity Doc "Doc":
  id: uuid pk
  title: str(80) required
  plain: ref Plain required
  permit:
    read: role(viewer)
  scope:
    read: plain = current_tenant
      as: viewer
"""
    p = tmp_path / "n.dsl"
    p.write_text(dsl.lstrip())
    appspec = build_appspec(parse_modules([p]), "t")
    pred = _scope(appspec, "Doc", "read").predicate
    assert type(pred).__name__ == "ColumnCheck"  # Plain is not a tenant_host kind → not expanded
