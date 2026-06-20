"""Tests for #1193 — the job explorer route factory.

``create_job_explorer_routes`` is the job-system analogue of
``create_event_explorer_routes``: it exposes ``/_dazzle/jobs/*``
inspection endpoints over the ``JobRun`` system entity (#953).

These tests verify:

  * ``GET /_dazzle/jobs`` returns the declared-job count plus
    ``JobRun`` counts grouped by status.
  * ``GET /_dazzle/jobs/runs`` returns recent runs newest-first and
    honours the ``limit`` query param.
  * ``GET /_dazzle/jobs/dead-letter`` returns only terminal-failure
    runs (``dead_letter`` / ``failed``).
  * The factory tolerates a ``None`` service (job subsystem inactive).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.job_explorer import create_job_explorer_routes

# ---------------------------------------------------------------------------
# Fixtures — a minimal JobRun CRUD-service stub
# ---------------------------------------------------------------------------


def _run(
    run_id: str,
    job_name: str,
    status: str,
    *,
    attempt: int = 1,
    created_at: str = "2026-05-22T00:00:00",
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Build one JobRun row dict matching JOB_RUN_FIELDS."""
    return {
        "id": run_id,
        "job_name": job_name,
        "status": status,
        "attempt_number": attempt,
        "payload": None,
        "error_message": error_message,
        "started_at": created_at,
        "finished_at": created_at if status != "running" else None,
        "duration_ms": duration_ms,
        "created_at": created_at,
    }


class _FakeJobRunService:
    """Stub satisfying the JobRunService protocol — paginated ``list``."""

    entity_name = "JobRun"

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: list[str] | None = None,
    ) -> dict[str, Any]:
        rows = list(self._rows)
        if sort and sort[0] == "-created_at":
            rows.sort(key=lambda r: r["created_at"], reverse=True)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return {
            "items": page_rows,
            "total": len(rows),
            "page": page,
            "page_size": page_size,
        }


_SAMPLE_ROWS = [
    _run("r1", "thumbnail_render", "completed", created_at="2026-05-22T01:00:00"),
    _run("r2", "thumbnail_render", "running", created_at="2026-05-22T02:00:00"),
    _run(
        "r3",
        "daily_summary",
        "failed",
        created_at="2026-05-22T03:00:00",
        error_message="boom",
        attempt=3,
    ),
    _run(
        "r4",
        "daily_summary",
        "dead_letter",
        created_at="2026-05-22T04:00:00",
        error_message="exhausted",
        attempt=4,
    ),
    _run("r5", "thumbnail_render", "completed", created_at="2026-05-22T05:00:00"),
]


@pytest.fixture
def client() -> TestClient:
    """A TestClient over an app mounting the job explorer routes."""
    app = FastAPI()
    service = _FakeJobRunService(_SAMPLE_ROWS)
    app.include_router(create_job_explorer_routes(service, jobs_declared=2))
    return TestClient(app)


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


def test_status_returns_counts(client: TestClient) -> None:
    """GET /_dazzle/jobs returns declared count + runs grouped by status."""
    resp = client.get("/_dazzle/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs_declared"] == 2
    assert body["total_runs"] == 5
    assert body["runs_by_status"] == {
        "completed": 2,
        "running": 1,
        "failed": 1,
        "dead_letter": 1,
    }
    # dead_letter + failed are both terminal-failure states
    assert body["dead_letter_count"] == 2


def test_status_none_service() -> None:
    """A None service yields a zeroed status (subsystem inactive)."""
    app = FastAPI()
    app.include_router(create_job_explorer_routes(None, jobs_declared=3))
    resp = TestClient(app).get("/_dazzle/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs_declared"] == 3
    assert body["total_runs"] == 0
    assert body["runs_by_status"] == {}
    assert body["dead_letter_count"] == 0


# ---------------------------------------------------------------------------
# Recent-runs endpoint
# ---------------------------------------------------------------------------


def test_runs_returns_recent_newest_first(client: TestClient) -> None:
    """GET /_dazzle/jobs/runs returns runs ordered newest-first."""
    resp = client.get("/_dazzle/jobs/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["limit"] == 20
    ids = [r["job_run_id"] for r in body["runs"]]
    assert ids == ["r5", "r4", "r3", "r2", "r1"]
    # field mapping: attempt_number -> attempt
    r3 = next(r for r in body["runs"] if r["job_run_id"] == "r3")
    assert r3["attempt"] == 3
    assert r3["error_message"] == "boom"
    assert r3["status"] == "failed"


def test_runs_honours_limit(client: TestClient) -> None:
    """The limit query param caps how many runs come back."""
    resp = client.get("/_dazzle/jobs/runs", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 2
    assert len(body["runs"]) == 2
    # total still reflects the full row count
    assert body["total"] == 5
    assert [r["job_run_id"] for r in body["runs"]] == ["r5", "r4"]


def test_runs_limit_out_of_range_rejected(client: TestClient) -> None:
    """limit is bounded 1..100 (mirrors the event explorer)."""
    assert client.get("/_dazzle/jobs/runs", params={"limit": 0}).status_code == 422
    assert client.get("/_dazzle/jobs/runs", params={"limit": 999}).status_code == 422


# ---------------------------------------------------------------------------
# Dead-letter endpoint
# ---------------------------------------------------------------------------


def test_dead_letter_returns_only_terminal_failures(client: TestClient) -> None:
    """GET /_dazzle/jobs/dead-letter returns only failed / dead_letter runs."""
    resp = client.get("/_dazzle/jobs/dead-letter")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    statuses = {r["status"] for r in body["runs"]}
    assert statuses == {"failed", "dead_letter"}
    # newest-first ordering
    assert [r["job_run_id"] for r in body["runs"]] == ["r4", "r3"]


def test_dead_letter_honours_limit(client: TestClient) -> None:
    """The dead-letter endpoint honours the limit query param."""
    resp = client.get("/_dazzle/jobs/dead-letter", params={"limit": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["limit"] == 1
    assert len(body["runs"]) == 1
    # total still counts every terminal-failure run
    assert body["total"] == 2
    assert body["runs"][0]["job_run_id"] == "r4"


def test_dead_letter_none_service() -> None:
    """A None service yields an empty dead-letter response."""
    app = FastAPI()
    app.include_router(create_job_explorer_routes(None))
    resp = TestClient(app).get("/_dazzle/jobs/dead-letter")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"] == []
    assert body["total"] == 0
