"""Tests for the cycle-1 #957 multi-tenancy extensions.

The existing `tenancy:` block already covers isolation mode +
partition key + provisioning + topic namespacing. Cycle 1 adds two
declarations:

  * `admin_personas:` — persona names whose grants bypass the tenant
    scope filter. Cycle 2 wires this into Cedar policy generation.
  * `per_tenant_config:` — key→type map for per-tenant configuration
    (locale / theme / feature flags). Cycle 4 stores values on a
    framework Tenant entity.

These tests pin the surface so cycles 2-5 can extend without DSL
re-authoring.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest


@pytest.fixture()
def parse_dsl():
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path):
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


class TestAdminPersonas:
    def test_admin_personas_list(self, parse_dsl, tmp_path):
        parse_dsl(
            """
            module test
            app a "A"

            tenancy:
              mode: shared_schema
              admin_personas: [super_admin, support]

            entity Doc "D":
              id: uuid pk
            """,
            tmp_path,
        )
        # `tenancy` lives on each module's fragment.tenancy, but the
        # AppSpec doesn't currently hoist it as a top-level field —
        # the cycle 1 contract is parser captures it; cycle 2 wires
        # the linker propagation. Read directly from the parsed
        # module fragment for now via a fresh parse.
        from dazzle.core.parser import parse_modules

        dsl_path = tmp_path / "test.dsl"
        modules = parse_modules([dsl_path])
        tenancy = modules[0].fragment.tenancy
        assert tenancy is not None
        assert tenancy.admin_personas == ["super_admin", "support"]

    def test_admin_personas_default_empty(self, parse_dsl, tmp_path):
        from dazzle.core.parser import parse_modules

        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(
            textwrap.dedent(
                """
                module test
                app a "A"

                tenancy:
                  mode: shared_schema

                entity Doc "D":
                  id: uuid pk
                """
            ).lstrip()
        )
        modules = parse_modules([dsl_path])
        tenancy = modules[0].fragment.tenancy
        assert tenancy is not None
        assert tenancy.admin_personas == []


class TestPerTenantConfig:
    def test_basic_config_keys(self, tmp_path):
        from dazzle.core.parser import parse_modules

        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(
            textwrap.dedent(
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
                """
            ).lstrip()
        )
        modules = parse_modules([dsl_path])
        tenancy = modules[0].fragment.tenancy
        assert tenancy is not None
        assert tenancy.per_tenant_config == {
            "locale": "str",
            "theme": "str",
            "feature_billing": "bool",
        }

    def test_per_tenant_config_default_empty(self, tmp_path):
        from dazzle.core.parser import parse_modules

        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(
            textwrap.dedent(
                """
                module test
                app a "A"

                tenancy:
                  mode: shared_schema

                entity Doc "D":
                  id: uuid pk
                """
            ).lstrip()
        )
        modules = parse_modules([dsl_path])
        tenancy = modules[0].fragment.tenancy
        assert tenancy is not None
        assert tenancy.per_tenant_config == {}


class TestCombined:
    def test_both_extensions_together(self, tmp_path):
        from dazzle.core.parser import parse_modules

        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(
            textwrap.dedent(
                """
                module test
                app a "A"

                tenancy:
                  mode: shared_schema
                  partition_key: tenant_id
                  admin_personas: [super_admin]
                  per_tenant_config:
                    locale: str
                    theme: str

                entity Doc "D":
                  id: uuid pk
                """
            ).lstrip()
        )
        modules = parse_modules([dsl_path])
        tenancy = modules[0].fragment.tenancy
        assert tenancy is not None
        # Existing fields preserved
        assert tenancy.isolation.mode.value == "shared_schema"
        assert tenancy.isolation.partition_key == "tenant_id"
        # New cycle-1 fields populated
        assert tenancy.admin_personas == ["super_admin"]
        assert tenancy.per_tenant_config == {"locale": "str", "theme": "str"}


class TestImmutability:
    def test_tenancy_spec_is_frozen(self):
        from pydantic import ValidationError

        from dazzle.core.ir import TenancySpec

        spec = TenancySpec(admin_personas=["x"], per_tenant_config={"k": "str"})
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            spec.admin_personas = ["y"]  # type: ignore[misc]


def test_ir_exports_new_fields() -> None:
    """`TenancySpec` exposes the new fields on the model schema."""
    from dazzle.core.ir import TenancySpec

    fields = TenancySpec.model_fields
    assert "admin_personas" in fields
    assert "per_tenant_config" in fields
    # Defaults: empty list / empty dict
    spec = TenancySpec()
    assert spec.admin_personas == []
    assert spec.per_tenant_config == {}
