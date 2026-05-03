"""Tests for #953 cycle 2 — JobRun system entity auto-generation.

Cycle 1 captured `job X:` blocks onto `ModuleFragment.jobs`. Cycle 2
injects a `JobRun` platform entity into the AppSpec so cycle-3's
worker has a destination table for run records.

The shape mirrors AIJob / AuditEntry: a single shared system entity
discriminated by `job_name`, with one row per worker invocation. The
injection is gated on the presence of at least one `job:` block —
apps without background jobs don't get the table.
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


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------


class TestInjection:
    def test_scheduled_job_triggers_entity_injection(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk

            job daily_summary "Daily roll-up":
              schedule: cron("0 1 * * *")
              run: scripts/daily_summary.py
            """,
            tmp_path,
        )
        names = [e.name for e in appspec.domain.entities]
        assert "JobRun" in names

    def test_triggered_job_triggers_entity_injection(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
              source_pdf: str(500)

            job thumbnail_render "Generate thumbnail":
              trigger: on_create Manuscript
              run: scripts/render_thumbnail.py
            """,
            tmp_path,
        )
        names = [e.name for e in appspec.domain.entities]
        assert "JobRun" in names

    def test_no_jobs_no_injection(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk
            """,
            tmp_path,
        )
        names = [e.name for e in appspec.domain.entities]
        assert "JobRun" not in names

    def test_multiple_jobs_single_job_run(self, parse_dsl, tmp_path):
        # Multiple `job X:` declarations share one JobRun table —
        # discriminated by `job_name` at insertion time.
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk

            job daily_summary "Daily roll-up":
              schedule: cron("0 1 * * *")
              run: scripts/daily.py

            job hourly_metrics "Hourly metrics":
              schedule: cron("0 * * * *")
              run: scripts/hourly.py
            """,
            tmp_path,
        )
        job_runs = [e for e in appspec.domain.entities if e.name == "JobRun"]
        assert len(job_runs) == 1


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestJobRunShape:
    @pytest.fixture()
    def job_run(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk

            job daily_summary "Daily roll-up":
              schedule: cron("0 1 * * *")
              run: scripts/daily.py
            """,
            tmp_path,
        )
        return next(e for e in appspec.domain.entities if e.name == "JobRun")

    def test_required_fields(self, job_run):
        names = {f.name for f in job_run.fields}
        # Every JobRun row needs: pk, job discriminator, status,
        # attempt counter, error/payload columns, timing.
        assert {
            "id",
            "job_name",
            "status",
            "attempt_number",
            "payload",
            "error_message",
            "started_at",
            "finished_at",
            "duration_ms",
            "created_at",
        } <= names

    def test_id_is_pk(self, job_run):
        from dazzle.core.ir.fields import FieldModifier

        id_field = next(f for f in job_run.fields if f.name == "id")
        assert FieldModifier.PK in id_field.modifiers

    def test_status_is_enum(self, job_run):
        status = next(f for f in job_run.fields if f.name == "status")
        assert status.type.kind.value == "enum"

    def test_status_default_pending(self, job_run):
        status = next(f for f in job_run.fields if f.name == "status")
        assert status.default == "pending"

    def test_attempt_number_default_one(self, job_run):
        attempt = next(f for f in job_run.fields if f.name == "attempt_number")
        assert attempt.default == "1"

    def test_created_at_defaults_now(self, job_run):
        created = next(f for f in job_run.fields if f.name == "created_at")
        assert created.default == "now"


# ---------------------------------------------------------------------------
# Domain + permissions
# ---------------------------------------------------------------------------


class TestPlatformDomain:
    @pytest.fixture()
    def job_run(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk

            job daily_summary "Daily":
              schedule: cron("0 1 * * *")
              run: scripts/daily.py
            """,
            tmp_path,
        )
        return next(e for e in appspec.domain.entities if e.name == "JobRun")

    def test_is_platform_entity(self, job_run):
        # Validators / drift gates skip platform-domain entities so
        # the framework can ship them without users having to add
        # scope rules etc.
        assert job_run.domain == "platform"

    def test_has_audit_pattern(self, job_run):
        # Pattern is "system" + "audit" — same as AuditEntry. Used
        # by the framework UI to surface JobRuns under a system /
        # observability nav rather than a user-facing nav.
        assert "audit" in job_run.patterns
        assert "system" in job_run.patterns


class TestAccess:
    @pytest.fixture()
    def job_run(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app a "A"

            entity Manuscript "M":
              id: uuid pk

            job daily_summary "Daily":
              schedule: cron("0 1 * * *")
              run: scripts/daily.py
            """,
            tmp_path,
        )
        return next(e for e in appspec.domain.entities if e.name == "JobRun")

    def test_no_delete_permission(self, job_run):
        # Historical job-run rows are evidence; cycle-6 retention
        # uses a different bulk-delete code path.
        from dazzle.core.ir.domain import PermissionKind

        ops = {p.operation for p in job_run.access.permissions}
        assert PermissionKind.DELETE not in ops

    def test_create_read_list_update_present(self, job_run):
        # Worker needs CREATE + UPDATE (status transitions); admins
        # need READ + LIST for triage.
        from dazzle.core.ir.domain import PermissionKind

        ops = {p.operation for p in job_run.access.permissions}
        assert {
            PermissionKind.CREATE,
            PermissionKind.READ,
            PermissionKind.LIST,
            PermissionKind.UPDATE,
        } <= ops
