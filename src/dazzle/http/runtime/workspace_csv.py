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
"""

import csv
import io
from datetime import date, datetime
from typing import Any

from starlette.responses import StreamingResponse

from dazzle.render.display_names import _resolve_display_name
from dazzle.render.fragment.format_cell import format_cell


def _csv_cell(item: dict[str, Any], column: dict[str, Any]) -> str:
    """Clerk-facing CSV cell — same honesty as the list grid.

    ``{key}_display`` still wins (FK names from ``_inject_display_names``).
    Money columns store minor units in ``<name>_minor`` — ``str(1200)``
    invents pence as pounds. Dict refs without ``_display`` must not
    invent ``str(dict)``. Leftover currency junk stays put (format_cell
    refuses ``int("zzz")``). Naive UTC datetimes must not dump as wall
    ISO (oral #126) — ``format_cell`` applies the tenant profile.
    """
    key = column["key"]
    display = item.get(f"{key}_display")
    if display is not None and str(display) != "":
        return str(display)
    raw = item.get(key)
    if raw is None or raw == "":
        return ""
    if isinstance(raw, dict):
        return _resolve_display_name(raw)
    kind = str(column.get("type") or "")
    if kind == "currency":
        return format_cell(
            raw,
            "currency",
            currency_code=str(column.get("currency_code") or "GBP"),
        )
    if kind in ("date", "datetime"):
        return format_cell(raw, kind)
    if isinstance(raw, datetime):
        return format_cell(raw, "datetime")
    if isinstance(raw, date):
        return format_cell(raw, "date")
    if isinstance(raw, bool):
        return format_cell(raw, "bool")
    return str(raw)


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
