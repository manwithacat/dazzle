"""CSV export response builder for workspace list regions.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Single pure helper — no I/O, no DB, no IR dispatch. Takes resolved
items + pre-computed column metadata in, returns a streaming
``text/csv`` response with a content-disposition attachment header.

Cycle 2253 (oral #122): CSV must not invent clerk-facing money from
raw minor units, or ``str(dict)`` for unresolved refs. Leftover
currency junk stays put. Distinct from leftover-token stay-put.

Cycle 2257 (oral #126): CSV must not invent naive-UTC datetime as
wall time, or ISO calendar dates when the grid uses the tenant
profile. Leftover date junk stays put.

Cycle 2260 (oral #129): entity-list ``?format=csv`` must not be
treated as an invalid graph dialect. Graph ``cytoscape`` / ``d3`` /
``raw`` stay graph; leftover junk stays 400.

Cycle 2261 (oral #130): badge / enum cells must not dump snake_case
tokens when the grid title-cases them (``in_progress`` vs
``In Progress``). Leftover junk stays put.

Cycle 2262 (oral #131): DSL ``format: currency:GBP`` on a decimal
amount must not dump bare major units when the grid shows ``£1,250.00``.
CSV uses the same ``format_kind`` override as the list row. Leftover
junk stays put. Distinct from money-minor ``type=currency`` (oral #122).
"""

import csv
import io
from datetime import date, datetime
from decimal import InvalidOperation
from typing import Any

from starlette.responses import StreamingResponse

from dazzle.render.channel_cell import clerk_email_display, clerk_phone_display
from dazzle.render.display_names import _resolve_display_name
from dazzle.render.file_cell import clerk_file_cell_display
from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell
from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_catalog_option_values,
)
from dazzle.render.rating_cell import clerk_rating_display
from dazzle.render.tags_cell import clerk_tags_join
from dazzle.render.temperature_cell import clerk_temperature_display

_CSV_CHANNEL_FORMATTERS = {
    "tags": clerk_tags_join,
    "rating": clerk_rating_display,
    "email": clerk_email_display,
    "phone": clerk_phone_display,
}


def _csv_format_override(raw: Any, column: dict[str, Any]) -> str | None:
    """DSL ``format:`` on a CSV cell — same override the grid uses (oral #131).

    Returns None when the column has no format_kind so typed inference runs.
    Leftover junk stays put (format_cell refuse, or exception → str(raw)).
    """
    format_kind = str(column.get("format_kind") or "")
    if not format_kind:
        return None
    try:
        return format_cell(
            raw,
            str(column.get("type") or "text"),
            currency_code=str(column.get("currency_code") or ""),
            override=ResolvedFormat(format_kind, column.get("format_arg") or None),
        )
    except (TypeError, ValueError, InvalidOperation):
        return str(raw)


def _csv_typed_cell(raw: Any, column: dict[str, Any]) -> str:
    """Format a non-dict CSV value by column type (oral #122 / #126 / #130 / #131)."""
    override = _csv_format_override(raw, column)
    if override is not None:
        return override
    kind = str(column.get("type") or "")
    if kind == "currency":
        return format_cell(
            raw,
            "currency",
            currency_code=str(column.get("currency_code") or "GBP"),
        )
    if kind in ("date", "datetime"):
        return format_cell(raw, kind)
    if kind == "temperature":
        return clerk_temperature_display(raw, column.get("key"))
    if kind == "badge":
        options = column.get("filter_options")
        if options is not None:
            known = leftover_honest_catalog_option_values(options)
            if known and str(raw) not in known:
                return str(raw)
        return format_cell(raw, "badge")
    channel = _CSV_CHANNEL_FORMATTERS.get(kind)
    if channel is not None:
        return channel(raw)
    if isinstance(raw, datetime):
        return format_cell(raw, "datetime")
    if isinstance(raw, date):
        return format_cell(raw, "date")
    if isinstance(raw, bool):
        return format_cell(raw, "bool")
    return str(raw)


def _csv_cell(item: dict[str, Any], column: dict[str, Any]) -> str:
    """Clerk-facing CSV cell — same honesty as the list grid.

    ``{key}_display`` still wins (FK names from ``_inject_display_names``).
    Money columns store minor units in ``<name>_minor`` — ``str(1200)``
    invents pence as pounds. Dict refs without ``_display`` must not
    invent ``str(dict)``. Leftover currency junk stays put (format_cell
    refuses ``int("zzz")``). Naive UTC datetimes must not dump as wall
    ISO (oral #126) — ``format_cell`` applies the tenant profile.
    Badge / enum tokens must not dump snake_case when the grid
    title-cases them (oral #130). DSL ``format:`` on decimal amounts
    must not dump bare major units when the grid shows currency
    (oral #131).
    """
    key = column["key"]
    raw = item.get(key)
    if str(column.get("type") or "") == "file":
        return clerk_file_cell_display(item, key, raw)
    display = item.get(f"{key}_display")
    if display is not None and str(display) != "":
        return str(display)
    if raw is None or raw == "":
        return ""
    if isinstance(raw, dict):
        return _resolve_display_name(raw)
    return _csv_typed_cell(raw, column)


def _render_csv_response(
    items: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    region_name: str,
) -> StreamingResponse:
    """Return items as a CSV download."""
    output = io.StringIO()
    col_labels = [c.get("label", c["key"]) for c in columns]

    writer = csv.writer(output)
    writer.writerow(col_labels)
    for item in items:
        writer.writerow([_csv_cell(item, c) for c in columns])

    output.seek(0)
    filename = f"{region_name}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_GRAPH_LIST_FORMATS = frozenset({"cytoscape", "d3"})
_SKIP_LIST_CSV_KEYS = frozenset({"id", "__display__"})


def list_export_kind(raw: Any) -> str:
    """Classify ``?format=`` on an entity list.

    ``csv`` is clerk export (oral #129). ``cytoscape`` / ``d3`` are graph
    (#619). Missing / ``raw`` is JSON/HTML. Anything else is leftover —
    stay put (400), do not invent CSV or a graph.
    """
    text = "" if raw is None else str(raw).strip()
    if not text or text == "raw":
        return "json"
    if text == "csv":
        return "csv"
    if text in _GRAPH_LIST_FORMATS:
        return "graph"
    return "leftover"


def _items_as_dicts(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _columns_for_list_csv(
    columns: list[dict[str, Any]] | None,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if columns:
        return [c for c in columns if isinstance(c, dict) and c.get("key")]
    if not items:
        return []
    return [
        {"key": k, "label": str(k).replace("_", " ").title()}
        for k in items[0]
        if k not in _SKIP_LIST_CSV_KEYS
    ]


def render_entity_list_csv(
    items: list[Any],
    columns: list[dict[str, Any]] | None,
    entity_name: str,
) -> StreamingResponse:
    """Clerk CSV for ``GET /{entities}?format=csv`` (oral #129)."""
    rows = _items_as_dicts(items)
    cols = _columns_for_list_csv(columns, rows)
    slug = (entity_name or "export").replace(" ", "_")
    return _render_csv_response(rows, cols, slug)
