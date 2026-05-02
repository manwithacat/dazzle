"""Tests for #957 cycle 6 — RouteGenerator threads admin_personas.

End of the integration chain: server.py reads
`appspec.tenancy.admin_personas` and forwards to `RouteGenerator`,
which stashes the list and threads it to `create_list_handler`. From
there cycles 4-5 already cover the runtime path.

These tests verify the plumbing is intact — `RouteGenerator.admin_personas`
is populated and an empty default keeps the cycle-5 behaviour exactly.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def stub_route_generator_args():
    """Minimal kwargs for `RouteGenerator(...)` — values are mocks since
    we only check the admin_personas plumbing, not route generation."""
    return {
        "services": {},
        "models": {},
    }


def test_admin_personas_default_empty(stub_route_generator_args):
    from dazzle_back.runtime.route_generator import RouteGenerator

    rg = RouteGenerator(**stub_route_generator_args)
    assert rg.admin_personas == []


def test_admin_personas_explicit_list_stored(stub_route_generator_args):
    from dazzle_back.runtime.route_generator import RouteGenerator

    rg = RouteGenerator(
        admin_personas=["super_admin", "support"],
        **stub_route_generator_args,
    )
    assert rg.admin_personas == ["super_admin", "support"]


def test_admin_personas_none_normalises_to_empty_list(stub_route_generator_args):
    from dazzle_back.runtime.route_generator import RouteGenerator

    rg = RouteGenerator(admin_personas=None, **stub_route_generator_args)
    assert rg.admin_personas == []


def test_admin_personas_copy_not_alias(stub_route_generator_args):
    """Mutating the caller's list must not bleed into the route generator."""
    from dazzle_back.runtime.route_generator import RouteGenerator

    src = ["super_admin"]
    rg = RouteGenerator(admin_personas=src, **stub_route_generator_args)
    src.append("support")  # mutate the original
    assert rg.admin_personas == ["super_admin"]


class TestServerIntegration:
    """Verify server.py extracts admin_personas from the linked AppSpec."""

    def test_extraction_with_tenancy(self):
        # Mirror the snippet in server.py:
        #   _admin_personas = list(self._appspec.tenancy.admin_personas)
        # — confirm the code path picks up cycle-3's linker propagation.
        import pathlib
        import tempfile
        import textwrap

        from dazzle.core.linker import build_appspec
        from dazzle.core.parser import parse_modules

        with tempfile.TemporaryDirectory() as td:
            dsl_path = pathlib.Path(td) / "test.dsl"
            dsl_path.write_text(
                textwrap.dedent(
                    """
                    module test
                    app a "A"

                    tenancy:
                      mode: shared_schema
                      admin_personas: [super_admin, support]

                    entity Doc "D":
                      id: uuid pk
                    """
                ).lstrip()
            )
            modules = parse_modules([dsl_path])
            appspec = build_appspec(modules, "test")

        assert appspec.tenancy is not None
        admin_personas = list(appspec.tenancy.admin_personas)
        assert admin_personas == ["super_admin", "support"]

    def test_extraction_without_tenancy(self):
        import pathlib
        import tempfile
        import textwrap

        from dazzle.core.linker import build_appspec
        from dazzle.core.parser import parse_modules

        with tempfile.TemporaryDirectory() as td:
            dsl_path = pathlib.Path(td) / "test.dsl"
            dsl_path.write_text(
                textwrap.dedent(
                    """
                    module test
                    app a "A"

                    entity Doc "D":
                      id: uuid pk
                    """
                ).lstrip()
            )
            modules = parse_modules([dsl_path])
            appspec = build_appspec(modules, "test")

        # server.py uses the `if appspec.tenancy:` guard — confirm the
        # missing-tenancy case stays None so callers can default to [].
        assert appspec.tenancy is None
