"""Tests for the `tenant_host:` block parser and IR (#1289)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dazzle.core import ir
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
