"""#1843 (cyfuture WCAG 2.2 audit) — the enhanced combobox in Chromium.

A required ``widget=combobox`` with a scrolling option list, between two
plain fields, rendered through the real emitter with the shipped CSS and the
HM controller:

* one Tab stop (2.4.3): Tab from the combobox lands on the next field, never
  on the listbox;
* leaving closes it (2.4.11): the listbox is hidden once focus is on the next
  field, so it cannot cover it;
* the label stays honest (3.3.2): the required marker is visible, the label's
  ``for`` targets the visible input, and input + listbox are named by the
  label span rather than a copy of its text.

Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dazzle.render.fragment import Field, FragmentRenderer, WidgetCombobox  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
CSS = REPO_ROOT / "src/dazzle/page/runtime/static/dist/dazzle.min.css"
JS = REPO_ROOT / "packages/hatchi-maxchi/controllers/dz-combobox.js"


@pytest.fixture(scope="module")
def browser() -> Any:
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


def _form() -> str:
    r = FragmentRenderer()
    combo = r.render(
        WidgetCombobox(
            name="deadline_type",
            label="Type",
            options=tuple((f"t{i}", f"Type {i}") for i in range(9)),
            required=True,
        )
    )
    before = r.render(Field(name="title", label="Title"))
    after = r.render(Field(name="due", label="Due date"))
    return (
        '<!doctype html><html><body><form style="width:30rem">'
        f"{before}{combo}{after}<button>Save</button></form></body></html>"
    )


def _state(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const root = document.querySelector(".dz-combobox");
            const list = document.querySelector(".dz-combobox-listbox");
            const input = document.querySelector(".dz-combobox-input");
            const label = document.querySelector("label.dz-field");
            const span = label.querySelector(".dz-field__label");
            return {
                active: document.activeElement.id,
                open: root && root.getAttribute("data-dz-open"),
                listVisible: !!list && list.getBoundingClientRect().height > 0,
                scrolls: !!list && list.scrollHeight > list.clientHeight,
                listTabindex: list && list.getAttribute("tabindex"),
                labelFor: label.htmlFor,
                inputId: input && input.id,
                inputLabelledby: input && input.getAttribute("aria-labelledby"),
                listLabelledby: list && list.getAttribute("aria-labelledby"),
                inputAriaLabel: input && input.getAttribute("aria-label"),
                spanId: span.id,
                marker: !!span.querySelector(".dz-form-required"),
            };
        }"""
    )


def test_combobox_is_one_tab_stop_and_closes_on_leave(browser: Any) -> None:
    page = browser.new_page(viewport={"width": 800, "height": 900})
    page.set_content(_form())
    page.add_style_tag(path=str(CSS))
    page.add_script_tag(path=str(JS))

    page.focus("#field-title")
    page.keyboard.press("Tab")  # onto the select → enhances, focus moves to the input
    s = _state(page)
    assert s["active"] == "field-deadline_type-input"
    assert s["open"] == "true" and s["listVisible"]
    assert s["scrolls"], "fixture must overflow the listbox to exercise the Tab-stop bug"
    assert s["listTabindex"] == "-1"

    page.keyboard.press("Tab")
    s = _state(page)
    assert s["active"] == "field-due", "the listbox must not be a Tab stop"
    assert s["open"] is None and not s["listVisible"], "listbox must close when focus leaves"

    # Focus that leaves from inside the listbox (pointer on its scrollbar,
    # then Tab) closes it too.
    page.focus("#field-deadline_type-input")
    page.focus("#field-deadline_type-listbox")
    page.keyboard.press("Tab")
    s = _state(page)
    assert s["open"] is None and not s["listVisible"]

    # 3.3.2: marker kept; label + names point at the visible control.
    assert s["marker"]
    assert s["labelFor"] == s["inputId"] == "field-deadline_type-input"
    assert s["inputLabelledby"] == s["listLabelledby"] == s["spanId"] == "field-deadline_type-label"
    assert s["inputAriaLabel"] is None
    page.close()
