"""DSL → linker → router integration tests for `signable: true` (#1283 phase 5).

These tests close the gap between the unit-level tests (which
hand-build ``EntitySpec`` instances) and a real boot — they parse DSL
source, run it through ``build_appspec``, and then exercise the
signing-router factory against the linked AppSpec.

The DB layer is deliberately out of scope here; that's an E2E test
fixture that needs Postgres provisioning. The flows we cover are the
ones unit tests can't see:

* The 11 framework-canonical fields are injected by the *real* linker
  pass, not the unit-level direct call.
* The ``audit: AuditConfig(enabled=True)`` default fires on a real
  ``EntitySpec`` that the parser produced.
* The router factory accepts the linked entities and emits the
  expected route table.
* The factory returns ``None`` when no entity in the linked AppSpec
  is signable.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402

from dazzle.core import ir  # noqa: E402
from dazzle.core.linker import build_appspec  # noqa: E402
from dazzle.core.parser import parse_modules  # noqa: E402
from dazzle.signing.routes import create_signing_routes  # noqa: E402


def _parse_appspec(source: str, tmp_path: pathlib.Path) -> ir.AppSpec:
    dsl_path = tmp_path / "test.dsl"
    dsl_path.write_text(textwrap.dedent(source).lstrip())
    return build_appspec(parse_modules([dsl_path]), "test")


_SIGNABLE_DSL = """
module test
app a "A"

entity Contract "Contract":
  id: uuid pk
  party: str(200) required
  effective_date: date
  signable: true
  signing_validator: app.signing.validators.verify
"""


_NON_SIGNABLE_DSL = """
module test
app a "A"

entity Task "Task":
  id: uuid pk
  title: str(200) required
"""


# -- IR-level linker assertions ---------------------------------------


class TestLinkerInjection:
    def test_linker_injects_11_fields_via_build_appspec(self, tmp_path) -> None:
        appspec = _parse_appspec(_SIGNABLE_DSL, tmp_path)
        contract = next(e for e in appspec.domain.entities if e.name == "Contract")
        names = {f.name for f in contract.fields}
        for expected in (
            "status",
            "signing_service",
            "signing_url",
            "signed_document",
            "signing_token_hash",
            "signer_ip",
            "signer_user_agent",
            "sent_at",
            "viewed_at",
            "signed_at",
            "expires_at",
        ):
            assert expected in names, f"linker did not inject {expected!r}"

    def test_signable_flag_survives_linker(self, tmp_path) -> None:
        appspec = _parse_appspec(_SIGNABLE_DSL, tmp_path)
        contract = next(e for e in appspec.domain.entities if e.name == "Contract")
        assert contract.signable is True
        assert contract.signing_validator == "app.signing.validators.verify"

    def test_audit_default_enabled_when_unset(self, tmp_path) -> None:
        appspec = _parse_appspec(_SIGNABLE_DSL, tmp_path)
        contract = next(e for e in appspec.domain.entities if e.name == "Contract")
        assert contract.audit is not None
        assert contract.audit.enabled is True

    def test_non_signable_entity_untouched(self, tmp_path) -> None:
        appspec = _parse_appspec(_NON_SIGNABLE_DSL, tmp_path)
        task = next(e for e in appspec.domain.entities if e.name == "Task")
        names = {f.name for f in task.fields}
        # No auto-injected signing fields on a non-signable entity.
        assert names == {"id", "title"}
        assert task.signable is False
        assert task.audit is None


# -- Router factory against the linked AppSpec ------------------------


class TestRouterFromAppSpec:
    def test_router_mounts_when_signable_entity_present(self, tmp_path) -> None:
        appspec = _parse_appspec(_SIGNABLE_DSL, tmp_path)
        router = create_signing_routes(list(appspec.domain.entities), repositories={})
        assert router is not None

        app = FastAPI()
        app.include_router(router)
        paths = {
            (route.path, tuple(sorted(route.methods)))
            for route in app.routes
            if hasattr(route, "methods")
        }
        assert ("/sign/{entity_name}/{record_id}", ("GET",)) in paths
        assert ("/api/sign/{entity_name}/{record_id}", ("POST",)) in paths

    def test_router_returns_none_when_no_signable_entity(self, tmp_path) -> None:
        appspec = _parse_appspec(_NON_SIGNABLE_DSL, tmp_path)
        router = create_signing_routes(list(appspec.domain.entities), repositories={})
        assert router is None

    def test_signable_false_explicit_is_not_signable(self, tmp_path) -> None:
        """A `signable: false` declaration should leave the entity off the
        signable list — same as omitting the directive entirely."""
        appspec = _parse_appspec(
            """
            module test
            app a "A"

            entity Doc "Doc":
              id: uuid pk
              title: str(200) required
              signable: false
            """,
            tmp_path,
        )
        router = create_signing_routes(list(appspec.domain.entities), repositories={})
        assert router is None


# -- Project-declared field wins over auto-inject ---------------------


class TestProjectOverridesViaDSL:
    def test_project_status_enum_wins(self, tmp_path) -> None:
        """If the project declares its own `status` field, the linker
        must leave it alone — explicit always beats auto-inject."""
        appspec = _parse_appspec(
            """
            module test
            app a "A"

            entity Contract "C":
              id: uuid pk
              party: str(200) required
              status: enum[draft, signed_remote, signed_in_person, archived] required
              signable: true
            """,
            tmp_path,
        )
        contract = next(e for e in appspec.domain.entities if e.name == "Contract")
        status = next(f for f in contract.fields if f.name == "status")
        assert status.type.enum_values == [
            "draft",
            "signed_remote",
            "signed_in_person",
            "archived",
        ]

    def test_project_signing_url_widened(self, tmp_path) -> None:
        """A project that needs a longer signing_url cap can declare it
        explicitly; the linker keeps the wider field."""
        appspec = _parse_appspec(
            """
            module test
            app a "A"

            entity Contract "C":
              id: uuid pk
              party: str(200) required
              signing_url: str(2000)
              signable: true
            """,
            tmp_path,
        )
        contract = next(e for e in appspec.domain.entities if e.name == "Contract")
        url = next(f for f in contract.fields if f.name == "signing_url")
        assert url.type.max_length == 2000
