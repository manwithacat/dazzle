"""Tests for the tenant_host: validator pass (#1289)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.validator import validate_appspec


def _parse_and_validate(src: str) -> list[str]:
    _m, _a, _t, _c, _u, fragment = parse_dsl(src, Path("<test>"))
    errors = validate_appspec(fragment)
    return [str(e) for e in errors]


def test_validator_rejects_slug_field_pointing_at_non_slug_field():
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  name: str(40) required
  tenant_host:
    domain: example.com
    slug_field: name
""".lstrip()
    errors = _parse_and_validate(src)
    assert any("slug_field" in e and "slug" in e.lower() for e in errors)


def test_validator_rejects_unknown_history_entity():
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    history_entity: NoSuchEntity
""".lstrip()
    errors = _parse_and_validate(src)
    assert any("history_entity" in e and "NoSuchEntity" in e for e in errors)


def test_validator_requires_order_when_two_entities_share_domain():
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
""".lstrip()
    errors = _parse_and_validate(src)
    assert any("order" in e and "example.com" in e for e in errors)


def test_validator_accepts_distinct_order_values():
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 1
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 2
""".lstrip()
    errors = _parse_and_validate(src)
    assert not any("order" in e for e in errors)


def test_validator_rejects_unimportable_template():
    """Rule 5: dotted-path templates must resolve at validate time."""
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    not_found_template: no.such.module:render
""".lstrip()
    errors = _parse_and_validate(src)
    assert any("not_found_template" in e and "no.such.module" in e for e in errors)


def test_validator_rejects_inconsistent_super_admin_role_across_domain():
    """Rule 6: multi-entity-same-domain must agree on cookie_scope, super_admin_role, canonical_hosts."""
    src = """
module t
app t "T"
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 1
    super_admin_role: admin
entity School:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    order: 2
    super_admin_role: owner
""".lstrip()
    errors = _parse_and_validate(src)
    assert any("super_admin_role" in e and "example.com" in e for e in errors)
