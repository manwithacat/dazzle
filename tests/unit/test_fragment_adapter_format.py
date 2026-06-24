"""#1470 Phase 1 — the http fragment adapter's _format_cell delegates to the
pure render formatter (it used to str()-coerce everything)."""

from dazzle.http.runtime.renderers.fragment_adapter import _cell_value, _format_cell


def test_ref_cell_prefers_display() -> None:
    # #1471: a ref column renders the resolved {key}_display, not the raw UUID.
    item = {"academic_year": "d0e6d87c-uuid", "academic_year_display": "2025-2026"}
    assert _cell_value(item, {"key": "academic_year", "type": "ref"}) == "2025-2026"


def test_ref_cell_falls_back_to_raw_when_no_display() -> None:
    item = {"academic_year": "d0e6d87c-uuid"}
    assert _cell_value(item, {"key": "academic_year", "type": "ref"}) == "d0e6d87c-uuid"


def test_non_ref_cell_uses_bare_key() -> None:
    # A non-ref column ignores any _display sibling.
    item = {"status": "active", "status_display": "ignored"}
    assert _cell_value(item, {"key": "status", "type": "badge"}) == "active"


def test_adapter_delegates_to_formatter() -> None:
    assert _format_cell(True, "bool") == "Yes"
    assert _format_cell(False, "bool") == "No"
    assert _format_cell("ACTIVE", "badge") == "Active"
    assert _format_cell(None, "text") == ""


def test_adapter_threads_currency() -> None:
    assert _format_cell(12345, "currency", "GBP") == "£123.45"


def test_adapter_returns_raw() -> None:
    # Raw — the renderer escapes at emit time (no pre-escape / double-escape).
    assert _format_cell("<x>", "text") == "<x>"
