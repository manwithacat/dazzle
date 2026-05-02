"""Tests for the `audit` DSL block (#956 cycle 1).

Covers parsing + linker propagation. Cycle 2-6 wires runtime
(auto-generated AuditEntry, repository hooks, history region rendering,
RBAC, retention sweep). These tests pin the surface contract so later
cycles can extend without DSL re-authoring.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest


@pytest.fixture()
def parse_dsl():
    """Parse DSL source → AppSpec."""
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    def _parse(source: str, tmp_path: pathlib.Path):
        dsl_path = tmp_path / "test.dsl"
        dsl_path.write_text(textwrap.dedent(source).lstrip())
        modules = parse_modules([dsl_path])
        return build_appspec(modules, "test")

    return _parse


class TestBasicAudit:
    def test_minimal_audit(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              status: str(20)

            audit on Manuscript:
              track: status
            """,
            tmp_path,
        )
        audit = appspec.audits[0]
        assert audit.entity == "Manuscript"
        assert audit.track == ["status"]
        assert audit.show_to.kind == "persona"
        assert audit.show_to.personas == []
        assert audit.retention_days == 0  # 0 = forever

    def test_track_multiple_fields(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)
              title: str(200)
              owner_id: uuid

            audit on Doc:
              track: status, title, owner_id
            """,
            tmp_path,
        )
        assert appspec.audits[0].track == ["status", "title", "owner_id"]


class TestShowTo:
    def test_persona_list(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            audit on Doc:
              track: status
              show_to: persona(teacher, admin)
            """,
            tmp_path,
        )
        assert appspec.audits[0].show_to.personas == ["teacher", "admin"]

    def test_unknown_show_to_kind_rejected(self, parse_dsl, tmp_path):
        from dazzle.core.errors import ParseError

        with pytest.raises(ParseError, match="show_to kind"):
            parse_dsl(
                """
                module test
                app a "A"

                entity Doc "D":
                  id: uuid pk

                audit on Doc:
                  track: status
                  show_to: role(admin)
                """,
                tmp_path,
            )


class TestRetention:
    def test_days_literal(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            audit on Doc:
              track: status
              retention: 90d
            """,
            tmp_path,
        )
        assert appspec.audits[0].retention_days == 90

    def test_hours_floor_to_days(self, parse_dsl, tmp_path):
        """Sub-day retention rounds down — cycle 6 sweep runs daily,
        so 23h is functionally identical to 0d."""
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            audit on Doc:
              track: status
              retention: 23h
            """,
            tmp_path,
        )
        assert appspec.audits[0].retention_days == 0

    def test_plain_integer_treated_as_days(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            audit on Doc:
              track: status
              retention: 365
            """,
            tmp_path,
        )
        assert appspec.audits[0].retention_days == 365


class TestLinkerPropagation:
    def test_audit_lands_in_appspec(self, parse_dsl, tmp_path):
        """Linker must propagate audits from module fragment → AppSpec.
        Same gate that caught #952 + #953 gaps in cycle 1."""
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            audit on Doc:
              track: status
              retention: 30d
            """,
            tmp_path,
        )
        assert len(appspec.audits) == 1

    def test_duplicate_audit_per_entity_rejected(self, parse_dsl, tmp_path):
        from dazzle.core.errors import LinkError

        with pytest.raises(LinkError, match="Duplicate audit"):
            parse_dsl(
                """
                module test
                app a "A"

                entity Doc "D":
                  id: uuid pk
                  status: str(20)

                audit on Doc:
                  track: status

                audit on Doc:
                  track: status
                """,
                tmp_path,
            )

    def test_audits_for_different_entities_coexist(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Doc "D":
              id: uuid pk
              status: str(20)

            entity Order "O":
              id: uuid pk
              state: str(20)

            audit on Doc:
              track: status

            audit on Order:
              track: state
            """,
            tmp_path,
        )
        entities = sorted(a.entity for a in appspec.audits)
        assert entities == ["Doc", "Order"]


class TestImmutability:
    def test_audit_spec_is_frozen(self):
        from pydantic import ValidationError

        from dazzle.core.ir import AuditSpec

        spec = AuditSpec(entity="Doc", track=["status"])
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            spec.entity = "Other"  # type: ignore[misc]


def test_ir_exports_audit_types() -> None:
    """`from dazzle.core.ir import AuditSpec` works."""
    from dazzle.core.ir import AuditShowTo, AuditSpec

    assert AuditSpec.__name__ == "AuditSpec"
    assert AuditShowTo.__name__ == "AuditShowTo"
