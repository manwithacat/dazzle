"""
Dazzle Control Plane API.

Provides /dazzle/dev/* endpoints for developer-mode operations.
These endpoints handle data management and frontend logging.

These endpoints are only available in dev/native mode or when test_mode is enabled.
"""

import logging
import re
from dataclasses import dataclass
from functools import partial
from typing import Any

from pydantic import BaseModel

from dazzle_back.runtime._fastapi_compat import FASTAPI_AVAILABLE, APIRouter
from dazzle_back.runtime.repository import DatabaseManager, Repository
from dazzle_back.specs.entity import EntitySpec

logger = logging.getLogger(__name__)

# Table-name pattern: only word chars (letters, digits, underscore).
_SAFE_TABLE_RE = re.compile(r"^[A-Za-z_]\w*$")


def _delete_all_rows(conn: Any, table_name: str) -> None:
    """Delete all rows from *table_name* after validating it is a safe identifier."""
    if not _SAFE_TABLE_RE.match(table_name):
        raise ValueError(f"Unsafe table name: {table_name!r}")
    conn.execute(f"DELETE FROM {table_name}")  # nosemgrep  # table_name validated above


# =============================================================================
# Request/Response Models
# =============================================================================


class FrontendLogRequest(BaseModel):
    """Frontend log entry from the browser."""

    level: str = "info"  # error, warn, info, debug
    message: str
    source: str | None = None
    line: int | None = None
    column: int | None = None
    stack: str | None = None
    url: str | None = None
    user_agent: str | None = None
    extra: dict[str, Any] | None = None


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _ControlPlaneDeps:
    db_manager: DatabaseManager | None
    repositories: dict[str, Repository[Any]] | None
    entities: list[EntitySpec]


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _reset_data(deps: _ControlPlaneDeps) -> dict[str, str]:
    """
    Reset all data in the database.

    Clears all entity data while preserving schema.
    """
    if not deps.db_manager:
        return {"status": "skipped", "reason": "No database configured"}

    with deps.db_manager.connection() as conn:
        for entity in deps.entities:
            try:
                _delete_all_rows(conn, entity.name)
            except Exception:
                logger.debug("Failed to reset table %s", entity.name, exc_info=True)

    return {"status": "reset_complete"}


async def _log_frontend_message(
    deps: _ControlPlaneDeps, request: FrontendLogRequest
) -> dict[str, str]:
    """
    Log a message from the frontend.

    This endpoint captures frontend errors, warnings, and info messages
    and writes them to the JSONL log file for LLM agent monitoring.

    The log file at .dazzle/logs/dnr.log is JSONL format - each line
    is a complete JSON object that LLM agents can parse.
    """
    from dazzle_back.runtime.logging import log_frontend_entry

    log_frontend_entry(
        level=request.level,
        message=request.message,
        source=request.source,
        line=request.line,
        column=request.column,
        stack=request.stack,
        url=request.url,
        user_agent=request.user_agent,
        extra=request.extra,
    )

    return {"status": "logged"}


async def _get_logs(
    deps: _ControlPlaneDeps, count: int = 50, level: str | None = None
) -> dict[str, Any]:
    """
    Get recent log entries for LLM agent inspection.

    Returns JSONL entries as a list for easy processing.
    LLM agents can use this to understand recent activity and errors.

    Args:
        count: Number of recent entries (default 50)
        level: Filter by level (ERROR, WARNING, INFO, DEBUG)
    """
    from dazzle_back.runtime.logging import get_log_file, get_recent_logs

    entries = get_recent_logs(count=count, level=level)

    return {
        "count": len(entries),
        "log_file": str(get_log_file()),
        "entries": entries,
    }


async def _get_error_summary(deps: _ControlPlaneDeps) -> dict[str, Any]:
    """
    Get error summary for LLM agent diagnosis.

    Returns a structured summary of errors grouped by component,
    with recent errors for context. Designed for LLM agents to
    quickly understand what's going wrong.
    """
    from dazzle_back.runtime.logging import get_error_summary

    return get_error_summary()


async def _clear_logs(deps: _ControlPlaneDeps) -> dict[str, Any]:
    """
    Clear all log files.

    Useful for starting fresh when debugging.
    """
    from dazzle_back.runtime.logging import clear_logs

    count = clear_logs()
    return {"status": "cleared", "files_deleted": count}


# =============================================================================
# Route Factory
# =============================================================================


def create_control_plane_routes(
    db_manager: DatabaseManager | None,
    repositories: dict[str, Repository[Any]] | None,
    entities: list[EntitySpec],
) -> APIRouter:
    """
    Create control plane routes.

    Args:
        db_manager: Database manager instance (optional)
        repositories: Dictionary of repositories by entity name (optional)
        entities: List of entity specifications

    Returns:
        APIRouter with control plane endpoints

    Raises:
        RuntimeError: If FastAPI is not available
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is required for control plane routes. Install it with: pip install fastapi"
        )

    router = APIRouter(prefix="/dazzle/dev", tags=["Dazzle Control Plane"])

    deps = _ControlPlaneDeps(
        db_manager=db_manager,
        repositories=repositories,
        entities=entities,
    )

    # -------------------------------------------------------------------------
    # Data Management Endpoints
    # -------------------------------------------------------------------------

    router.add_api_route("/reset", partial(_reset_data, deps), methods=["POST"])

    # -------------------------------------------------------------------------
    # Logging Endpoints (v0.8.11)
    # -------------------------------------------------------------------------

    router.add_api_route("/log", partial(_log_frontend_message, deps), methods=["POST"])
    router.add_api_route("/logs", partial(_get_logs, deps), methods=["GET"])
    router.add_api_route("/logs/errors", partial(_get_error_summary, deps), methods=["GET"])
    router.add_api_route("/logs", partial(_clear_logs, deps), methods=["DELETE"])

    return router
