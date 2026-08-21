"""Timeline must not title sessions as raw duration minutes (oral #137)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.workspace_columns import build_surface_columns
from dazzle.http.runtime.workspace_region_render import _entity_display_field, _pick_display_key
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


def test_session_display_field_is_notes_not_duration() -> None:
    runtime, cols = _session_runtime_columns()
    assert str(getattr(runtime, "display_field", "") or "") == "notes"
    preferred = _entity_display_field(type("Ctx", (), {"entity_spec": runtime})())
    assert preferred == "notes"
    assert _pick_display_key(cols, preferred=preferred) == "notes"
    assert _pick_display_key(cols) != "duration_minutes"


def test_timeline_title_is_notes_not_duration_minutes() -> None:
    adapter = WorkspaceRegionAdapter()
    notes = "Continuous sampling walk around the campus path."
    ctx = {
        "items": [
            {
                "id": "e1000000-0000-4000-8000-000000000001",
                "device": "FT-PROBE-A12",
                "tester": "Alex Field",
                "duration_minutes": 45,
                "environment": "outdoor",
                "temperature": 28.5,
                "notes": notes,
                "logged_at": "2026-08-01T10:00:00+00:00",
            }
        ],
        "columns": [
            {"key": "device", "label": "Device", "type": "ref"},
            {"key": "tester", "label": "Tester", "type": "ref"},
            {"key": "duration_minutes", "label": "Duration (min)", "type": "text"},
            {"key": "environment", "label": "Environment", "type": "badge"},
            {"key": "temperature", "label": "Temperature", "type": "text"},
            {"key": "logged_at", "label": "Logged At", "type": "datetime"},
        ],
        "display_key": "notes",
        "entity_name": "Test Session",
    }
    surface = adapter._build_timeline(_FakeTimeline(), ctx)  # type: ignore[arg-type]
    event = surface.body.body.events[0]  # type: ignore[union-attr]
    assert event.title == notes
    assert "45" not in event.title


def test_timeline_leftover_notes_title_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "sess-zzz",
                "duration_minutes": 45,
                "notes": "zzz",
                "logged_at": "2026-08-01T10:00:00+00:00",
            }
        ],
        "columns": [
            {"key": "duration_minutes", "label": "Duration (min)", "type": "text"},
            {"key": "notes", "label": "Notes", "type": "text"},
        ],
        "display_key": "notes",
        "entity_name": "Test Session",
    }
    surface = adapter._build_timeline(_FakeTimeline(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.events[0].title == "zzz"  # type: ignore[union-attr]
