"""Schema-drift detection for `signable: true` entities (#1340).

A signable entity gets the signing columns in ``SIGNABLE_AUTO_FIELD_NAMES``
auto-injected by the linker. If the live table was frozen at a stale,
pre-signable shape (an early baseline migration) and never reconciled, a create
INSERT — built from the full entity fields — 500s on the first missing column
(e.g. ``UndefinedColumn: signing_token_hash``). This detector surfaces the drift
loudly at ``dazzle db verify`` time, naming the missing columns, instead of an
opaque per-create 500.

Remediation is a migration (ADR-0017 — all schema changes go through Alembic):
``dazzle db revision -m "add signing columns" --autogenerate && dazzle db
upgrade``. This module is purely diagnostic — it never ALTERs the table.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.linker import SIGNABLE_AUTO_FIELD_NAMES

from .connection import fetchall


def missing_signable_columns(live_columns: set[str]) -> list[str]:
    """Return the signing columns absent from a live signable table, in order.

    Each signing field is a plain single-column scalar/datetime/enum/file field,
    so the column name equals the field name.
    """
    return [c for c in SIGNABLE_AUTO_FIELD_NAMES if c not in live_columns]


async def _live_columns(conn: Any, table: str) -> set[str]:
    """Live column names for ``table`` via information_schema (empty if absent)."""
    rows = await fetchall(
        conn,
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {row["column_name"] for row in rows}


async def detect_signable_drift(conn: Any, entities: list[Any]) -> list[dict[str, Any]]:
    """Return drift entries for signable entities missing signing columns.

    Each entry is ``{"entity": name, "missing": [columns]}``. The list is empty
    when every ``signable: true`` table carries all signing columns (or there are
    no signable entities).

    A table that is entirely absent is **not** reported here — that is an
    unmigrated DB (a different state), not column drift, and flagging it would
    false-positive a fresh/never-upgraded database.
    """
    drifts: list[dict[str, Any]] = []
    for entity in entities:
        if not getattr(entity, "signable", False):
            continue
        live = await _live_columns(conn, entity.name)
        if not live:
            continue
        missing = missing_signable_columns(live)
        if missing:
            drifts.append({"entity": entity.name, "missing": missing})
    return drifts
