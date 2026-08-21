"""Queue/timeline must not drop expanded money or title ISO dates (oral #136)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.workspace_columns import build_surface_columns
from dazzle.http.runtime.workspace_region_render import _pick_display_key
from dazzle.render.fragment.region._builders_tables import (
    _format_queue_meta_value,
    _queue_row_meta_columns,
)
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.region._shared import format_minor_money_display


class _FakeRegion:
    name = "salary_queue"
    title = "Salary queue"
    empty_message = "No active salaries"


def _salary_runtime_columns() -> tuple[object, object, list[dict[str, object]]]:
    spec = load_project(Path("examples/hr_records"))
    ir_sal = spec.get_entity("Salary")
    runtime = convert_entity(ir_sal)
    surface = spec.get_surface("salary_list")
    cols = build_surface_columns(runtime, surface, spec.enums)
    return runtime, surface, cols


def test_surface_columns_keep_money_after_runtime_expansion() -> None:
    _runtime, _surface, cols = _salary_runtime_columns()
    by = {c["key"]: c for c in cols}
    assert "amount_minor" in by
    assert by["amount_minor"]["type"] == "currency"
    assert by["amount_minor"]["currency_code"] == "GBP"
    assert by["amount_minor"]["label"] == "Amount"
    assert _pick_display_key(cols) == "amount_minor"


def test_format_minor_money_pence_is_sterling() -> None:
    assert format_minor_money_display(7141688, currency_code="GBP") == "£71,416.88"


def test_format_minor_money_leftover_stays_put() -> None:
    assert format_minor_money_display("zzz", currency_code="GBP") == "zzz"


def test_queue_meta_amount_minor_is_sterling_not_pence() -> None:
    col = {"key": "amount_minor", "label": "Amount", "type": "currency", "currency_code": "GBP"}
    assert "£71,416.88" in _format_queue_meta_value(7141688, col)
    leftover = _format_queue_meta_value("zzz", col)
    assert leftover == "zzz"


def test_queue_title_is_sterling_not_iso_date() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "23a8025a-045d-403d-bd4f-cf39d5a2fb8a",
                "person": "a1000000-0000-4000-8000-000000000008",
                "amount_minor": 7141688,
                "amount_currency": "GBP",
                "effective_from": "2024-06-01",
                "effective_to": None,
                "reason": "promotion",
            }
        ],
        "columns": [
            {"key": "person", "label": "Person", "type": "ref"},
            {
                "key": "amount_minor",
                "label": "Amount",
                "type": "currency",
                "currency_code": "GBP",
            },
            {"key": "effective_from", "label": "From", "type": "date"},
            {"key": "reason", "label": "Reason", "type": "badge"},
        ],
        "total": 1,
        "display_key": "amount_minor",
        "queue_status_field": "reason",
        "queue_api_endpoint": "/api/salary",
        "queue_transitions": [],
        "region_name": "salary_queue",
    }
    surface = adapter._build_queue(_FakeRegion(), ctx)  # type: ignore[arg-type]
    row = surface.body.body.rows[0]
    assert row.title == "£71,416.88"
    assert "2024-06-01" not in row.title
    assert "7141688" not in row.title


def test_queue_leftover_minor_title_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "sal-1",
                "amount_minor": "zzz",
                "amount_currency": "GBP",
                "effective_from": "2024-06-01",
                "reason": "promotion",
            }
        ],
        "columns": [
            {
                "key": "amount_minor",
                "label": "Amount",
                "type": "currency",
                "currency_code": "GBP",
            },
            {"key": "effective_from", "label": "From", "type": "date"},
            {"key": "reason", "label": "Reason", "type": "badge"},
        ],
        "total": 1,
        "display_key": "amount_minor",
        "queue_status_field": "reason",
        "region_name": "salary_queue",
    }
    surface = adapter._build_queue(_FakeRegion(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.rows[0].title == "zzz"


def test_timeline_title_is_sterling_not_iso_date() -> None:
    adapter = WorkspaceRegionAdapter()

    class _Tl:
        name = "salary_list"
        title = "Salary list"
        empty_message = "No active salaries"

    ctx = {
        "items": [
            {
                "id": "sal-1",
                "amount_minor": 7141688,
                "amount_currency": "GBP",
                "effective_from": "2024-06-01",
                "reason": "promotion",
            }
        ],
        "columns": [
            {
                "key": "amount_minor",
                "label": "Amount",
                "type": "currency",
                "currency_code": "GBP",
            },
            {"key": "effective_from", "label": "From", "type": "date"},
            {"key": "reason", "label": "Reason", "type": "badge"},
        ],
        "display_key": "amount_minor",
        "entity_name": "Salary",
    }
    surface = adapter._build_timeline(_Tl(), ctx)  # type: ignore[arg-type]
    event = surface.body.body.events[0]
    assert event.title == "£71,416.88"
    assert "2024-06-01" not in event.title


def test_queue_meta_skips_title_minor() -> None:
    item = {
        "id": "sal-1",
        "amount_minor": 7141688,
        "amount_currency": "GBP",
        "effective_from": "2024-06-01",
        "reason": "promotion",
    }
    cols = [
        {
            "key": "amount_minor",
            "label": "Amount",
            "type": "currency",
            "currency_code": "GBP",
        },
        {"key": "effective_from", "label": "From", "type": "date"},
        {"key": "reason", "label": "Reason", "type": "badge"},
    ]
    meta = _queue_row_meta_columns(
        item, cols, display_key="amount_minor", queue_status_field="reason"
    )
    assert all(m.label != "Amount" for m in meta)
