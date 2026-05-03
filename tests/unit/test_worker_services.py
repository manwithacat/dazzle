"""Tests for worker service wiring (#992).

The standalone `dazzle worker` previously passed `services={}` to
the worker + retention loops, so JobRun status transitions logged
but didn't persist, and retention sweeps were no-ops. The new
`build_worker_services` helper builds CRUD services for the
platform entities the loops actually write through.

These tests exercise the entity-selection logic without standing
up Postgres — the actual repo + service wiring is a thin
combination of code already covered elsewhere. The risk this fix
re-introduces is the *selection logic*: building services for
entities the AppSpec doesn't have, or building none when audit/job
blocks are present.
"""

from __future__ import annotations

import pathlib
import textwrap
from unittest.mock import MagicMock, patch

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


def test_no_jobrun_or_auditentry_returns_empty_services(parse_dsl, tmp_path):
    appspec = parse_dsl(
        """
        module test
        app a "A"

        entity Ticket "T":
          id: uuid pk
        """,
        tmp_path,
    )
    from dazzle_back.runtime.worker_services import build_worker_services

    fake_pg = MagicMock()
    with patch("dazzle_back.runtime.worker_services.PostgresBackend", return_value=fake_pg):
        services, db = build_worker_services(appspec, "postgresql://x")
    assert services == {}
    # We still hand back a live db_manager so caller's shutdown is uniform.
    assert db is fake_pg
    fake_pg.open_pool.assert_called_once()


def test_audit_block_yields_auditentry_service(parse_dsl, tmp_path):
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
    from dazzle_back.runtime.worker_services import build_worker_services

    fake_pg = MagicMock()
    with patch("dazzle_back.runtime.worker_services.PostgresBackend", return_value=fake_pg):
        services, _ = build_worker_services(appspec, "postgresql://x")

    assert "AuditEntry" in services
    assert "JobRun" not in services  # no job blocks → no JobRun service


def test_job_block_yields_jobrun_service(parse_dsl, tmp_path):
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
    from dazzle_back.runtime.worker_services import build_worker_services

    fake_pg = MagicMock()
    with patch("dazzle_back.runtime.worker_services.PostgresBackend", return_value=fake_pg):
        services, _ = build_worker_services(appspec, "postgresql://x")

    assert "JobRun" in services
    assert "AuditEntry" not in services


def test_both_blocks_yield_both_services(parse_dsl, tmp_path):
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
    from dazzle_back.runtime.worker_services import build_worker_services

    fake_pg = MagicMock()
    with patch("dazzle_back.runtime.worker_services.PostgresBackend", return_value=fake_pg):
        services, _ = build_worker_services(appspec, "postgresql://x")

    assert {"JobRun", "AuditEntry"} <= set(services.keys())
    # Both services know which entity they target — the worker loop
    # passes services["JobRun"] to process_one for status writes.
    assert services["JobRun"].entity_name == "JobRun"
    assert services["AuditEntry"].entity_name == "AuditEntry"


def test_services_have_repository_wired(parse_dsl, tmp_path):
    """CRUD services without a repository can't perform writes — verify wiring."""
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
    from dazzle_back.runtime.worker_services import build_worker_services

    fake_pg = MagicMock()
    with patch("dazzle_back.runtime.worker_services.PostgresBackend", return_value=fake_pg):
        services, _ = build_worker_services(appspec, "postgresql://x")

    job_service = services["JobRun"]
    # CRUDService uses `_repository` after `set_repository()` is called.
    assert getattr(job_service, "_repository", None) is not None
