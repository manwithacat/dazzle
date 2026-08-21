"""Timeline must rail datetime when, not hide logged_at (oral #143)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.workspace_columns import build_surface_columns
from dazzle.render.filters import _timeago_filter
from dazzle.render.fragment.region._builders_timeline import _timeline_when_col_key
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter


class _FakeTimeline:
    name = "tester_activity"
    title = "Tester activity"
    empty_message = "No recent test sessions logged"


def _session_runtime_columns() -> tuple[object, list[dict[str, object]]]:
    spec = load_project(Path("examples/fieldtest_hub"))
    ir_session = spec.get_entity("TestSession")
    assert ir_session is not None
    runtime = convert_entity(ir_session)
    surface = spec.get_surface("test_session_list")
    cols = build_surface_columns(runtime, surface, spec.enums)
    return runtime, cols


def test_session_logged_at_is_datetime_not_date() -> None:
    _, cols = _session_runtime_columns()
    by = {str(c.get("key") or ""): c for c in cols}
    assert "logged_at" in by
    assert by["logged_at"].get("type") == "datetime"
    assert _timeline_when_col_key(cols) == "logged_at"


def test_timeline_when_col_prefers_datetime_over_skipping() -> None:
    assert (
        _timeline_when_col_key(
            [
                {"key": "notes", "type": "text"},
                {"key": "logged_at", "type": "datetime"},
            ]
        )
        == "logged_at"
    )
    assert (
        _timeline_when_col_key(
            [
                {"key": "release_date", "type": "date"},
                {"key": "created_at", "type": "datetime"},
            ]
        )
        == "release_date"
    )
    assert _timeline_when_col_key([{"key": "notes", "type": "text"}]) == ""
    assert _timeline_when_col_key([]) == ""


def test_timeline_datetime_rail_is_timeago_not_empty() -> None:
    adapter = WorkspaceRegionAdapter()
    notes = "Continuous sampling walk around the campus path."
    logged = "2026-08-01T10:00:00+00:00"
    ctx = {
        "items": [
            {
                "id": "e1000000-0000-4000-8000-000000000001",
                "device": "FT-PROBE-A12",
                "duration_minutes": 45,
                "notes": notes,
                "logged_at": logged,
            }
        ],
        "columns": [
            {"key": "device", "label": "Device", "type": "ref"},
            {"key": "duration_minutes", "label": "Duration (min)", "type": "text"},
            {"key": "logged_at", "label": "Logged At", "type": "datetime"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
        "display_key": "notes",
        "entity_name": "Test Session",
    }
    surface = adapter._build_timeline(_FakeTimeline(), ctx)  # type: ignore[arg-type]
    event = surface.body.body.events[0]  # type: ignore[union-attr]
    assert event.title == notes
    assert event.date_label
    assert event.date_label == _timeago_filter(logged)
    assert "2026-08-01" not in event.date_label
    assert "T10:00" not in event.date_label
    assert not any(label == "Logged At" for label, _ in event.fields)


def test_timeline_datetime_rail_leftover_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "sess-zzz",
                "notes": "Keep leftover visible.",
                "logged_at": "zzz",
            }
        ],
        "columns": [
            {"key": "logged_at", "label": "Logged At", "type": "datetime"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
        "display_key": "notes",
        "entity_name": "Test Session",
    }
    surface = adapter._build_timeline(_FakeTimeline(), ctx)  # type: ignore[arg-type]
    event = surface.body.body.events[0]  # type: ignore[union-attr]
    assert event.date_label == "zzz"
    assert event.title == "Keep leftover visible."


def test_timeline_date_only_rail_still_rides() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [{"title": "1.4.2", "release_date": "2026-08-01"}],
        "columns": [
            {"key": "title", "label": "Version", "type": "text"},
            {"key": "release_date", "label": "Released", "type": "date"},
        ],
        "display_key": "title",
        "entity_name": "Firmware Release",
    }
    surface = adapter._build_timeline(_FakeTimeline(), ctx)  # type: ignore[arg-type]
    event = surface.body.body.events[0]  # type: ignore[union-attr]
    assert event.title == "1.4.2"
    assert event.date_label
    assert "2026-08-01" not in event.date_label
    assert not any(label == "Released" for label, _ in event.fields)
