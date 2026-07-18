"""#1623 — workspace list datetime cells use format_cell / DisplayLocaleProfile."""

from __future__ import annotations

from datetime import UTC, datetime

from dazzle.render.fragment.region._shared import _render_typed_value


def _html(frag: object) -> str:
    return str(getattr(frag, "html", frag))


def test_datetime_column_not_raw_iso() -> None:
    item = {"created_at": datetime(2026, 7, 17, 15, 38, 29, 874803, tzinfo=UTC)}
    col = {"key": "created_at", "type": "datetime"}
    html = _html(_render_typed_value(item, col))
    assert "+00:00" not in html
    assert "874803" not in html
    # Still shows the calendar day in some form
    assert "2026" in html or "Jul" in html or "17" in html


def test_date_column_formatted() -> None:
    item = {"due": "2026-07-17"}
    col = {"key": "due", "type": "date"}
    html = _html(_render_typed_value(item, col))
    assert "+00:00" not in html
    assert "2026" in html or "Jul" in html or "17" in html


def test_text_column_iso_datetime_defensive() -> None:
    """Mistyped text columns with ISO strings should still humanise."""
    item = {"ts": "2026-07-17 15:38:29.874803+00:00"}
    col = {"key": "ts", "type": "text"}
    html = _html(_render_typed_value(item, col))
    assert "874803" not in html
    assert "+00:00" not in html


def test_empty_datetime_emdash() -> None:
    frag = _render_typed_value({"created_at": None}, {"key": "created_at", "type": "datetime"})
    assert _html(frag) == "—"
