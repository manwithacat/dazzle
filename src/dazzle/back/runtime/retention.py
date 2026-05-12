"""Generic retention-sweep helper (#953 cycle 10).

Bulk-delete rows from a framework system entity older than a
threshold. Reusable across both `JobRun` (#953) and `AuditEntry`
(#956) — both have the same shape: a date column + a need to
prevent unbounded historical growth.

Cycle 11 will wire this for `JobRun` via a built-in scheduled
job (uses the cycle-7b cron scheduler). Cycle 12 will wire it
for `AuditEntry` per-spec from `AuditSpec.retention_days`.

Design notes
------------

* **Service-level delete, not raw SQL.** Goes through the
  framework's repository/service layer so any tenant scoping +
  cascade behaviour stays consistent. Some services don't
  expose bulk delete yet; the helper falls back to per-row
  delete and logs a hint to add a bulk path.
* **Best-effort.** Failures during the sweep log + return a
  partial count rather than raising — retention is housekeeping,
  not safety-critical. The cycle-11 scheduled job will surface
  failures via `JobRun.error_message` for operator triage.
* **`older_than=0` is a no-op.** Both `JobSpec.retention_days`
  and `AuditSpec.retention_days` use 0 to mean "keep forever";
  the helper honours that without iterating the table.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


async def sweep_old_rows(
    service: Any,
    *,
    date_field: str,
    older_than_days: int,
    page_size: int = 200,
) -> int:
    """Delete rows from ``service`` whose ``date_field`` is older
    than ``older_than_days``.

    Args:
        service: A framework service (cycle-2 `JobRun` or
            `AuditEntry`). Must expose `list(filters=..., page=...,
            page_size=...)` and `delete(id=...)` async methods.
        date_field: Name of the date column to compare against.
            ``"created_at"`` for JobRun; ``"at"`` for AuditEntry.
        older_than_days: Threshold in days. ``0`` means "keep
            forever" — function returns 0 immediately.
        page_size: Rows per fetched page during the sweep. Bounds
            memory and avoids long-running transactions on big
            tables.

    Returns:
        Number of rows successfully deleted. Partial counts on
        per-row failures (logged at WARNING).
    """
    if older_than_days <= 0:
        return 0
    if service is None:
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    deleted = 0
    page = 1

    while True:
        try:
            rows = await service.list(
                filters={f"{date_field}__lt": cutoff},
                page=page,
                page_size=page_size,
            )
        except Exception:
            logger.warning(
                "Retention sweep list-page failed (page=%d) — stopping",
                page,
                exc_info=True,
            )
            break

        items = _unwrap_items(rows)
        if not items:
            break

        for row in items:
            row_id = _row_id(row)
            if row_id is None:
                continue
            try:
                await service.delete(row_id)
                deleted += 1
            except Exception:
                logger.warning(
                    "Retention sweep delete failed for id=%s — continuing",
                    row_id,
                    exc_info=True,
                )

        # Defensive: stop after one page when the page is short.
        # Otherwise the same rows could re-appear on page 2 if the
        # underlying list query isn't stable across deletes.
        if len(items) < page_size:
            break
        page += 1

    if deleted:
        logger.info("Retention sweep deleted %d row(s) older than %s", deleted, cutoff)
    return deleted


def _unwrap_items(rows: Any) -> list[Any]:
    """Tolerate both list-of-dicts and paged-response shapes."""
    if isinstance(rows, dict) and "items" in rows:
        return list(rows["items"])
    if isinstance(rows, list):
        return rows
    return []


def _row_id(row: Any) -> Any:
    """Extract `id` from a dict, Pydantic model, or attr-bearing object."""
    if isinstance(row, dict):
        return row.get("id")
    return getattr(row, "id", None)
