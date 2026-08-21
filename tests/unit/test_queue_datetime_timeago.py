"""Queue datetime must not dump storage ISO on meta (oral #156)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import field_kind_to_col_type
from dazzle.render.filters import _timeago_filter
from dazzle.render.fragment.region._builders_tables import _format_queue_meta_value
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter


class _FakeQueue:
    name = "ack_queue"
    title = "Ack"
    display = "queue"
    empty_message = "All alerts acknowledged"


def test_ops_dashboard_alert_triggered_at_is_datetime() -> None:
    spec = load_project(Path("examples/ops_dashboard"))
    alert = next(e for e in spec.domain.entities if e.name == "Alert")
    triggered = next(f for f in alert.fields if f.name == "triggered_at")
    system = next(e for e in spec.domain.entities if e.name == "System")
    last_check = next(f for f in system.fields if f.name == "last_check")
    assert field_kind_to_col_type(triggered, alert) == "datetime"
    assert field_kind_to_col_type(last_check, system) == "datetime"


def test_queue_datetime_uses_timeago_not_iso() -> None:
    triggered = datetime(2026, 5, 18, 14, 30, tzinfo=UTC)
    surface = WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
        _FakeQueue(),
        {
            "items": [
                {
                    "id": "a1000000-0000-4000-8000-000000000001",
                    "message": "CPU spike on api-gateway",
                    "severity": "critical",
                    "triggered_at": triggered,
                }
            ],
            "columns": [
                {"key": "message", "label": "Message", "type": "text"},
                {"key": "severity", "label": "Severity", "type": "badge"},
                {"key": "triggered_at", "label": "Triggered At", "type": "datetime"},
            ],
            "display_key": "message",
        },
    )
    row = surface.body.body.rows[0]  # type: ignore[union-attr]
    assert row.date_columns
    assert row.date_columns[0].timeago_str == _timeago_filter(triggered)
    assert "2026-05-18" not in row.date_columns[0].timeago_str
    assert not any("2026-05-18" in m.value for m in row.meta_columns)
    assert not any("14:30" in m.value for m in row.meta_columns)


def test_queue_datetime_leftover_stays_put() -> None:
    surface = WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
        _FakeQueue(),
        {
            "items": [
                {
                    "id": "a1000000-0000-4000-8000-000000000002",
                    "message": "CPU spike on api-gateway",
                    "triggered_at": "zzz",
                }
            ],
            "columns": [
                {"key": "message", "label": "Message", "type": "text"},
                {"key": "triggered_at", "label": "Triggered At", "type": "datetime"},
            ],
            "display_key": "message",
        },
    )
    row = surface.body.body.rows[0]  # type: ignore[union-attr]
    assert row.date_columns[0].timeago_str == "zzz"
    leftover = _format_queue_meta_value(
        "zzz", {"key": "triggered_at", "type": "datetime", "label": "Triggered At"}
    )
    assert leftover == "zzz"


def test_queue_date_still_timeago() -> None:
    due = "2026-05-18"
    surface = WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
        SimpleNamespace(
            name="due_queue",
            title="Due",
            display="queue",
            empty_message="Nothing due",
        ),
        {
            "items": [
                {
                    "id": "t1000000-0000-4000-8000-000000000001",
                    "title": "File taxes",
                    "due_date": due,
                }
            ],
            "columns": [
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "due_date", "label": "Due", "type": "date"},
            ],
            "display_key": "title",
        },
    )
    row = surface.body.body.rows[0]  # type: ignore[union-attr]
    assert row.date_columns[0].timeago_str == _timeago_filter(due)
    assert not any(m.label == "Due" for m in row.meta_columns)
