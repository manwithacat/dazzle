"""Native <select> chrome must not clip option text (CyFuture letter filters).

Queue/list filter bars emit bare ``<select class="dz-queue-filter-select">``
/ ``dz-filter-select``, not the combobox Hyperpart. base.css pads every
``select``; a short ``height`` plus UA chrome clips "All Status".
``select.dz-form-input`` already pins height + appearance:none (#930).
"""

from pathlib import Path

QUEUE = Path("packages/hatchi-maxchi/components/queue.css")
TABLE = Path("packages/hatchi-maxchi/components/table.css")
FORM = Path("packages/hatchi-maxchi/components/form.css")
SHELL = Path("packages/hatchi-maxchi/components/workspace-shell.css")


def _block(path: Path, start: str, max_chars: int = 900) -> str:
    css = path.read_text()
    idx = css.index(start)
    return css[idx : idx + max_chars]


def test_queue_filter_select_not_short_native_chrome() -> None:
    block = _block(QUEUE, ".dz-queue-filter-select {")
    assert "height: 1.75rem" not in block
    assert "appearance: none" in block
    assert "line-height: 1.4" in block
    assert "padding-block:" in block


def test_list_filter_select_pins_webkit_height() -> None:
    block = _block(TABLE, "select.dz-filter-select {")
    assert "appearance: none" in block
    assert "height: 2rem" in block


def test_form_and_context_selects_flatten_ua_chrome() -> None:
    form = _block(FORM, "select.dz-form-input {")
    assert "appearance: none" in form
    money = _block(FORM, ".dz-form-money-select {")
    assert "appearance: none" in money
    ctx = _block(SHELL, ".dz-workspace-context-select {")
    assert "appearance: none" in ctx
    assert "height: 2rem" in ctx
