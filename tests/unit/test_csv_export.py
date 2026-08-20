"""Tests for workspace CSV export (#562)."""

import asyncio
import csv
import io

from dazzle.http.runtime.workspace_csv import _render_csv_response


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


def test_csv_money_minor_does_not_invent_raw_pence():
    """Currency columns store minor units — str(1200) invents pence as pounds (oral #122)."""
    columns = [
        {
            "key": "total_minor",
            "label": "Total",
            "type": "currency",
            "currency_code": "GBP",
        }
    ]
    resp = _render_csv_response([{"total_minor": 1200}], columns, "invoices")
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["£12.00"]


def test_csv_leftover_money_stays_put():
    """Leftover currency junk must not invent £0.00 / a silent 12 (oral #122)."""
    columns = [
        {
            "key": "total_minor",
            "label": "Total",
            "type": "currency",
            "currency_code": "GBP",
        }
    ]
    resp = _render_csv_response(
        [{"total_minor": "zzz"}, {"total_minor": "12abc"}],
        columns,
        "invoices",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["zzz"]
    assert rows[2] == ["12abc"]


def test_csv_dict_ref_does_not_invent_repr():
    """Unresolved FK dicts must not invent str(dict) chrome (oral #122)."""
    columns = [{"key": "assignee", "label": "Assignee", "type": "ref"}]
    resp = _render_csv_response(
        [{"assignee": {"id": "u1", "name": "Ada"}}],
        columns,
        "tasks",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["Ada"]
    assert "{" not in rows[1][0]


def test_csv_naive_utc_datetime_does_not_invent_wall_iso():
    """Naive UTC storage must not dump as wall ``YYYY-MM-DD HH:MM:SS`` (oral #126)."""
    from datetime import datetime

    from dazzle.render.fragment.format_cell import format_cell

    stored = datetime(2026, 8, 18, 14, 30, 0)
    columns = [{"key": "created_at", "label": "Created", "type": "datetime"}]
    resp = _render_csv_response([{"created_at": stored}], columns, "tickets")
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == [format_cell(stored, "datetime")]
    assert rows[1][0] != "2026-08-18 14:30:00"


def test_csv_calendar_date_uses_profile_not_iso():
    """Calendar due dates must not dump ISO when the grid uses the profile (oral #126)."""
    from datetime import date

    from dazzle.render.fragment.format_cell import format_cell

    due = date(2026, 8, 19)
    columns = [{"key": "due_date", "label": "Due", "type": "date"}]
    resp = _render_csv_response([{"due_date": due}], columns, "tasks")
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == [format_cell(due, "date")]
    assert rows[1][0] != "2026-08-19"


def test_csv_leftover_datetime_stays_put():
    """Leftover date junk must not invent a clock / calendar day (oral #126)."""
    columns = [{"key": "created_at", "label": "Created", "type": "datetime"}]
    resp = _render_csv_response(
        [{"created_at": "zzz"}, {"created_at": "2026-06-01zzz"}],
        columns,
        "tickets",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["zzz"]
    assert rows[2] == ["2026-06-01zzz"]


def test_csv_bool_uses_yes_no():
    """Bool columns match the grid Yes/No path; leftover stays put (oral #126)."""
    columns = [{"key": "is_active", "label": "Active", "type": "bool"}]
    resp = _render_csv_response(
        [{"is_active": True}, {"is_active": False}, {"is_active": "zzz"}],
        columns,
        "users",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["Yes"]
    assert rows[2] == ["No"]
    assert rows[3] == ["zzz"]


def test_csv_badge_does_not_invent_raw_token():
    """Enum / SM status CSV must match the grid title-case, not snake_case (oral #130)."""
    from dazzle.render.fragment.format_cell import format_cell

    columns = [
        {
            "key": "status",
            "label": "Status",
            "type": "badge",
            "filter_options": ["open", "in_progress", "resolved"],
        }
    ]
    resp = _render_csv_response(
        [{"status": "in_progress"}, {"status": "open"}],
        columns,
        "tickets",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == [format_cell("in_progress", "badge")]
    assert rows[1][0] == "In Progress"
    assert rows[2] == ["Open"]
    assert rows[1][0] != "in_progress"


def test_csv_leftover_badge_stays_put():
    """Leftover badge junk must not invent a title-cased enum (oral #130)."""
    columns = [
        {
            "key": "status",
            "label": "Status",
            "type": "badge",
            "filter_options": ["open", "in_progress", "resolved"],
        }
    ]
    resp = _render_csv_response(
        [{"status": "zzz"}, {"status": "ghost_state"}],
        columns,
        "tickets",
    )
    rows = _parse_csv(_get_body(resp))
    assert rows[1] == ["zzz"]
    assert rows[2] == ["ghost_state"]
