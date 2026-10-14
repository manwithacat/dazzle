"""Re-sanitise stored rich-text values (``dazzle db resanitize-rich-text``).

Flense ship T (ADR-0057) put ``clean_rich_text`` on every write path, but rows
written before it still hold whatever HTML was posted. This walks every
rich-text field (``rich_text_fields_by_entity``: any surface rendering the
field with ``widget=rich_text``), runs the same allowlist sanitiser over each
stored value, and reports — or, with ``apply``, writes — the rows that change.

* Counts only: the report never carries a stored value.
* A value whose sanitised form exceeds the field's cap is reported and left
  untouched; the write path would reject it with 422, and truncating it here
  would lose data.
* A visually empty value (the editor's ``<p><br></p>`` shell, or markup with
  no text such as ``<img onerror=…>``) becomes NULL, as on the write path,
  or ``""`` when the field is ``required`` (NOT NULL).

The planner talks to a :class:`RichTextStore`, so it is unit-testable without
a database; :class:`PgRichTextStore` is the psycopg implementation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

from dazzle.db.connection import fetchall
from dazzle.db.sql import quote_id
from dazzle.http.runtime.richtext_field import clean_rich_text, rich_text_fields_by_entity

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

_PK = "id"
_BATCH_SIZE = 500


class RichTextTarget(BaseModel):
    """One stored rich-text column."""

    entity: str
    field: str
    cap: int
    required: bool = False


class FieldResult(BaseModel):
    """Counts for one rich-text column. Never carries a value."""

    entity: str
    field: str
    scanned: int = 0
    changed: int = 0
    over_cap: int = 0


class ResanitizeReport(BaseModel):
    applied: bool
    fields: list[FieldResult]

    @property
    def total_changed(self) -> int:
        return sum(f.changed for f in self.fields)

    @property
    def total_over_cap(self) -> int:
        return sum(f.over_cap for f in self.fields)


class RichTextStore(Protocol):
    """Row access the planner needs: read a column, write one cell."""

    def iter_values(self, entity: str, field: str) -> AsyncIterator[tuple[Any, Any]]:
        """Yield ``(row_id, value)`` for every row whose ``field`` is not NULL."""
        ...

    async def write_value(self, entity: str, field: str, row_id: Any, value: str | None) -> None:
        """Set ``field`` on one row."""
        ...


def rich_text_targets(appspec: AppSpec) -> list[RichTextTarget]:
    """Rich-text columns to walk, in a stable order.

    Only fields declared on a domain entity count: a surface element naming a
    field the entity does not have has no column to re-sanitise.
    """
    targets: list[RichTextTarget] = []
    for entity_name, fields in sorted(rich_text_fields_by_entity(appspec).items()):
        entity = appspec.get_entity(entity_name)
        if entity is None:
            continue
        for field_name, cap in sorted(fields.items()):
            spec = entity.get_field(field_name)
            if spec is None:
                continue
            targets.append(
                RichTextTarget(
                    entity=entity_name, field=field_name, cap=cap, required=spec.is_required
                )
            )
    return targets


def _resanitized(value: str, target: RichTextTarget) -> str | None:
    """The value the write path would store. Raises ``ValueError`` over the cap."""
    cleaned = clean_rich_text(value, max_length=target.cap)
    if cleaned:
        return cleaned
    if value == "":
        return value  # already empty: nothing to normalise
    return "" if target.required else None


async def resanitize_rich_text(
    targets: list[RichTextTarget],
    store: RichTextStore,
    *,
    apply: bool = False,
) -> ResanitizeReport:
    """Run ``clean_rich_text`` over every stored value of ``targets``.

    With ``apply=False`` (dry run) nothing is written; the report counts the
    rows that would change. Over-cap values are counted and never written.
    """
    results: list[FieldResult] = []
    for target in targets:
        result = FieldResult(entity=target.entity, field=target.field)
        async for row_id, value in store.iter_values(target.entity, target.field):
            if not isinstance(value, str):
                continue
            result.scanned += 1
            try:
                new = _resanitized(value, target)
            except ValueError:
                result.over_cap += 1
                continue
            if new == value:
                continue
            result.changed += 1
            if apply:
                await store.write_value(target.entity, target.field, row_id, new)
        results.append(result)
    return ResanitizeReport(applied=apply, fields=results)


class PgRichTextStore:
    """:class:`RichTextStore` over a psycopg async connection (mapping rows).

    Reads in primary-key order with keyset pagination, so a large table is
    never held in memory at once. Identifiers come from the AppSpec and are
    quoted with :func:`quote_id`; values are always bound parameters.
    """

    def __init__(self, conn: Any, *, batch_size: int = _BATCH_SIZE) -> None:
        self._conn = conn
        self._batch_size = batch_size

    async def iter_values(self, entity: str, field: str) -> AsyncIterator[tuple[Any, Any]]:
        table, col, pk = quote_id(entity), quote_id(field), quote_id(_PK)
        base = f"SELECT {pk} AS row_id, {col} AS value FROM {table} WHERE {col} IS NOT NULL"
        last: Any = None
        while True:
            if last is None:
                sql = f"{base} ORDER BY {pk} LIMIT %s"
                params: tuple[Any, ...] = (self._batch_size,)
            else:
                sql = f"{base} AND {pk} > %s ORDER BY {pk} LIMIT %s"
                params = (last, self._batch_size)
            rows = await fetchall(self._conn, sql, params)  # nosemgrep
            for row in rows:
                yield row["row_id"], row["value"]
            if len(rows) < self._batch_size:
                return
            last = rows[-1]["row_id"]

    async def write_value(self, entity: str, field: str, row_id: Any, value: str | None) -> None:
        sql = f"UPDATE {quote_id(entity)} SET {quote_id(field)} = %s WHERE {quote_id(_PK)} = %s"
        await self._conn.execute(sql, (value, row_id))  # nosemgrep
