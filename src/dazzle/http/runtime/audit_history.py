"""Audit history reader (#956 cycle 6).

Cycle 4 wires the writer; cycle 6 builds the read-side primitives the
detail-surface ``history`` region (cycle 7) will consume.

Three pieces:

  * ``HistoryEntry`` — a single decoded audit row ready for display
    (JSON-decoded before/after values, operation, timestamp, user).
  * ``decode_audit_row(row_dict)`` — converts one raw AuditEntry dict
    into a ``HistoryEntry``.
  * ``group_by_change(entries)`` — groups same-(at, by_user_id, op)
    rows into a single logical change spanning multiple fields. The
    cycle-3 emitter writes one row per tracked field, so a single
    user action shows up as N rows; the UI typically wants one card
    per action.

The reader is intentionally pure / synchronous on the row data — the
async DB call is left to the caller (which will use the existing
service/repository list API). Keeps unit tests fast and the wiring in
cycle 7 trivially mockable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """One decoded audit row, ready for template rendering.

    Attributes:
        at: When the change happened (kept as the raw value from the
            row — datetime or str — so the template can apply its own
            formatting).
        entity_type, entity_id: Discriminators.
        field_name: Which field changed.
        operation: ``"create"`` / ``"update"`` / ``"delete"``.
        before, after: The raw stored JSON strings (None for the
            create/delete side that doesn't exist).
        decoded_before, decoded_after: JSON-decoded Python values for
            display. Falls back to the raw string when JSON parse
            fails so the UI never blanks out.
        by_user_id: Who made the change (None for system writes).
    """

    at: Any
    entity_type: str
    entity_id: str
    field_name: str
    operation: str
    before: str | None
    after: str | None
    decoded_before: Any
    decoded_after: Any
    by_user_id: str | None


@dataclass
class HistoryChange:
    """One logical user action — may span multiple fields.

    The cycle-3 emitter writes one row per tracked field on a single
    update; this groups them so the UI renders one card per action
    rather than N cards-of-one-field. Sort order is preserved.

    Attributes:
        at: Timestamp of the underlying change (shared across fields).
        entity_type, entity_id, operation, by_user_id: Shared facets.
        fields: One ``HistoryEntry`` per tracked field that changed
            in this action (preserves the input order).
    """

    at: Any
    entity_type: str
    entity_id: str
    operation: str
    by_user_id: str | None
    fields: list[HistoryEntry] = field(default_factory=list)


def _safe_decode(value: str | None) -> Any:
    """JSON-decode `value` with a string fallback.

    Cycle 3 always JSON-encodes via `json.dumps(..., default=str)`, so
    this should round-trip cleanly. The fallback exists for hand-
    written rows or future format changes — never blank the UI.
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def decode_audit_row(row: dict[str, Any]) -> HistoryEntry:
    """Convert one raw AuditEntry dict into a typed HistoryEntry.

    Tolerant of missing keys — fields default to None / empty so a
    partially-formed row from a future schema version still renders.
    """
    before = row.get("before_value")
    after = row.get("after_value")
    return HistoryEntry(
        at=row.get("at"),
        entity_type=row.get("entity_type", ""),
        entity_id=row.get("entity_id", ""),
        field_name=row.get("field_name", ""),
        operation=row.get("operation", "update"),
        before=before,
        after=after,
        decoded_before=_safe_decode(before),
        decoded_after=_safe_decode(after),
        by_user_id=row.get("by_user_id"),
    )


def group_by_change(entries: Iterable[HistoryEntry]) -> list[HistoryChange]:
    """Group consecutive rows with the same (at, by_user_id, operation,
    entity) into one ``HistoryChange``.

    Caller is responsible for sort order — typically the audit service
    returns rows ordered by ``at`` desc, with a stable tiebreaker on
    insertion order so all rows from a single mutation arrive
    contiguously.

    Returns ``[]`` for an empty input.
    """
    changes: list[HistoryChange] = []
    current: HistoryChange | None = None

    for entry in entries:
        key = (entry.at, entry.by_user_id, entry.operation, entry.entity_type, entry.entity_id)
        current_key = (
            (
                current.at,
                current.by_user_id,
                current.operation,
                current.entity_type,
                current.entity_id,
            )
            if current is not None
            else None
        )
        if current is None or key != current_key:
            current = HistoryChange(
                at=entry.at,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                operation=entry.operation,
                by_user_id=entry.by_user_id,
                fields=[entry],
            )
            changes.append(current)
        else:
            current.fields.append(entry)

    return changes
