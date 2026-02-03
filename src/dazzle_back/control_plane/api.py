"""
Control Plane API endpoints.

Provides JSON APIs for metrics, logs, health, processes, and configuration.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from .log_store import LogStore
    from .metrics_store import MetricsStore
    from .process_monitor import ProcessMonitor

router = APIRouter(tags=["API"])


# =============================================================================
# Response Models
# =============================================================================


class MetricSummary(BaseModel):
    """Summary statistics for a metric."""

    name: str
    min: float | None
    max: float | None
    avg: float | None
    count: int
    latest: float | None


class MetricPoint(BaseModel):
    """A single metric data point."""

    timestamp: float
    value: float


class MetricSeries(BaseModel):
    """Time series data for a metric."""

    name: str
    resolution: str
    points: list[MetricPoint]


class HealthStatus(BaseModel):
    """System health status."""

    status: str
    uptime_seconds: float
    metrics_collected: int
    components: dict[str, str]


class LogEntryResponse(BaseModel):
    """A log entry for API response."""

    timestamp: float
    source: str
    level: str
    message: str
    metadata: dict[str, Any] = {}


class LogsResponse(BaseModel):
    """Response for logs endpoint."""

    entries: list[LogEntryResponse]
    total: int


class ProcessRunResponse(BaseModel):
    """Process run information."""

    id: str
    process_name: str
    status: str
    started_at: float | None
    completed_at: float | None
    current_step: str | None
    error: str | None
    duration_seconds: float | None


class HumanTaskResponse(BaseModel):
    """Human task information."""

    id: str
    run_id: str
    task_type: str
    status: str
    assignee: str | None
    due_at: float | None
    is_overdue: bool


class ProcessStatsResponse(BaseModel):
    """Process statistics."""

    total_runs: int
    running: int
    waiting: int
    completed: int
    failed: int
    pending_tasks: int
    overdue_tasks: int


# Track start time for uptime
_start_time = time.time()


# =============================================================================
# Helper Functions
# =============================================================================


def _get_store(request: Request) -> MetricsStore:
    """Get metrics store from app state."""
    collector = getattr(request.app.state, "metrics_collector", None)
    if not collector or not collector.store:
        raise HTTPException(status_code=503, detail="Metrics collector not ready")
    store: MetricsStore = collector.store
    return store


def _get_log_store(request: Request) -> LogStore:
    """Get log store from app state."""
    log_store: LogStore | None = getattr(request.app.state, "log_store", None)
    if not log_store:
        raise HTTPException(status_code=503, detail="Log store not ready")
    return log_store


def _get_process_monitor(request: Request) -> ProcessMonitor:
    """Get process monitor from app state."""
    monitor: ProcessMonitor | None = getattr(request.app.state, "process_monitor", None)
    if not monitor:
        raise HTTPException(status_code=503, detail="Process monitor not ready")
    return monitor


# =============================================================================
# Metrics API
# =============================================================================


@router.get("/metrics", response_model=list[str])
async def list_metrics(request: Request) -> list[str]:
    """List all known metric names."""
    store = _get_store(request)
    return store.get_metric_names()


@router.get("/metrics/{name}/summary", response_model=MetricSummary)
async def get_metric_summary(request: Request, name: str, duration: int = 300) -> MetricSummary:
    """
    Get summary statistics for a metric.

    Args:
        name: Metric name
        duration: Lookback duration in seconds (default: 5 minutes)
    """
    store = _get_store(request)
    summary = store.get_summary(name, duration_seconds=duration)
    return MetricSummary(name=name, **summary)


@router.get("/metrics/{name}/series", response_model=MetricSeries)
async def get_metric_series(
    request: Request,
    name: str,
    resolution: str = "1m",
    start: float | None = None,
    end: float | None = None,
) -> MetricSeries:
    """
    Get time series data for a metric.

    Args:
        name: Metric name
        resolution: Time resolution (1m, 5m, 1h, 1d)
        start: Start timestamp (default: resolution's retention ago)
        end: End timestamp (default: now)
    """
    from .metrics_store import Resolution

    res_map = {
        "1m": Resolution.MINUTE,
        "5m": Resolution.FIVE_MIN,
        "1h": Resolution.HOUR,
        "1d": Resolution.DAY,
    }
    res = res_map.get(resolution, Resolution.MINUTE)

    store = _get_store(request)
    metric = store.query(name, resolution=res, start=start, end=end)

    return MetricSeries(
        name=metric.name,
        resolution=metric.resolution,
        points=[MetricPoint(timestamp=p.timestamp, value=p.value) for p in metric.points],
    )


# =============================================================================
# Health API
# =============================================================================


@router.get("/health/detailed", response_model=HealthStatus)
async def detailed_health(request: Request) -> HealthStatus:
    """Get detailed health status."""
    try:
        store = _get_store(request)
        req_summary = store.get_summary("http_requests_total", duration_seconds=3600)
        metrics_count = req_summary.get("count", 0)
    except Exception:
        metrics_count = 0

    return HealthStatus(
        status="healthy",
        uptime_seconds=time.time() - _start_time,
        metrics_collected=metrics_count,
        components={
            "collector": "running",
        },
    )


@router.get("/dashboard/data")
async def dashboard_data(request: Request) -> dict[str, Any]:
    """
    Get all data needed for the dashboard in one call.

    Used by HTMX to populate the dashboard.
    """
    try:
        store = _get_store(request)
    except HTTPException:
        # Metrics not ready, return empty data
        return {
            "timestamp": time.time(),
            "summary": {
                "requests_per_min": 0,
                "error_rate_pct": 0,
                "latency_p50": None,
                "latency_p99": None,
            },
            "charts": {"requests": [], "latency": []},
        }

    now = time.time()

    # Get key metrics
    request_rate = store.get_summary("http_requests_total", duration_seconds=60)
    error_rate = store.get_summary("http_errors_total", duration_seconds=60)
    latency = store.get_summary("http_latency_ms", duration_seconds=60)

    # Calculate error percentage
    total_requests = request_rate.get("count", 0)
    total_errors = error_rate.get("count", 0)
    error_pct = (total_errors / total_requests * 100) if total_requests > 0 else 0

    # Get time series for charts (last hour, 1-minute resolution)
    request_series = store.query(
        "http_requests_total",
        start=now - 3600,
        end=now,
    )

    latency_series = store.query(
        "http_latency_ms",
        start=now - 3600,
        end=now,
    )

    return {
        "timestamp": now,
        "summary": {
            "requests_per_min": request_rate.get("count", 0),
            "error_rate_pct": round(error_pct, 2),
            "latency_p50": latency.get("avg"),
            "latency_p99": latency.get("max"),
        },
        "charts": {
            "requests": [{"ts": p.timestamp, "value": p.value} for p in request_series.points],
            "latency": [{"ts": p.timestamp, "value": p.value} for p in latency_series.points],
        },
    }


# =============================================================================
# Logs API
# =============================================================================


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    request: Request,
    count: int = Query(default=100, ge=1, le=1000),
    source: str = Query(default="all"),
    level: str | None = Query(default=None),
) -> LogsResponse:
    """
    Get recent log entries.

    Args:
        count: Number of entries to retrieve (1-1000)
        source: Filter by source type (all, app, worker)
        level: Filter by level (error, warning)
    """
    log_store = _get_log_store(request)
    entries = log_store.get_recent(count=count, source_type=source, level=level)

    return LogsResponse(
        entries=[
            LogEntryResponse(
                timestamp=e.timestamp,
                source=e.source,
                level=e.level,
                message=e.message,
                metadata=e.metadata,
            )
            for e in entries
        ],
        total=len(entries),
    )


@router.get("/logs/errors")
async def get_error_logs(
    request: Request,
    count: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """Get recent error logs."""
    log_store = _get_log_store(request)
    entries = log_store.get_recent(count=count, level="error")

    return {
        "entries": [
            {
                "timestamp": e.timestamp,
                "source": e.source,
                "message": e.message,
            }
            for e in entries
        ],
        "count": len(entries),
    }


@router.get("/logs/search")
async def search_logs(
    request: Request,
    q: str = Query(..., min_length=2),
    count: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Search logs by message content."""
    log_store = _get_log_store(request)
    entries = log_store.search(query=q, count=count)

    return {
        "query": q,
        "entries": [
            {
                "timestamp": e.timestamp,
                "source": e.source,
                "level": e.level,
                "message": e.message,
            }
            for e in entries
        ],
        "count": len(entries),
    }


# =============================================================================
# Process API
# =============================================================================


@router.get("/processes/stats", response_model=ProcessStatsResponse)
async def get_process_stats(request: Request) -> ProcessStatsResponse:
    """Get aggregate process statistics."""
    monitor = _get_process_monitor(request)
    stats = monitor.get_stats()

    return ProcessStatsResponse(
        total_runs=stats.total_runs,
        running=stats.running,
        waiting=stats.waiting,
        completed=stats.completed,
        failed=stats.failed,
        pending_tasks=stats.pending_tasks,
        overdue_tasks=stats.overdue_tasks,
    )


@router.get("/processes/runs", response_model=list[ProcessRunResponse])
async def get_process_runs(
    request: Request,
    count: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> list[ProcessRunResponse]:
    """
    Get recent process runs.

    Args:
        count: Number of runs to retrieve (1-100)
        status: Filter by status (pending, running, waiting, completed, failed)
    """
    monitor = _get_process_monitor(request)
    runs = monitor.get_recent_runs(count=count, status=status)

    return [
        ProcessRunResponse(
            id=run.id,
            process_name=run.process_name,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            current_step=run.current_step,
            error=run.error,
            duration_seconds=run.duration_seconds,
        )
        for run in runs
    ]


@router.get("/processes/runs/active", response_model=list[ProcessRunResponse])
async def get_active_runs(request: Request) -> list[ProcessRunResponse]:
    """Get all currently active (running, waiting, pending) runs."""
    monitor = _get_process_monitor(request)
    runs = monitor.get_active_runs()

    return [
        ProcessRunResponse(
            id=run.id,
            process_name=run.process_name,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            current_step=run.current_step,
            error=run.error,
            duration_seconds=run.duration_seconds,
        )
        for run in runs
    ]


@router.get("/processes/runs/{run_id}", response_model=ProcessRunResponse)
async def get_process_run(request: Request, run_id: str) -> ProcessRunResponse:
    """Get a single process run by ID."""
    monitor = _get_process_monitor(request)
    run = monitor.get_run(run_id)

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return ProcessRunResponse(
        id=run.id,
        process_name=run.process_name,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        current_step=run.current_step,
        error=run.error,
        duration_seconds=run.duration_seconds,
    )


@router.get("/processes/tasks", response_model=list[HumanTaskResponse])
async def get_pending_tasks(
    request: Request,
    count: int = Query(default=20, ge=1, le=100),
) -> list[HumanTaskResponse]:
    """Get pending human tasks, sorted by due date."""
    monitor = _get_process_monitor(request)
    tasks = monitor.get_pending_tasks(count=count)

    return [
        HumanTaskResponse(
            id=task.id,
            run_id=task.run_id,
            task_type=task.task_type,
            status=task.status,
            assignee=task.assignee,
            due_at=task.due_at,
            is_overdue=task.is_overdue,
        )
        for task in tasks
    ]


@router.get("/processes/runs/{run_id}/tasks", response_model=list[HumanTaskResponse])
async def get_tasks_for_run(request: Request, run_id: str) -> list[HumanTaskResponse]:
    """Get all tasks for a specific process run."""
    monitor = _get_process_monitor(request)
    tasks = monitor.get_tasks_for_run(run_id)

    return [
        HumanTaskResponse(
            id=task.id,
            run_id=task.run_id,
            task_type=task.task_type,
            status=task.status,
            assignee=task.assignee,
            due_at=task.due_at,
            is_overdue=task.is_overdue,
        )
        for task in tasks
    ]
