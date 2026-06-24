"""#1470 Phase 1 — the http fragment adapter's _format_cell delegates to the
pure render formatter (it used to str()-coerce everything)."""

from dazzle.http.runtime.renderers.fragment_adapter import _format_cell


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
