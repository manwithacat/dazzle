"""Tests for #957 cycle 3 — linker propagates `tenancy:` to AppSpec.

Cycle 1 captured `TenancySpec` on `ModuleFragment`. Cycle 3 wires the
linker so `build_appspec` carries the merged `tenancy` through to
`AppSpec.tenancy`, which is what the request middleware (cycle 4) will
read to populate `AccessContext.tenant_admin_personas`.

Pre-cycle-3, `AppSpec.tenancy` defaulted to `None` even when modules
declared a `tenancy:` block — the field was simply never wired.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.linker_impl import LinkError
from dazzle.core.parser import parse_modules


def _parse(source: str, tmp_path: pathlib.Path):
    dsl_path = tmp_path / "test.dsl"
    dsl_path.write_text(textwrap.dedent(source).lstrip())
    return parse_modules([dsl_path])


def test_appspec_carries_tenancy(tmp_path):
    modules = _parse(
        """
        module test
        app a "A"

        tenancy:
          mode: shared_schema
          partition_key: tenant_id
          admin_personas: [super_admin, support]

        entity Doc "D":
          id: uuid pk
        """,
        tmp_path,
    )
    appspec = build_appspec(modules, "test")
    assert appspec.tenancy is not None
    assert appspec.tenancy.isolation.mode.value == "shared_schema"
    assert appspec.tenancy.isolation.partition_key == "tenant_id"
    assert appspec.tenancy.admin_personas == ["super_admin", "support"]


def test_appspec_tenancy_none_when_absent(tmp_path):
    modules = _parse(
        """
        module test
        app a "A"

        entity Doc "D":
          id: uuid pk
        """,
        tmp_path,
    )
    appspec = build_appspec(modules, "test")
    assert appspec.tenancy is None


def test_per_tenant_config_propagates(tmp_path):
    modules = _parse(
        """
        module test
        app a "A"

        tenancy:
          mode: shared_schema
          per_tenant_config:
            locale: str
            theme: str
            feature_billing: bool

        entity Doc "D":
          id: uuid pk
        """,
        tmp_path,
    )
    appspec = build_appspec(modules, "test")
    assert appspec.tenancy is not None
    assert appspec.tenancy.per_tenant_config == {
        "locale": "str",
        "theme": "str",
        "feature_billing": "bool",
    }


def test_duplicate_tenancy_blocks_raise(tmp_path):
    a = tmp_path / "a.dsl"
    a.write_text(
        textwrap.dedent(
            """
            module a
            app a "A"

            tenancy:
              mode: shared_schema

            entity Doc "D":
              id: uuid pk
            """
        ).lstrip()
    )
    b = tmp_path / "b.dsl"
    b.write_text(
        textwrap.dedent(
            """
            module b
            uses a

            tenancy:
              mode: schema_per_tenant
            """
        ).lstrip()
    )
    modules = parse_modules([a, b])
    with pytest.raises(LinkError, match="Duplicate tenancy"):
        build_appspec(modules, "a")
