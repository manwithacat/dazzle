"""Tests for #991 fix — admin LIST surfaces for AuditEntry + JobRun.

Pre-fix, the cycle-2 system entities had no auto-generated
admin surface, so the route generator emitted no CRUD endpoints.
The audit-history region worked in-process but external
inspection (`curl /auditentries?entity_type=Ticket`) was
impossible without the user authoring a surface manually.

The linker now builds an admin LIST surface for each platform
entity it auto-injects, mirroring the FeedbackReport pattern.
The route generator picks them up naturally and emits the
expected CRUD URLs.
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
        return build_appspec(parse_modules([dsl_path]), "test")

    return _parse


# ---------------------------------------------------------------------------
# AuditEntry admin surface
# ---------------------------------------------------------------------------


class TestAuditEntryAdminSurface:
    def test_surface_injected_when_audit_block_present(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
              status: str(50)

            audit on Ticket:
              track: status
              show_to: persona(admin)
            """,
            tmp_path,
        )
        names = {s.name for s in appspec.surfaces}
        assert "auditentry_admin" in names

    def test_surface_not_injected_without_audit_blocks(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
            """,
            tmp_path,
        )
        names = {s.name for s in appspec.surfaces}
        assert "auditentry_admin" not in names
        # And the entity itself is also absent — cycle 2 only injects
        # AuditEntry when there's an audit block to populate it.
        entity_names = {e.name for e in appspec.domain.entities}
        assert "AuditEntry" not in entity_names

    def test_surface_shape(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
              status: str(50)

            audit on Ticket:
              track: status
              show_to: persona(admin)
            """,
            tmp_path,
        )
        surface = next(s for s in appspec.surfaces if s.name == "auditentry_admin")
        from dazzle.core.ir.surfaces import SurfaceMode

        assert surface.entity_ref == "AuditEntry"
        assert surface.mode == SurfaceMode.LIST
        assert surface.title == "Audit Entries"
        # UX-decorated so route gen wires sort + filter + search.
        assert surface.ux is not None
        assert any(s.field == "at" for s in surface.ux.sort)
        assert "entity_type" in surface.ux.filter
        # The displayed columns should help the operator triage rows.
        field_names = {e.field_name for e in surface.sections[0].elements}
        assert {"at", "entity_type", "operation", "by_user_id"} <= field_names


# ---------------------------------------------------------------------------
# JobRun admin surface
# ---------------------------------------------------------------------------


class TestJobRunAdminSurface:
    def test_surface_injected_when_job_block_present(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk

            job daily "Daily":
              schedule: cron("0 1 * * *")
              run: app.jobs:daily
            """,
            tmp_path,
        )
        names = {s.name for s in appspec.surfaces}
        assert "jobrun_admin" in names

    def test_surface_not_injected_without_job_blocks(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
            """,
            tmp_path,
        )
        names = {s.name for s in appspec.surfaces}
        assert "jobrun_admin" not in names
        entity_names = {e.name for e in appspec.domain.entities}
        assert "JobRun" not in entity_names

    def test_surface_shape(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk

            job daily "Daily":
              schedule: cron("0 1 * * *")
              run: app.jobs:daily
            """,
            tmp_path,
        )
        surface = next(s for s in appspec.surfaces if s.name == "jobrun_admin")
        from dazzle.core.ir.surfaces import SurfaceMode

        assert surface.entity_ref == "JobRun"
        assert surface.mode == SurfaceMode.LIST
        assert surface.title == "Job Runs"
        assert surface.ux is not None
        assert any(s.field == "created_at" for s in surface.ux.sort)
        assert "status" in surface.ux.filter
        field_names = {e.field_name for e in surface.sections[0].elements}
        # Must include the columns operators triage on most.
        assert {"job_name", "status", "attempt_number", "duration_ms"} <= field_names


# ---------------------------------------------------------------------------
# Combined — both surfaces present when both blocks declared
# ---------------------------------------------------------------------------


class TestCombined:
    def test_both_surfaces_when_audit_and_jobs_declared(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Ticket "T":
              id: uuid pk
              status: str(50)

            audit on Ticket:
              track: status
              show_to: persona(admin)

            job daily "Daily":
              schedule: cron("0 1 * * *")
              run: app.jobs:daily
            """,
            tmp_path,
        )
        names = {s.name for s in appspec.surfaces}
        assert "auditentry_admin" in names
        assert "jobrun_admin" in names
