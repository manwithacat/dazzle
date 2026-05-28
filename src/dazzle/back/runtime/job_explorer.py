"""
Job Explorer routes for runtime inspection.

Provides /_dazzle/jobs/* endpoints for inspecting the background-job
subsystem (#953) — declared jobs, recent ``JobRun`` rows, and runs that
exhausted their retries (``dead_letter``).

This is the job-system analogue of ``event_explorer.py``'s
``/_dazzle/events/*`` endpoints. Like the event explorer, these
endpoints are always available in development mode (localhost) and
carry no auth dependency — they mirror the event explorer's exact
route-shape and (absent) auth gating.
"""

import logging
from datetime import datetime
from functools import partial
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Terminal-failure JobRun statuses — runs that exhausted retries without
# succeeding. ``dead_letter`` is the cycle-1 spec status for runs with no
# JobSpec.dead_letter entity declared; ``failed`` is the generic terminal
# failure. Mirrors JOB_RUN_FIELDS' status enum in core/ir/jobs.py.
_DEAD_LETTER_STATUSES = ("dead_letter", "failed")


@runtime_checkable
class JobRunService(Protocol):
    """Protocol for the ``JobRun`` CRUD service methods the explorer uses.

    Satisfied by ``service_generator.CRUDService`` — the auto-generated
    service wrapping the framework ``JobRun`` system entity (#953 cycle 2).
    """

    async def list(
        self,
        page: int = ...,
        page_size: int = ...,
        filters: dict[str, Any] | None = ...,
        sort: list[str] | None = ...,
    ) -> dict[str, Any]: ...


# =============================================================================
# Response Models
# =============================================================================


class JobSystemStatus(BaseModel):
    """Overall job system status."""

    jobs_declared: int
    total_runs: int
    runs_by_status: dict[str, int] = Field(default_factory=dict)
    dead_letter_count: int = 0


class JobRunSummary(BaseModel):
    """Summary of a single ``JobRun`` row for listing."""

    job_run_id: str
    job_name: str
    status: str
    attempt: int
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    created_at: str | None = None


class JobListResponse(BaseModel):
    """Response for the recent-runs endpoint."""

    runs: list[JobRunSummary]
    total: int
    limit: int


class JobDeadLetterResponse(BaseModel):
    """Response for the dead-letter endpoint.

    Lists runs in a terminal-failure state — ``dead_letter`` (retries
    exhausted, no dead-letter entity declared) or ``failed``.
    """

    runs: list[JobRunSummary]
    total: int
    limit: int


# =============================================================================
# Helpers
# =============================================================================


def _as_iso(value: Any) -> str | None:
    """Render a timestamp value as an ISO string, tolerating None / str."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _row_field(row: Any, name: str) -> Any:
    """Read a field from a ``JobRun`` row that may be a model or a dict."""
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _to_summary(row: Any) -> JobRunSummary:
    """Map a ``JobRun`` row (model or dict) to a :class:`JobRunSummary`."""
    return JobRunSummary(
        job_run_id=str(_row_field(row, "id") or ""),
        job_name=str(_row_field(row, "job_name") or ""),
        status=str(_row_field(row, "status") or "unknown"),
        attempt=int(_row_field(row, "attempt_number") or 1),
        error_message=_row_field(row, "error_message"),
        started_at=_as_iso(_row_field(row, "started_at")),
        finished_at=_as_iso(_row_field(row, "finished_at")),
        duration_ms=_row_field(row, "duration_ms"),
        created_at=_as_iso(_row_field(row, "created_at")),
    )


async def _all_runs(service: JobRunService) -> list[Any]:
    """Page through the ``JobRun`` service and return every row."""
    rows: list[Any] = []
    page = 1
    page_size = 200
    while True:
        result = await service.list(page=page, page_size=page_size)
        items = result.get("items", []) if isinstance(result, dict) else []
        rows.extend(items)
        total = result.get("total", len(rows)) if isinstance(result, dict) else len(rows)
        if len(rows) >= total or not items:
            break
        page += 1
    return rows


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _job_system_status(
    service: JobRunService | None,
    jobs_declared: int,
) -> JobSystemStatus:
    """
    Get job system status.

    Returns the count of declared jobs plus ``JobRun`` counts by status.
    """
    if service is None:
        return JobSystemStatus(
            jobs_declared=jobs_declared,
            total_runs=0,
            runs_by_status={},
            dead_letter_count=0,
        )

    rows = await _all_runs(service)
    runs_by_status: dict[str, int] = {}
    for row in rows:
        status = str(_row_field(row, "status") or "unknown")
        runs_by_status[status] = runs_by_status.get(status, 0) + 1

    dead_letter_count = sum(runs_by_status.get(status, 0) for status in _DEAD_LETTER_STATUSES)

    return JobSystemStatus(
        jobs_declared=jobs_declared,
        total_runs=len(rows),
        runs_by_status=runs_by_status,
        dead_letter_count=dead_letter_count,
    )


async def _list_runs(
    service: JobRunService | None,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum runs to return"),
) -> JobListResponse:
    """
    List recent ``JobRun`` rows, newest first.

    Returns runs ordered by creation time descending, capped at ``limit``.
    """
    if service is None:
        return JobListResponse(runs=[], total=0, limit=limit)

    result = await service.list(
        page=1,
        page_size=limit,
        sort=["-created_at"],
    )
    items = result.get("items", []) if isinstance(result, dict) else []
    total = result.get("total", len(items)) if isinstance(result, dict) else len(items)

    return JobListResponse(
        runs=[_to_summary(row) for row in items],
        total=total,
        limit=limit,
    )


async def _dead_letter_runs(
    service: JobRunService | None,
    limit: int = Query(default=20, ge=1, le=100, description="Maximum runs to return"),
) -> JobDeadLetterResponse:
    """
    List ``JobRun`` rows in a terminal-failure state.

    Returns runs whose status is ``dead_letter`` or ``failed`` — jobs that
    exhausted their retries without succeeding.
    """
    if service is None:
        return JobDeadLetterResponse(runs=[], total=0, limit=limit)

    rows = await _all_runs(service)
    failed = [row for row in rows if str(_row_field(row, "status") or "") in _DEAD_LETTER_STATUSES]
    failed.sort(key=lambda r: str(_row_field(r, "created_at") or ""), reverse=True)
    total = len(failed)

    return JobDeadLetterResponse(
        runs=[_to_summary(row) for row in failed[:limit]],
        total=total,
        limit=limit,
    )


# =============================================================================
# Job Explorer Routes
# =============================================================================


def create_job_explorer_routes(
    service: JobRunService | None,
    jobs_declared: int = 0,
) -> APIRouter:
    """
    Create job explorer routes for runtime inspection.

    Args:
        service: The ``JobRun`` CRUD service (may be None if the job
            subsystem is inactive).
        jobs_declared: Number of ``job`` blocks declared in the AppSpec.

    Returns:
        APIRouter with job explorer endpoints.
    """
    router = APIRouter(prefix="/_dazzle/jobs", tags=["Job Explorer"])

    router.add_api_route(
        "",
        partial(_job_system_status, service, jobs_declared),
        methods=["GET"],
        response_model=JobSystemStatus,
    )
    router.add_api_route(
        "/runs",
        partial(_list_runs, service),
        methods=["GET"],
        response_model=JobListResponse,
    )
    router.add_api_route(
        "/dead-letter",
        partial(_dead_letter_runs, service),
        methods=["GET"],
        response_model=JobDeadLetterResponse,
    )

    return router
