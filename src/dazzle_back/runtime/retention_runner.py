"""Retention orchestrator (#953 cycle 11, also unblocks #956 cycle 12).

Single async entry point that sweeps both built-in framework
retention targets in one pass:

  * `JobRun` rows older than ``jobrun_retention_days`` (default
    30) — historical worker invocations.
  * `AuditEntry` rows older than each `AuditSpec.retention_days`
    declared in the AppSpec — user-visible change history per
    entity. Audit blocks with ``retention_days=0`` are skipped
    (the IR's "keep forever" sentinel, honoured by the cycle-10
    sweep helper too).

Cycle 12 will register this with the cycle-7b scheduler as a
synthetic daily job so the operator gets retention for free
without needing to author a `job:` block themselves.
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.retention import sweep_old_rows

logger = logging.getLogger(__name__)


async def run_retention_sweep(
    *,
    services: dict[str, Any],
    audits: list[Any] | None = None,
    jobrun_retention_days: int = 30,
    page_size: int = 200,
) -> dict[str, int]:
    """Sweep both JobRun and AuditEntry retention in one pass.

    Args:
        services: ``{entity_name: BaseService}`` from the running
            server. Looks up `JobRun` and `AuditEntry` by name;
            silently skips when either is missing (cycle-2
            injection didn't fire because no jobs / audits were
            declared).
        audits: ``appspec.audits`` list. Each `AuditSpec.entity`
            shares one `AuditEntry` table; the sweep filters by
            `entity_type` so per-entity retention windows are
            honoured. None / empty skips audit cleanup.
        jobrun_retention_days: How long to keep `JobRun` rows.
            ``0`` means "keep forever" (the IR convention) — the
            cycle-10 sweep helper short-circuits without
            touching the service.
        page_size: Per-page batch size threaded through to the
            sweep helper. Defaults to a value that keeps memory
            bounded on big tables without being so small it
            burns DB round-trips.

    Returns:
        Per-source delete count: ``{"JobRun": N, "AuditEntry:Manuscript":
        N, ...}``. Useful for the cycle-12 scheduled-job wrapper to
        log + surface via JobRun.error_message on failure.
    """
    stats: dict[str, int] = {}

    job_run = services.get("JobRun")
    if job_run is not None:
        deleted = await sweep_old_rows(
            job_run,
            date_field="created_at",
            older_than_days=jobrun_retention_days,
            page_size=page_size,
        )
        stats["JobRun"] = deleted

    audit_entry = services.get("AuditEntry")
    if audit_entry is not None and audits:
        for audit_spec in audits:
            entity_name = getattr(audit_spec, "entity", "")
            retention = int(getattr(audit_spec, "retention_days", 0) or 0)
            if not entity_name or retention <= 0:
                continue
            deleted = await _sweep_audit_for_entity(
                audit_entry,
                entity_name=entity_name,
                older_than_days=retention,
                page_size=page_size,
            )
            stats[f"AuditEntry:{entity_name}"] = deleted

    if stats:
        logger.info("Retention sweep complete: %s", stats)
    return stats


async def _sweep_audit_for_entity(
    audit_entry_service: Any,
    *,
    entity_name: str,
    older_than_days: int,
    page_size: int,
) -> int:
    """Sweep `AuditEntry` rows for one audited entity type.

    Wraps the cycle-10 helper with an additional `entity_type`
    filter so per-entity retention windows are honoured (a
    `Manuscript` audit block with 90-day retention shouldn't
    delete `Order` audit rows that have a 365-day retention).
    """
    from datetime import UTC, datetime, timedelta

    if older_than_days <= 0:
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    deleted = 0
    page = 1
    while True:
        try:
            rows = await audit_entry_service.list(
                filters={"entity_type": entity_name, "at__lt": cutoff},
                page=page,
                page_size=page_size,
            )
        except Exception:
            logger.warning(
                "AuditEntry retention list-page failed for %s (page=%d) — stopping",
                entity_name,
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
                await audit_entry_service.delete(row_id)
                deleted += 1
            except Exception:
                logger.warning(
                    "AuditEntry retention delete failed for id=%s — continuing",
                    row_id,
                    exc_info=True,
                )

        if len(items) < page_size:
            break
        page += 1

    return deleted


def _unwrap_items(rows: Any) -> list[Any]:
    if isinstance(rows, dict) and "items" in rows:
        return list(rows["items"])
    if isinstance(rows, list):
        return rows
    return []


def _row_id(row: Any) -> Any:
    if isinstance(row, dict):
        return row.get("id")
    return getattr(row, "id", None)
