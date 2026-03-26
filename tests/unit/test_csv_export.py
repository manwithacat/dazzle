"""Tests for workspace CSV export (#562)."""

import asyncio
import csv
import io

from dazzle_back.runtime.workspace_rendering import _render_csv_response


def _get_body(resp) -> str:  # type: ignore[no-untyped-def]
    """Extract the full response body from a StreamingResponse."""

    async def _collect() -> str:
        chunks: list[str] = []
        async for chunk in resp.body_iterator:
            chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
        return "".join(chunks)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop (e.g. pytest-asyncio) — create a new one
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(lambda: asyncio.run(_collect())).result()
    return asyncio.run(_collect())


def _parse_csv(response_body: str) -> list[list[str]]:
    """Parse CSV string into rows."""
    reader = csv.reader(io.StringIO(response_body))
    return list(reader)


def test_csv_response_headers():
    """CSV response has correct content type and disposition."""
    columns = [{"key": "name", "label": "Name"}]
    resp = _render_csv_response([{"name": "Alice"}], columns, "tasks")
    assert resp.media_type == "text/csv"
    assert resp.headers["content-disposition"] == 'attachment; filename="tasks.csv"'


def test_csv_header_row_matches_labels():
    """Header row uses column labels, not keys."""
    columns = [
        {"key": "first_name", "label": "First Name"},
        {"key": "status", "label": "Current Status"},
    ]
    resp = _render_csv_response([], columns, "people")
    body = _get_body(resp)
    rows = _parse_csv(body)
    assert rows[0] == ["First Name", "Current Status"]


def test_csv_data_rows():
    """Data rows contain correct item values in column order."""
    columns = [
        {"key": "title", "label": "Title"},
        {"key": "priority", "label": "Priority"},
    ]
    items = [
        {"title": "Fix bug", "priority": "high", "id": "123"},
        {"title": "Add feature", "priority": "low", "id": "456"},
    ]
    resp = _render_csv_response(items, columns, "tasks")
    body = _get_body(resp)
    rows = _parse_csv(body)
    assert len(rows) == 3  # header + 2 data rows
    assert rows[1] == ["Fix bug", "high"]
    assert rows[2] == ["Add feature", "low"]


def test_csv_empty_items_produces_header_only():
    """Empty items list produces a CSV with only the header row."""
    columns = [
        {"key": "name", "label": "Name"},
        {"key": "email", "label": "Email"},
    ]
    resp = _render_csv_response([], columns, "users")
    body = _get_body(resp)
    rows = _parse_csv(body)
    assert len(rows) == 1
    assert rows[0] == ["Name", "Email"]


def test_csv_missing_keys_default_to_empty_string():
    """Items missing a column key produce empty string in that cell."""
    columns = [
        {"key": "name", "label": "Name"},
        {"key": "email", "label": "Email"},
    ]
    items = [{"name": "Alice"}]  # no "email" key
    resp = _render_csv_response(items, columns, "contacts")
    body = _get_body(resp)
    rows = _parse_csv(body)
    assert rows[1] == ["Alice", ""]


def test_csv_label_falls_back_to_key():
    """When a column has no label, the key is used as the header."""
    columns = [{"key": "amount"}]
    resp = _render_csv_response([{"amount": "42"}], columns, "payments")
    body = _get_body(resp)
    rows = _parse_csv(body)
    assert rows[0] == ["amount"]
