"""0–100 rate fields must not dump unitless 2.40 (oral #155)."""

from __future__ import annotations

from decimal import Decimal

from dazzle.render.filters import clerk_percent_points_display, clerk_percent_points_field
from dazzle.render.fragment.region._builders_tables import _format_queue_meta_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display


def test_clerk_percent_points_field() -> None:
    assert clerk_percent_points_field("error_rate") is True
    assert clerk_percent_points_field("cpu_usage") is True
    assert clerk_percent_points_field("win_pct") is True
    assert clerk_percent_points_field("fill_percent") is True
    assert clerk_percent_points_field("count") is False
    assert clerk_percent_points_field("zzz") is False
    assert clerk_percent_points_field("1e2") is False


def test_clerk_percent_points_display_adds_percent() -> None:
    assert clerk_percent_points_display(2.40, "error_rate") == "2.4%"
    assert clerk_percent_points_display(Decimal("0.10"), "error_rate") == "0.1%"
    assert clerk_percent_points_display(45, "cpu_usage") == "45%"
    assert clerk_percent_points_display(0, "error_rate") == "0%"
    assert clerk_percent_points_display(0.05, "error_rate") == "0.05%"
    assert clerk_percent_points_display(2.40, "count") == "2.4"


def test_clerk_percent_points_leftover_stays_put() -> None:
    assert clerk_percent_points_display("zzz", "error_rate") == "zzz"
    assert clerk_percent_points_display("1e2", "error_rate") == "1e2"
    assert clerk_percent_points_display("2abc", "cpu_usage") == "2abc"
    assert clerk_percent_points_display(2.40, "zzz") == "2.4"


def test_list_row_percent_points_cell() -> None:
    html = _render_cell_display({"key": "error_rate", "type": "percentage"}, Decimal("2.40"))
    assert html == "2.4%"
    leftover = _render_cell_display({"key": "error_rate", "type": "percentage"}, "zzz")
    assert leftover == "zzz"
    unitless = _render_cell_display({"key": "count", "type": "text"}, Decimal("2.40"))
    assert unitless != "2.4%"


def test_typed_percentage_column_keeps_percent_suffix() -> None:
    """#1505 characterization: type=percentage must keep % even when the
    key is not ``*_rate`` / ``*_usage`` (cycle 2288 dropped ``pct`` → ``42``)."""
    html = _render_cell_display({"key": "pct", "type": "percentage"}, 42)
    assert html == "42%"
    leftover = _render_cell_display({"key": "pct", "type": "percentage"}, "zzz")
    assert leftover == "zzz"
    untyped = clerk_percent_points_display(42, "pct")
    assert untyped == "42"


def test_queue_meta_percent_points() -> None:
    shown = _format_queue_meta_value(
        Decimal("2.40"), {"key": "error_rate", "type": "percentage", "label": "Error Rate"}
    )
    assert shown == "2.4%"
    leftover = _format_queue_meta_value(
        "zzz", {"key": "error_rate", "type": "percentage", "label": "Error Rate"}
    )
    assert leftover == "zzz"
    cpu = _format_queue_meta_value(
        "71.00", {"key": "cpu_usage", "type": "text", "label": "CPU Usage"}
    )
    assert cpu == "71%"
