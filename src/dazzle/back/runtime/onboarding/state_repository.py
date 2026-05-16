"""Postgres data layer for per-user guide progression (v0.71.1).

One row per ``(user_id, guide_name, guide_version)`` in the
``onboarding_state`` table. The repository owns the UPSERT semantics
that enforce composite uniqueness — the IR entity has a UUID primary
key (matches the framework convention) but the natural key is the
triple.

Schema is auto-managed: the ``OnboardingState`` entity declared in
``dazzle.core.ir.onboarding_state`` flows through the standard
migration pipeline. There's no hand-written Alembic file in v0.71.1;
projects run ``dazzle db revision -m "add onboarding state"`` followed
by ``dazzle db upgrade`` per ADR-0017.

Postgres-only per ADR-0008.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

logger = logging.getLogger("dazzle.onboarding")


@dataclass(frozen=True)
class OnboardingProgress:
    """In-memory view of one ``onboarding_state`` row."""

    id: str
    user_id: str
    guide_name: str
    guide_version: int
    current_step: str | None
    completed_steps: list[str] = field(default_factory=list)
    dismissed_steps: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None


class OnboardingStateRepository:
    """Postgres data layer for ``onboarding_state``.

    Five operations:

    - ``get`` — fetch one ``(user_id, guide_name, guide_version)`` row,
      or ``None``.
    - ``upsert`` — create or replace progression for a triple. Returns
      the resulting :class:`OnboardingProgress`.
    - ``mark_step_completed`` — append a step ID to ``completed_steps``
      (no-op if already present). Advances ``current_step`` if given.
    - ``mark_step_dismissed`` — append to ``dismissed_steps``.
    - ``mark_completed`` — set ``completed_at`` + clear
      ``current_step``.

    All writes are idempotent — applying the same operation twice
    leaves the row in the same state. This matters because the
    runtime fires completion via UI events and we don't want a
    double-click to corrupt state.
    """

    # Table name inlined in each SQL statement below — interpolating it
    # via a class constant trips semgrep's SQL-injection rule even when
    # the value is a literal. Inlining keeps the queries flagged as
    # plain strings.

    def __init__(self, database_url: str):
        self._database_url = database_url

    # ------------------------------------------------------------------
    # Connection helper
    # ------------------------------------------------------------------

    def _get_connection(self) -> Any:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for onboarding state. "
                "Install it with: pip install psycopg[binary]"
            ) from exc
        try:
            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to PostgreSQL for onboarding state: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(
        self, user_id: str, guide_name: str, guide_version: int = 1
    ) -> OnboardingProgress | None:
        """Return one row for the triple, or ``None`` if no progression exists yet."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM onboarding_state "
                    "WHERE user_id = %s AND guide_name = %s AND guide_version = %s "
                    "LIMIT 1",
                    (user_id, guide_name, guide_version),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _row_to_progress(row)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        *,
        user_id: str,
        guide_name: str,
        guide_version: int = 1,
        current_step: str | None = None,
        completed_steps: list[str] | None = None,
        dismissed_steps: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OnboardingProgress:
        """Insert or replace progression for ``(user, guide, version)``.

        Uses PostgreSQL's ``INSERT ... ON CONFLICT`` to enforce composite
        uniqueness without a round trip. Returns the resulting row.
        """
        completed_steps = completed_steps or []
        dismissed_steps = dismissed_steps or []
        now = datetime.now(UTC).isoformat()
        row_id = str(uuid4())

        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO onboarding_state (
                        id, user_id, guide_name, guide_version,
                        current_step, completed_steps, dismissed_steps,
                        started_at, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id, guide_name, guide_version)
                    DO UPDATE SET
                        current_step = EXCLUDED.current_step,
                        completed_steps = EXCLUDED.completed_steps,
                        dismissed_steps = EXCLUDED.dismissed_steps,
                        metadata = EXCLUDED.metadata
                    RETURNING *
                    """,
                    (
                        row_id,
                        user_id,
                        guide_name,
                        guide_version,
                        current_step,
                        json.dumps(completed_steps),
                        json.dumps(dismissed_steps),
                        now,
                        json.dumps(metadata) if metadata is not None else None,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        finally:
            conn.close()
        if row is None:
            raise RuntimeError("upsert returned no row — unexpected")
        return _row_to_progress(row)

    def mark_step_completed(
        self,
        *,
        user_id: str,
        guide_name: str,
        guide_version: int,
        step_name: str,
        next_current_step: str | None = None,
    ) -> OnboardingProgress:
        """Append ``step_name`` to ``completed_steps`` (idempotent).

        ``next_current_step`` (if given) replaces ``current_step``. Use
        when the renderer knows the next step to advance to. Passing
        ``None`` clears ``current_step`` — appropriate for the last
        step in the guide (the caller should follow with
        :meth:`mark_completed`).
        """
        current = self.get(user_id, guide_name, guide_version)
        completed = list(current.completed_steps) if current else []
        if step_name not in completed:
            completed.append(step_name)
        dismissed = list(current.dismissed_steps) if current else []
        return self.upsert(
            user_id=user_id,
            guide_name=guide_name,
            guide_version=guide_version,
            current_step=next_current_step,
            completed_steps=completed,
            dismissed_steps=dismissed,
            metadata=current.metadata if current else None,
        )

    def mark_step_dismissed(
        self,
        *,
        user_id: str,
        guide_name: str,
        guide_version: int,
        step_name: str,
    ) -> OnboardingProgress:
        """Append ``step_name`` to ``dismissed_steps`` (idempotent)."""
        current = self.get(user_id, guide_name, guide_version)
        dismissed = list(current.dismissed_steps) if current else []
        if step_name not in dismissed:
            dismissed.append(step_name)
        completed = list(current.completed_steps) if current else []
        return self.upsert(
            user_id=user_id,
            guide_name=guide_name,
            guide_version=guide_version,
            current_step=current.current_step if current else None,
            completed_steps=completed,
            dismissed_steps=dismissed,
            metadata=current.metadata if current else None,
        )

    def mark_completed(self, *, user_id: str, guide_name: str, guide_version: int) -> bool:
        """Set ``completed_at = now()`` and clear ``current_step``.

        Returns True iff a row was touched (i.e. the user had any
        progression to mark complete).
        """
        now = datetime.now(UTC).isoformat()
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE onboarding_state SET completed_at = %s, current_step = NULL "
                    "WHERE user_id = %s AND guide_name = %s AND guide_version = %s",
                    (now, user_id, guide_name, guide_version),
                )
                rowcount: int = cur.rowcount
                conn.commit()
        finally:
            conn.close()
        return rowcount > 0


# ---------------------------------------------------------------------------
# Row → dataclass helper
# ---------------------------------------------------------------------------


def _row_to_progress(row: dict[str, Any]) -> OnboardingProgress:
    return OnboardingProgress(
        id=str(row["id"]),
        user_id=row["user_id"],
        guide_name=row["guide_name"],
        guide_version=int(row["guide_version"]),
        current_step=row.get("current_step"),
        completed_steps=_parse_json_list(row.get("completed_steps")),
        dismissed_steps=_parse_json_list(row.get("dismissed_steps")),
        started_at=_parse_dt(row.get("started_at")),
        completed_at=_parse_dt(row.get("completed_at")),
        metadata=_parse_json_dict(row.get("metadata")),
    )


def _parse_json_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        logger.debug("onboarding_state: malformed JSON list %r — defaulting to []", value)
        return []
    return [str(v) for v in parsed] if isinstance(parsed, list) else []


def _parse_json_dict(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
