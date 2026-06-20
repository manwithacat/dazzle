"""Tests for the `tenant_host:` block parser and IR (#1289)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.lexer import Lexer, TokenType


def test_tenant_host_spec_minimal_fields():
    """TenantHostSpec accepts the minimum required fields."""
    spec = ir.TenantHostSpec(domain="example.com", slug_field="slug")
    assert spec.domain == "example.com"
    assert spec.slug_field == "slug"
    assert spec.canonical_hosts == []
    assert spec.cookie_scope == "host"
    assert spec.super_admin_role == "super_admin"
    assert spec.history_entity is None
    assert spec.order is None


def test_tenant_host_spec_is_frozen():
    """TenantHostSpec instances are immutable."""
    spec = ir.TenantHostSpec(domain="example.com", slug_field="slug")
    with pytest.raises(ValidationError):
        spec.domain = "other.com"  # type: ignore[misc]


def test_lexer_emits_tenant_host_token():
    """The lexer recognises `tenant_host` as a keyword."""
    tokens = list(Lexer("tenant_host", Path("<test>")).tokenize())
    assert tokens[0].type == TokenType.TENANT_HOST
    assert tokens[0].value == "tenant_host"


TENANT_HOST_DSL = """
module test_tenant
app test_tenant "Test"

entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    canonical_hosts: [www.example.com, example.com]
    cookie_scope: host
    super_admin_role: admin
    history_entity: TrustSlugHistory
    not_found_template: pkg.tpl:render_404
    expired_template: pkg.tpl:render_410
    order: 1
""".lstrip()


def test_parser_extracts_full_tenant_host_block():
    _module, _app, _title, _config, _uses, fragment = parse_dsl(TENANT_HOST_DSL, Path("<test>"))
    trust = next(e for e in fragment.entities if e.name == "Trust")
    th = trust.tenant_host
    assert th is not None
    assert th.domain == "example.com"
    assert th.slug_field == "slug"
    assert th.canonical_hosts == ["www.example.com", "example.com"]
    assert th.cookie_scope == "host"
    assert th.super_admin_role == "admin"
    assert th.history_entity == "TrustSlugHistory"
    assert th.not_found_template == "pkg.tpl:render_404"
    assert th.expired_template == "pkg.tpl:render_410"
    assert th.order == 1


def test_parser_defaults_when_block_minimal():
    src = """
module test_tenant
app test_tenant "Test"

entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
""".lstrip()
    _m, _a, _t, _c, _u, fragment = parse_dsl(src, Path("<test>"))
    trust = next(e for e in fragment.entities if e.name == "Trust")
    assert trust.tenant_host is not None
    assert trust.tenant_host.canonical_hosts == []
    assert trust.tenant_host.cookie_scope == "host"
    assert trust.tenant_host.order is None


def test_middleware_class_is_importable():
    """The middleware class is importable (slice 3 supersedes the slice-1 stub)."""
    from dazzle.http.runtime.tenant.middleware import TenantResolutionMiddleware

    assert TenantResolutionMiddleware is not None


def test_membership_gated_defaults_true():
    """#1418: tenant_host gates membership-login by default (back-compat)."""
    assert ir.TenantHostSpec(domain="example.com", slug_field="slug").membership_gated is True


def test_parser_extracts_membership_gated_false():
    """#1418: `membership_gated: false` opts the host out of membership-gated login."""
    src = """
module t
app t "T"
entity Org:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    membership_gated: false
""".lstrip()
    _m, _a, _t, _c, _u, fragment = parse_dsl(src, Path("<test>"))
    org = next(e for e in fragment.entities if e.name == "Org")
    assert org.tenant_host is not None
    assert org.tenant_host.membership_gated is False


def test_parser_rejects_non_bool_membership_gated():
    """#1418: a non-true/false value is a parse error."""
    src = """
module t
app t "T"
entity Org:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    domain: example.com
    slug_field: slug
    membership_gated: maybe
""".lstrip()
    with pytest.raises(Exception, match="membership_gated expects true/false"):
        parse_dsl(src, Path("<test>"))
