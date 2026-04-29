"""Sibling-URL derivation for detail-view siblings (#942 cycle 3).

Project authors building detail pages (e.g. the PDF viewer chrome
from cycles 1a-2c) want prev/next URLs to navigate sequentially
through entities in the user's current scope (next manuscript in
the marking queue, previous invoice in the late-payments list,
etc). Computing them by hand requires knowing how the underlying
``Repository.list`` filter / sort grammar works AND the ID of the
adjacent row — both of which the framework already understands.

This module provides a single async helper:

    prev_url, next_url = await sibling_urls(
        repo=manuscript_repo,
        current_id=manuscript.id,
        sort="-created_at",
        filters={"cohort_id": cohort.id},
        url_for=lambda mid: f"/app/manuscripts/{mid}",
    )

The helper queries the repository twice (once for the row above
current in sort order, once for the row below) using the same
filter shape ``Repository.list`` accepts. Each query is paginated
to a single result for cheapness.

## Sort + tie-break

For now the helper supports a SINGLE sort field. Tied values
(rows with identical sort_field values) may produce inconsistent
prev/next behaviour at the tie boundary — when a project's
ordering key isn't unique, callers should pass ``id`` (or a
unique combination) instead. A future revision can add composite
``(sort_field, id)`` keysets if real adoption surfaces ties as a
problem.

## URL shape

The ``url_for`` callable takes the sibling's id and returns the
URL string. Decoupling URL construction from this helper keeps
project route shapes flexible — different apps will mount the
detail surface at different paths (``/app/<entity>/<id>`` vs
``/manuscripts/<id>`` vs ``/cohort/<cohort>/<id>``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID


def _parse_sort(sort: str) -> tuple[str, bool]:
    """Split a sort spec into (field_name, descending). ``"-foo"``
    means descending by foo; ``"+foo"`` or ``"foo"`` means
    ascending."""
    sort = sort.strip()
    if not sort:
        return "id", False
    if sort.startswith("-"):
        return sort[1:].strip(), True
    if sort.startswith("+"):
        return sort[1:].strip(), False
    return sort, False


def _read_field(row: Any, field: str) -> Any:
    """Get ``field`` off a row regardless of whether it's a Pydantic
    model, dict, or arbitrary attribute carrier."""
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


async def sibling_urls(
    *,
    repo: Any,
    current_id: UUID,
    sort: str = "id",
    filters: dict[str, Any] | None = None,
    url_for: Callable[[Any], str],
) -> tuple[str | None, str | None]:
    """Return ``(prev_url, next_url)`` for the entity at
    ``current_id`` in the given sort order, scoped by ``filters``.

    Either or both URLs may be ``None`` when the current row is the
    first / last in scope (no sibling exists in that direction).

    Args:
        repo: A ``Repository`` instance (must expose
            ``read(id) -> row | None`` and
            ``list(filters=, sort=, page=, page_size=) -> {"items": [...]}``).
        current_id: Primary key of the current entity. The helper
            reads this row first to learn its sort-key value, then
            queries for the closest row above and below.
        sort: Sort spec — bare field name (ascending) or
            ``"-field"`` (descending). Defaults to ``"id"``.
        filters: Same dict shape ``Repository.list`` accepts. Used
            to scope the sibling search (e.g. only show siblings
            within the same cohort / status / owner).
        url_for: Callable that turns a sibling's id into a URL
            string. Project-shaped — each app mounts detail
            surfaces at different paths.

    Returns:
        ``(prev_url, next_url)``. Each is ``None`` when the
        current row has no neighbour in that direction.
    """
    current_row = await repo.read(current_id)
    if current_row is None:
        return None, None

    sort_field, descending = _parse_sort(sort)
    current_value = _read_field(current_row, sort_field)
    if current_value is None:
        # Sort key value is missing — can't position the row in
        # the ordering. Treat as no siblings rather than guessing.
        return None, None

    base_filters = dict(filters or {})

    # Reading order semantics:
    # - ASC list: prev row has sort_field < current; next has sort_field >
    # - DESC list: prev row has sort_field > current; next has sort_field <
    if descending:
        prev_filters = {**base_filters, f"{sort_field}__gt": current_value}
        prev_sort = sort_field  # ASC of underlying = closest above current
        next_filters = {**base_filters, f"{sort_field}__lt": current_value}
        next_sort = f"-{sort_field}"  # DESC of underlying = closest below current
    else:
        prev_filters = {**base_filters, f"{sort_field}__lt": current_value}
        prev_sort = f"-{sort_field}"
        next_filters = {**base_filters, f"{sort_field}__gt": current_value}
        next_sort = sort_field

    prev_result = await repo.list(filters=prev_filters, sort=prev_sort, page=1, page_size=1)
    next_result = await repo.list(filters=next_filters, sort=next_sort, page=1, page_size=1)

    prev_id = _row_id(prev_result.get("items"))
    next_id = _row_id(next_result.get("items"))

    return (
        url_for(prev_id) if prev_id is not None else None,
        url_for(next_id) if next_id is not None else None,
    )


def _row_id(items: list[Any] | None) -> Any:
    """Pick the ``id`` off the first item, supporting both dict
    and model representations (Repository.list emits whichever the
    underlying entity uses)."""
    if not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        return first.get("id")
    return getattr(first, "id", None)
