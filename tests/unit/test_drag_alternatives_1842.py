"""#1842 WCAG 2.5.7 Dragging Movements: every drag has a single-pointer path.

cyfuture's audit found three drag-only interactions. Each now has a click
alternative that runs the same code as the drag, driven here in Chromium on
real SSR markup:

* Dashboard cards: a Card options menu (edit mode, like the remove ×) with
  Move up / Move down / Narrower / Wider; a read-only grid neither drags nor
  resizes.
* List columns: each Columns menu row has Narrower / Wider buttons, and the
  resize handle is a focusable separator (Left/Right, Home resets). A list
  too small for the Columns menu has no resize handles.
* Kanban in-column reorder (rank boards): Move up / Move down buttons PUT
  the same midpoint rank as the drop.

Skipped without Playwright or a Chromium build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pw = pytest.importorskip("playwright.sync_api")

from dazzle.render.fragment import (  # noqa: E402
    ColumnVisibilityMenu,
    DashboardCard,
    DashboardGrid,
    FragmentRenderer,
    Table,
)
from dazzle.render.fragment.ingest.emit import render_kanban_card  # noqa: E402
from dazzle.render.fragment.ingest.models import KanbanCard  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
JS = REPO_ROOT / "src/dazzle/page/runtime/static/js"
HM = REPO_ROOT / "packages/hatchi-maxchi/controllers"


@pytest.fixture(scope="module")
def page() -> Any:
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"chromium unavailable: {exc}")
        pg = browser.new_page()
        yield pg
        browser.close()


def _card(i: int, *, edit: bool) -> DashboardCard:
    return DashboardCard(
        card_id=f"card-{i}",
        name=f"r{i}",
        title=f"Region {i}",
        display="LIST",
        col_span=6,
        row_order=i,
        hx_endpoint=f"/api/workspaces/ops/regions/r{i}",
        edit_enabled=edit,
    )


def _load_dashboard(page: Any, *, edit: bool) -> None:
    grid = FragmentRenderer().render(
        DashboardGrid(cards=tuple(_card(i, edit=edit) for i in range(3)), edit_enabled=edit)
    )
    page.set_content(
        "<!doctype html><html><body>"
        f'<div data-dz-dashboard-builder data-workspace-name="ops">{grid}</div>'
        "</body></html>"
    )
    page.add_script_tag(path=str(JS / "dashboard-builder.js"))


def _layout(page: Any) -> list[tuple[str, str]]:
    return page.evaluate(
        """() => [...document.querySelectorAll('[data-grid-container] [data-card-id]')]
              .map(c => [c.dataset.cardId, c.dataset.cardColSpan])"""
    )


def _live(page: Any) -> str:
    return page.evaluate("() => document.getElementById('dz-live-region')?.textContent || ''")


def _op(page: Any, card: str, op: str) -> None:
    page.click(f'[data-card-id="{card}"] [data-test-id="dz-card-options"]')
    page.click(f'[data-card-id="{card}"] [data-dz-card-op="{op}"]')


def test_card_options_menu_moves_and_resizes_cards(page: Any) -> None:
    _load_dashboard(page, edit=True)
    assert [c for c, _ in _layout(page)] == ["card-0", "card-1", "card-2"]

    _op(page, "card-0", "move-down")
    assert [c for c, _ in _layout(page)] == ["card-1", "card-0", "card-2"]
    assert _live(page) == "Card moved to position 2"
    # The menu closes and focus returns to its trigger.
    assert page.evaluate(
        """() => {
            const s = document.querySelector('[data-card-id="card-0"] [data-test-id="dz-card-options"]');
            return document.activeElement === s && !s.parentElement.open;
        }"""
    )

    _op(page, "card-2", "move-up")
    assert [c for c, _ in _layout(page)] == ["card-1", "card-2", "card-0"]

    _op(page, "card-1", "move-up")
    assert _live(page) == "Already first"

    _op(page, "card-1", "wider")
    assert dict(_layout(page))["card-1"] == "8"
    _op(page, "card-1", "narrower")
    _op(page, "card-1", "narrower")
    assert dict(_layout(page))["card-1"] == "4"
    assert _live(page) == "4 columns"

    # Every op is undoable like its drag.
    page.evaluate("() => document.querySelector('[data-dz-dashboard-builder]')._dzBuilder.undo()")
    assert dict(_layout(page))["card-1"] == "6"


def test_read_only_grid_neither_drags_nor_offers_the_menu(page: Any) -> None:
    _load_dashboard(page, edit=False)
    assert page.query_selector('[data-test-id="dz-card-options"]') is None
    header = page.locator('[data-card-id="card-0"] [data-test-id="dz-card-drag-handle"]')
    box = header.bounding_box()
    page.mouse.move(box["x"] + 10, box["y"] + 10)
    page.mouse.down()
    page.mouse.move(box["x"] + 10, box["y"] + 400, steps=8)
    page.mouse.up()
    assert [c for c, _ in _layout(page)] == ["card-0", "card-1", "card-2"]
    assert (
        page.evaluate(
            "() => document.querySelector('[data-dz-dashboard-builder]')._dzBuilder.undoStack.length"
        )
        == 0
    )


_COLS = (("name", "Name"), ("email", "Email"), ("plan", "Plan"), ("seats", "Seats"))


def _list_html(cols: tuple[tuple[str, str], ...]) -> str:
    r = FragmentRenderer()
    table = r.render(
        Table(
            columns=tuple(label for _, label in cols),
            rows=(),
            column_keys=tuple(k for k, _ in cols),
            skeleton=True,
            hx_endpoint="/rows",
        )
    )
    return r.render(ColumnVisibilityMenu(columns=cols)) + table


def _load_grid(page: Any) -> None:
    page.set_content(
        # An empty table sizes its columns to the headers — give it room so a
        # step is not swallowed by the 80px clamp.
        "<!doctype html><html><head><style>table { width: 960px; }</style></head><body>"
        f'<div data-dz-grid id="g">{_list_html(_COLS)}</div>'
        "</body></html>"
    )
    page.add_script_tag(path=str(HM / "dz-grid-resize.js"))


def _col_width(page: Any, key: str) -> str:
    return page.evaluate(f"() => document.querySelector('col[data-dz-col=\"{key}\"]').style.width")


def test_columns_menu_steps_width_and_announces(page: Any) -> None:
    _load_grid(page)
    page.click("summary.dz-table-col-menu-trigger")
    start = page.evaluate("() => document.querySelector('col[data-dz-col=\"plan\"]').offsetWidth")
    page.click('[data-dz-grid-width="plan"][data-dz-step="1"]')
    wider = int(_col_width(page, "plan").removesuffix("px"))
    assert wider > start
    status = page.text_content("[data-dz-grid-width-status]")
    assert status == f"Plan column width {wider} pixels"
    page.click('[data-dz-grid-width="plan"][data-dz-step="-1"]')
    assert int(_col_width(page, "plan").removesuffix("px")) == wider - 24


def test_resize_handle_is_a_keyboard_separator(page: Any) -> None:
    _load_grid(page)
    handle = '[data-dz-grid-resize="email"]'
    assert page.get_attribute(handle, "role") == "separator"
    assert page.get_attribute(handle, "aria-label") == "Resize Email column"
    page.focus(handle)
    before = int(page.get_attribute(handle, "aria-valuenow"))
    page.keyboard.press("ArrowRight")
    after = int(page.get_attribute(handle, "aria-valuenow"))
    assert after > before
    page.keyboard.press("Home")
    assert _col_width(page, "email") == ""


def test_list_without_columns_menu_has_no_resize_handles() -> None:
    html = FragmentRenderer().render(
        Table(
            columns=("Name", "Plan", "Seats"),
            rows=(),
            column_keys=("name", "plan", "seats"),
            skeleton=True,
            hx_endpoint="/rows",
        )
    )
    assert "data-dz-grid-resize" not in html


def _kanban_card(cid: str, rank: int | None) -> str:
    return render_kanban_card(
        KanbanCard(
            title=f"Card {cid}",
            row_id=cid,
            from_state="open",
            allowed_to=("done",),
            rank=rank,
        )
    )


def _load_kanban(page: Any) -> None:
    cards = "".join(_kanban_card(c, r) for c, r in (("a", 1000), ("b", 2000), ("c", 3000)))
    page.set_content(
        "<!doctype html><html><body>"
        '<div data-dz-kanban-board data-dz-kanban-rearrange="status" '
        'data-dz-kanban-status-field="status" data-dz-kanban-api="/api/tasks" '
        'data-dz-kanban-src="/board" data-dz-kanban-rank-field="rank">'
        "<span data-dz-kanban-announce></span>"
        f'<div data-dz-kanban-stack data-dz-to-state="open">{cards}</div></div>'
        "<script>window.__puts = []; window.fetch = function (url, opts) {"
        " window.__puts.push([url, JSON.parse(opts.body)]);"
        " return Promise.resolve({ok: true, status: 200}); };"
        " window.htmx = {ajax: function () { return Promise.resolve(); }};</script>"
        "</body></html>"
    )
    page.add_script_tag(path=str(HM / "dz-kanban.js"))


def test_kanban_order_buttons_put_the_drop_rank(page: Any) -> None:
    _load_kanban(page)
    assert page.get_attribute("#dz-kanban-card-b [data-dz-kanban-step='-1']", "aria-label") == (
        "Move Card b up"
    )
    page.click("#dz-kanban-card-b [data-dz-kanban-step='-1']")
    page.click("#dz-kanban-card-b [data-dz-kanban-step='1']")
    page.wait_for_function("() => window.__puts.length === 2")
    puts = page.evaluate("() => window.__puts")
    # Up: before a (rank 1000) with nothing above → half of 1000.
    assert puts[0] == ["/api/tasks/b", {"rank": 500}]
    # Down: lands between c (3000) and the end → c + 1000.
    assert puts[1] == ["/api/tasks/b", {"rank": 4000}]
    page.click("#dz-kanban-card-a [data-dz-kanban-step='-1']")
    assert page.text_content("[data-dz-kanban-announce]") == "Already first"


def test_kanban_without_rank_has_no_order_buttons() -> None:
    assert "data-dz-kanban-step" not in _kanban_card("a", None)
