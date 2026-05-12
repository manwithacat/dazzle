"""CSV export response builder for workspace list regions.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Single pure helper — no I/O, no DB, no IR dispatch. Takes resolved
items + pre-computed column metadata in, returns a streaming
``text/csv`` response with a content-disposition attachment header.
"""

import csv
import io
from typing import Any

from starlette.responses import StreamingResponse


def _render_csv_response(
    items: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    region_name: str,
) -> StreamingResponse:
    """Return items as a CSV download."""
    output = io.StringIO()
    col_keys = [c["key"] for c in columns]
    col_labels = [c.get("label", c["key"]) for c in columns]

    writer = csv.writer(output)
    writer.writerow(col_labels)
    for item in items:
        row = [str(item.get(f"{k}_display", item.get(k, ""))) for k in col_keys]
        writer.writerow(row)

    output.seek(0)
    filename = f"{region_name}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
