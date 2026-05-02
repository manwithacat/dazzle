"""Audit-trail emitter (#956 cycle 3).

Computes before/after diffs for tracked fields and writes one
``AuditEntry`` row per changed field. Cycle-2 injected the
``AuditEntry`` system entity; this cycle builds the diff logic and a
callback factory that the service generator (cycle 4) will register
against `BaseService.on_created` / `on_updated` / `on_deleted` for any
entity with an ``audit on X:`` block.

Design notes
------------

* Single function pair — ``compute_diff`` (pure) and
  ``build_audit_callbacks`` (factory). Easy to unit-test in isolation
  before the service-callback wiring lands in cycle 4.

* `before_value` / `after_value` are JSON-encoded strings on the
  ``AuditEntry`` row so any field type round-trips through the same
  TEXT column without a polymorphic schema. ``json.dumps`` with
  ``default=str`` handles UUIDs, datetimes, Decimals etc.

* For CREATE and DELETE we still emit one row per tracked field —
  the "before" side is null on create, "after" is null on delete.
  This gives the cycle-4 history region a uniform read shape (no
  branching per operation).

* `track` empty list means "track every field" (per cycle-1
  semantics). Callers feed the actual entity field list separately;
  the emitter doesn't need the IR model since it works on dicts.

The emitter never raises — audit writes are best-effort and must not
break the user's mutation. Failures land in the logger.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type for the writer callback the cycle-4 wiring will provide.
# Takes a list of AuditEntry-shaped dicts and persists them. Returning
# nothing keeps the interface simple — failures are swallowed inside.
AuditWriter = Callable[[list[dict[str, Any]]], Awaitable[None]]


def _safe_json(value: Any) -> str | None:
    """JSON-encode `value` with str-fallback for UUIDs/datetimes/Decimals.

    Returns None for None inputs so the AuditEntry's nullable
    before/after_value columns can carry "this side didn't exist"
    semantics distinctly from the literal string ``"null"``.
    """
    if value is None:
        return None
    try:
        return json.dumps(value, default=str, sort_keys=True)
    except (TypeError, ValueError):
        # Last-ditch: stringify and wrap so the row still gets written.
        return json.dumps(str(value))


def compute_diff(
    *,
    entity_type: str,
    entity_id: str,
    old_data: dict[str, Any] | None,
    new_data: dict[str, Any] | None,
    track: list[str],
    by_user_id: str | None = None,
    operation: str = "update",
) -> list[dict[str, Any]]:
    """Compute one AuditEntry-shaped dict per tracked field that changed.

    Args:
        entity_type: The audited entity's name (e.g. "Manuscript").
        entity_id: The row's primary key as a string.
        old_data: Pre-mutation field values, or None for CREATE.
        new_data: Post-mutation field values, or None for DELETE.
        track: Field names to capture. Empty list means "every field
            present in either side" — preserves cycle-1 semantics.
        by_user_id: User who made the change. None for system writes.
        operation: ``"create"``, ``"update"``, or ``"delete"``.

    Returns:
        A list of dicts ready for insertion into AuditEntry. May be
        empty when nothing changed (no row written).
    """
    if old_data is None and new_data is None:
        return []

    old = old_data or {}
    new = new_data or {}

    # `track=[]` means "every field present" — union the two sides so
    # added/removed fields are captured during create/delete.
    if track:
        candidate_fields = list(track)
    else:
        candidate_fields = sorted(set(old.keys()) | set(new.keys()))

    rows: list[dict[str, Any]] = []
    for field_name in candidate_fields:
        old_val = old.get(field_name)
        new_val = new.get(field_name)
        if operation == "update" and old_val == new_val:
            continue  # No change — skip.
        rows.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_name": field_name,
                "operation": operation,
                "before_value": _safe_json(old_val),
                "after_value": _safe_json(new_val),
                "by_user_id": by_user_id,
            }
        )
    return rows


def build_audit_callbacks(
    *,
    entity_type: str,
    track: list[str],
    writer: AuditWriter,
    user_id_provider: Callable[[], str | None] | None = None,
) -> dict[str, Callable[..., Awaitable[None]]]:
    """Build on_created / on_updated / on_deleted callbacks for an
    audited entity.

    Args:
        entity_type: The audited entity's name.
        track: Fields to capture (empty = all).
        writer: Async callable that persists the rows. The cycle-4
            wiring will pass an ``AuditEntry`` service-write function.
        user_id_provider: Optional zero-arg callable returning the
            current user ID. Per-request resolution lives in cycle 4
            (most likely via a ContextVar populated by the auth
            middleware); this hook lets the unit tests inject one.

    Returns:
        Dict with keys ``"on_created"``, ``"on_updated"``,
        ``"on_deleted"`` — each value is an async function that
        ``BaseService`` will invoke with the standard callback
        signature (``entity_id, entity_data, old_data, operation``).
    """

    def _resolve_user() -> str | None:
        if user_id_provider is None:
            return None
        try:
            return user_id_provider()
        except Exception:
            return None

    async def _write_safely(rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        try:
            await writer(rows)
        except Exception:
            # Best-effort — never break the user's mutation.
            logger.warning(
                "Audit emitter failed for %s (%d rows)",
                entity_type,
                len(rows),
                exc_info=True,
            )

    async def on_created(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        rows = compute_diff(
            entity_type=entity_type,
            entity_id=entity_id,
            old_data=None,
            new_data=entity_data,
            track=track,
            by_user_id=_resolve_user(),
            operation="create",
        )
        await _write_safely(rows)

    async def on_updated(
        entity_id: str,
        entity_data: dict[str, Any],
        old_data: dict[str, Any] | None,
        _op: str,
    ) -> None:
        rows = compute_diff(
            entity_type=entity_type,
            entity_id=entity_id,
            old_data=old_data,
            new_data=entity_data,
            track=track,
            by_user_id=_resolve_user(),
            operation="update",
        )
        await _write_safely(rows)

    async def on_deleted(
        entity_id: str,
        entity_data: dict[str, Any],
        _old: dict[str, Any] | None,
        _op: str,
    ) -> None:
        rows = compute_diff(
            entity_type=entity_type,
            entity_id=entity_id,
            old_data=entity_data,
            new_data=None,
            track=track,
            by_user_id=_resolve_user(),
            operation="delete",
        )
        await _write_safely(rows)

    return {
        "on_created": on_created,
        "on_updated": on_updated,
        "on_deleted": on_deleted,
    }
