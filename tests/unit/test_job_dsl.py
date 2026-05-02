"""Tests for the `job` DSL block (#953 cycle 1).

Covers parsing + linker propagation. Runtime queue + worker land in
cycle 3 — these tests pin the surface contract so the runtime can't
silently change what the parser captures.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from dazzle.core.ir import JobBackoff


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


class TestTriggeredJob:
    """Entity-event triggered jobs."""

    def test_basic_on_create(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Manuscript "Manuscript":
              id: uuid pk
              source_pdf: str(500)

            job thumbnail_render "Generate thumbnail":
              trigger: on_create Manuscript
              run: scripts/render_thumbnail.py
              timeout: 60s
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "thumbnail_render")
        assert job.title == "Generate thumbnail"
        assert job.run == "scripts/render_thumbnail.py"
        assert len(job.triggers) == 1
        assert job.triggers[0].entity == "Manuscript"
        assert job.triggers[0].event == "created"
        assert job.timeout_seconds == 60
        assert job.schedule is None

    def test_field_changed_trigger(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Order "Order":
              id: uuid pk
              status: str(20)

            job order_status_changed "Order status notification":
              trigger: on_field_changed Order.status
              run: scripts/order_notify.py
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "order_status_changed")
        assert job.triggers[0].event == "field_changed"
        assert job.triggers[0].field == "status"

    def test_when_condition_captured_as_text(self, parse_dsl, tmp_path):
        """Cycle 1: condition is captured as raw text. Cycle 3 wires
        the evaluator."""
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Manuscript "Manuscript":
              id: uuid pk
              source_pdf: str(500)

            job thumbnail_render "Generate thumbnail":
              trigger: on_create Manuscript when source_pdf is_set
              run: scripts/render_thumbnail.py
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "thumbnail_render")
        assert job.triggers[0].when_condition == "source_pdf is_set"

    def test_multiple_triggers(self, parse_dsl, tmp_path):
        """A job can react to several entity events."""
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Doc "Document":
              id: uuid pk

            job index_doc "Index document":
              trigger: on_create Doc
              trigger: on_update Doc
              run: scripts/index.py
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "index_doc")
        assert [t.event for t in job.triggers] == ["created", "updated"]


class TestScheduledJob:
    def test_cron_schedule(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            job daily_summary "Daily metrics roll-up":
              schedule: cron("0 1 * * *")
              run: scripts/daily_summary.py
              timeout: 5m
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "daily_summary")
        assert job.schedule is not None
        assert job.schedule.cron == "0 1 * * *"
        assert job.timeout_seconds == 300  # 5m → 300s
        assert job.triggers == []


class TestRetryAndDeadLetter:
    def test_retry_count(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Doc "Document":
              id: uuid pk

            job risky "Risky":
              trigger: on_create Doc
              run: scripts/risky.py
              retry: 5
              retry_backoff: linear
              dead_letter: DocDeadLetter
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "risky")
        assert job.retry == 5
        assert job.retry_backoff == JobBackoff.LINEAR
        assert job.dead_letter == "DocDeadLetter"

    def test_default_retry_is_three(self, parse_dsl, tmp_path):
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Doc "Document":
              id: uuid pk

            job j "j":
              trigger: on_create Doc
              run: scripts/j.py
            """,
            tmp_path,
        )
        job = next(j for j in appspec.jobs if j.name == "j")
        assert job.retry == 3
        assert job.retry_backoff == JobBackoff.EXPONENTIAL


class TestErrors:
    def test_missing_trigger_and_schedule_raises(self, parse_dsl, tmp_path):
        from dazzle.core.errors import ParseError

        with pytest.raises(ParseError, match="trigger.*schedule"):
            parse_dsl(
                """
                module test
                app jobs_test "Jobs Test"

                entity Doc "Document":
                  id: uuid pk

                job orphan "Orphan":
                  run: scripts/x.py
                """,
                tmp_path,
            )


class TestAppSpecPropagation:
    def test_jobs_land_in_appspec(self, parse_dsl, tmp_path):
        """Linker must propagate jobs from module fragment → AppSpec.
        Pre-fix the same gap was caught for notifications in #952 cycle 1."""
        appspec = parse_dsl(
            """
            module test
            app jobs_test "Jobs Test"

            entity Doc "Document":
              id: uuid pk

            job a "A":
              trigger: on_create Doc
              run: scripts/a.py

            job b "B":
              schedule: cron("0 0 * * *")
              run: scripts/b.py
            """,
            tmp_path,
        )
        names = sorted(j.name for j in appspec.jobs)
        assert names == ["a", "b"]


class TestImmutability:
    def test_job_spec_is_frozen(self):
        from pydantic import ValidationError

        from dazzle.core.ir import JobSpec, JobTrigger

        spec = JobSpec(
            name="x",
            triggers=[JobTrigger(entity="Doc", event="created")],
            run="scripts/x.py",
        )
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            spec.run = "scripts/y.py"  # type: ignore[misc]


def test_ir_exports_job_types() -> None:
    """`from dazzle.core.ir import JobSpec` works."""
    from dazzle.core.ir import JobBackoff, JobSchedule, JobSpec, JobTrigger

    assert JobSpec.__name__ == "JobSpec"
    assert JobBackoff.EXPONENTIAL.value == "exponential"
    assert JobTrigger.__name__ == "JobTrigger"
    assert JobSchedule.__name__ == "JobSchedule"
