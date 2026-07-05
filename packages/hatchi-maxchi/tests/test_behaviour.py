"""Console-domain behaviour gates — the interactive contracts, in a real
browser against the committed gallery (file://, mock htmx).

Regression pins for the two launch bugs:
- Esc must close the palette on the FIRST press even mid-query
  (input type="search" natively swallows Esc to clear its value).
- The light/dark toggle must actually flip rendered colours (a page-level
  color-scheme declaration once overrode the [data-theme] binding).
"""

from pathlib import Path

import pytest

_SITE_URI = (Path(__file__).resolve().parents[1] / "site" / "index.html").as_uri()

PALETTE = "dialog.command"
INPUT = ".command__input"

# Behaviour runs in BOTH Chromium and WebKit (Safari's engine). WebKit
# catches Safari/iPadOS regressions the keyboard-only + Chromium tests
# miss — e.g. the command palette's close button collapsing to 0×0 under
# absolute positioning in a modal <dialog> (v0.93.34, fixed by the flex
# bar). This module OVERRIDES the shared chromium-only `page` fixture;
# visual/wcag stay on chromium (their baselines are chromium-rendered).
_ENGINES = ["chromium", "webkit"]


@pytest.fixture(params=_ENGINES, scope="module")
def _engine_browser(request):  # type: ignore[no-untyped-def]
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        engine = getattr(p, request.param, None)
        if engine is None:
            pytest.skip(f"{request.param} not installed")
        try:
            b = engine.launch()
        except Exception as exc:  # noqa: BLE001 — a missing engine binary should skip, not error
            pytest.skip(f"{request.param} unavailable: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(_engine_browser):  # type: ignore[no-untyped-def]  # noqa: F811 (overrides conftest)
    pg = _engine_browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(_SITE_URI)
    pg.wait_for_timeout(200)
    yield pg
    assert not errors, f"gallery page threw JS errors: {errors}"
    pg.close()


def _open_palette(page) -> None:  # type: ignore[no-untyped-def]
    page.click("[data-hm-open-command]")
    page.wait_for_timeout(150)
    assert page.evaluate(f"document.querySelector('{PALETTE}').open")


def test_palette_opens_via_button_and_cmd_k(page) -> None:  # type: ignore[no-untyped-def]
    _open_palette(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    page.keyboard.press("Meta+k")
    page.wait_for_timeout(100)
    assert page.evaluate(f"document.querySelector('{PALETTE}').open")


def test_palette_esc_closes_even_with_query_text(page) -> None:  # type: ignore[no-untyped-def]
    _open_palette(page)
    page.fill(f"{PALETTE} {INPUT}", "inv")
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open"), (
        "first Esc mid-query must close the palette (search inputs swallow "
        "Esc natively — dz-command.js handles it explicitly)"
    )


def test_palette_closes_via_backdrop_tap(page) -> None:  # type: ignore[no-untyped-def]
    """A touch device has no Esc key — tapping outside the palette (the
    backdrop) MUST close it, or a mobile user is trapped. Regression pin
    for the bug the keyboard-only tests never caught."""
    _open_palette(page)
    # The palette is top-anchored + centered; (8, 8) is backdrop, not the box.
    page.mouse.click(8, 8)
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open"), (
        "backdrop tap must close the palette (the only pointer-only dismiss path)"
    )


def test_palette_close_button_is_rendered_and_placed(page) -> None:  # type: ignore[no-untyped-def]
    """The close button must have a real box and sit at the top-right of the
    dialog. Direct pin for the v0.93.34 Safari bug: absolute positioning
    against a modal <dialog> collapsed the button to 0×0 in WebKit, so it was
    invisible and untappable. The flex bar fixed it — assert it in WebKit."""
    _open_palette(page)
    box = page.evaluate(
        "() => { const b = document.querySelector('.command__close').getBoundingClientRect();"
        " const d = document.querySelector('dialog.command').getBoundingClientRect();"
        " return {w: b.width, h: b.height, topRight: b.right > d.right - 70 && b.top < d.top + 70}; }"
    )
    assert box["w"] > 10 and box["h"] > 10, f"close button collapsed ({box}) — the Safari 0×0 bug"
    assert box["topRight"], "close button must sit at the dialog's top-right"


def test_palette_closes_via_close_button(page) -> None:  # type: ignore[no-untyped-def]
    """The always-visible close button is the discoverable dismiss
    affordance (touch has no Esc)."""
    _open_palette(page)
    page.click("[data-hm-close-command]")
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open"), (
        "the close button must close the palette"
    )


def test_palette_arrows_and_enter(page) -> None:  # type: ignore[no-untyped-def]
    _open_palette(page)
    page.focus(f"{PALETTE} {INPUT}")  # focus triggers the mock hx-get
    page.wait_for_timeout(200)
    count = page.evaluate(f"document.querySelectorAll('{PALETTE} .command__item').length")
    assert count >= 3, "mock results should populate on focus"
    # afterSwap preselects index 0; two ArrowDowns land on index 2
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    selected = page.evaluate(
        f"document.querySelectorAll('{PALETTE} .command__item')[2].getAttribute('aria-selected')"
    )
    assert selected == "true"


def test_confirm_dialog_intercepts_hx_confirm(page) -> None:  # type: ignore[no-untyped-def]
    # The gallery mock fires the real htmx-4 `htmx:confirm` shape (config under
    # detail.ctx, issueRequest/dropRequest). This guards the full flow, not just
    # dialog-open, so an htmx-detail-shape drift (which silently degrades the
    # designed dialog to native window.confirm) is caught.
    # Scope to the confirm Hyperpart's own button (hx-delete) — the grid's bulk
    # Delete also carries hx-confirm now (with hx-post), so a bare [hx-confirm]
    # is ambiguous.
    trigger = "[hx-delete][hx-confirm]"
    question = page.get_attribute(trigger, "hx-confirm")
    page.click(trigger)
    page.wait_for_timeout(150)
    assert page.evaluate(
        "!!document.querySelector('dialog.alert-dialog') && "
        "document.querySelector('dialog.alert-dialog').open"
    ), "clicking an hx-confirm element must open the designed dz-alert-dialog"
    # message is populated from the event payload (proves the confirm text was
    # read off the htmx-4 detail.ctx.confirm, not a stale detail.question)
    assert page.inner_text("dialog.alert-dialog .alert-dialog__message").strip() == question, (
        "the designed dialog must show the hx-confirm text"
    )
    # accepting issues the request (the mock flags it with a toast)
    page.click("dialog.alert-dialog [data-confirm-accept]")
    page.wait_for_timeout(150)
    assert page.query_selector(".hm-toast") is not None, (
        "confirming must call issueRequest() (htmx-4 continuation) — the request was dropped"
    )
    assert not page.evaluate("document.querySelector('dialog.alert-dialog').open"), (
        "the dialog must close after confirm"
    )


def test_grid_selection_reveals_and_clears_the_bulk_bar(page) -> None:  # type: ignore[no-untyped-def]
    """dz-grid selection is delegated + state-in-DOM: checking rows writes the
    count to data-bulk-count on the root, the CSS reveals the bulk bar, select-all
    reflects the tri-state, and Clear resets it. (Gallery classes are un-prefixed.)"""
    root, bar, boxes = "[data-grid]", ".bulk-actions", "[data-grid-select]"
    disp = "e => getComputedStyle(e).display"

    # Default: nothing selected, bar hidden.
    assert page.get_attribute(root, "data-bulk-count") == "0"
    assert page.eval_on_selector(bar, disp) == "none"

    # Select one row → count 1, bar revealed, summary mirrors the count.
    page.locator(boxes).first.check()
    page.wait_for_timeout(80)
    assert page.get_attribute(root, "data-bulk-count") == "1"
    assert page.eval_on_selector(bar, disp) != "none"
    assert page.inner_text("[data-bulk-count-target]").strip() == "1"
    # the count sits in a polite live region so SRs announce "N selected"
    assert page.eval_on_selector(
        "[data-bulk-count-target]",
        "e => e.closest('[aria-live=polite]') !== null",
    ), "the selection count must be inside an aria-live=polite region"

    # Select-all → every row checked, count == N, header box fully checked.
    n = page.eval_on_selector_all(boxes, "els => els.length")
    page.check("[data-grid-select-all]")
    page.wait_for_timeout(80)
    assert page.get_attribute(root, "data-bulk-count") == str(n)
    assert page.eval_on_selector("[data-grid-select-all]", "e => e.checked && !e.indeterminate")

    # Clear → back to zero, bar hidden again.
    page.click("[data-grid-clear]")
    page.wait_for_timeout(80)
    assert page.get_attribute(root, "data-bulk-count") == "0"
    assert page.eval_on_selector(bar, disp) == "none"


def test_grid_hydrates_rows_via_exchange_with_stable_ids(page) -> None:  # type: ignore[no-untyped-def]
    """The tbody hydrates its rows over the wire (hx-get on `load`, the gallery
    mock). The hydrated rows carry a stable `id` — the idiomorph morph key — so a
    selection follows its ROW (not its DOM position) across a re-sort/paginate in
    a real innerMorph swap. `data-grid-row-id` stays the bulk-payload anchor; the
    `id` encodes it, so the two agree. (Gallery classes are un-prefixed.)"""
    body = "[data-grid-body]"
    boxes = "[data-grid-select]"

    # By the fixture's 200ms wait the `load` exchange has replaced the skeleton
    # placeholder with the real rows — there are selectable checkboxes now.
    n = page.eval_on_selector_all(boxes, "els => els.length")
    assert n == 4, "the tbody hydrates the first page (page_size 4 of 6 rows)"
    # the skeleton placeholder is gone — hydrated rows carry no skeleton
    assert page.eval_on_selector_all(f"{body} .skeleton", "els => els.length") == 0, (
        "the skeleton placeholder must be replaced by the hydrated rows"
    )

    # Every hydrated row exposes a stable, unique id that encodes its row-id.
    report = page.eval_on_selector_all(
        boxes,
        "els => els.map(b => { const tr = b.closest('tr');"
        " return { id: tr && tr.id, rowId: b.getAttribute('data-grid-row-id') }; })",
    )
    ids = [r["id"] for r in report]
    assert all(ids), f"every hydrated row needs a stable id (the morph key): {report}"
    assert len(set(ids)) == len(ids), f"row ids must be unique (idiomorph de-dupes on id): {ids}"
    for r in report:
        assert r["rowId"] and r["id"].endswith(r["rowId"]), (
            f"the row id (morph key) must encode data-grid-row-id (payload anchor): {r}"
        )

    # Selection still works on the hydrated rows: checking one reveals the bar.
    page.locator(boxes).first.check()
    page.wait_for_timeout(80)
    assert page.get_attribute("[data-grid]", "data-bulk-count") == "1", (
        "selection must work on the hydrated rows (afterSwap re-sync)"
    )


def _grid_names(page):  # type: ignore[no-untyped-def]
    """The First-name column (first data cell) of each hydrated row, in DOM order."""
    return page.eval_on_selector_all(
        "[data-grid-body] tr",
        "trs => trs.map(tr => { const c = tr.querySelector('.tr-cell');"
        " return c ? c.textContent.trim() : null; }).filter(Boolean)",
    )


def _aria_sort(page, key):  # type: ignore[no-untyped-def]
    return page.eval_on_selector(
        f"[data-grid-sort='{key}']", "b => b.closest('th').getAttribute('aria-sort')"
    )


def test_grid_sort_cycles_direction_and_reorders_rows(page) -> None:  # type: ignore[no-untyped-def]
    """A sortable header cycles none → ascending → descending → none (state on the
    th's aria-sort, delegated + state-in-DOM), and each click reloads the tbody
    over the wire (dz-grid:refresh → the sort/dir query → the mock returns the
    sorted rows). No client-side row rendering — the server owns the order."""
    # Unsorted at rest: PAGE 1 (page_size 4) of the mock's scrambled order.
    assert _aria_sort(page, "first") == "none"
    natural_p1 = ["Mia", "Ravi", "Amir", "Sofia"]
    assert _grid_names(page) == natural_p1

    # 1st click → ascending by first name (page 1 of the sorted set).
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(120)
    assert _aria_sort(page, "first") == "ascending"
    assert _grid_names(page) == ["Amir", "Jane", "Mia", "Noah"]

    # 2nd click → descending (page 1 of the reversed set).
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(120)
    assert _aria_sort(page, "first") == "descending"
    assert _grid_names(page) == ["Sofia", "Ravi", "Noah", "Mia"]

    # 3rd click → cleared: back to the natural order, header neutral again.
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(120)
    assert _aria_sort(page, "first") == "none"
    assert _grid_names(page) == natural_p1


def test_grid_sort_is_single_column(page) -> None:  # type: ignore[no-untyped-def]
    """Only one column is sorted at a time: sorting a second column clears the
    first's aria-sort (one server ORDER BY, one active indicator). Sorting by a
    DIFFERENT column yields a visibly different order — the diagnostic the sparse
    data lacked."""
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(120)
    assert _aria_sort(page, "first") == "ascending"
    assert _grid_names(page)[0] == "Amir", "first-name asc leads with Amir"

    page.click("[data-grid-sort='last']")
    page.wait_for_timeout(120)
    assert _aria_sort(page, "last") == "ascending", "the newly-clicked column sorts"
    assert _aria_sort(page, "first") == "none", "the previously-sorted column resets"
    # last-name asc leads with Alvarez (Sofia) — a DIFFERENT order than first-name
    assert _grid_names(page)[0] == "Sofia", "sorting by last name reorders differently"


def test_grid_filter_narrows_rows_over_the_wire(page) -> None:  # type: ignore[no-untyped-def]
    """Changing a filter select ([data-grid-filter]) rebuilds the tbody query and
    reloads it — the server returns only the matching rows. The 'Any …' option
    (empty value) clears the filter."""
    assert len(_grid_names(page)) == 4  # page 1 of 6

    page.select_option("[data-grid-filter='plan']", "Free")
    page.wait_for_timeout(120)
    # insertion order (no active sort): Sofia (cust_4) before Jane (cust_6)
    assert _grid_names(page) == ["Sofia", "Jane"], "plan=Free narrows to the two Free rows"

    page.select_option("[data-grid-filter='plan']", "")  # Any plan → cleared
    page.wait_for_timeout(120)
    assert len(_grid_names(page)) == 4, "clearing the filter restores every row (page 1)"


def test_grid_filter_composes_with_sort(page) -> None:  # type: ignore[no-untyped-def]
    """Filter and sort compose in one query built from the DOM state: sorting then
    filtering keeps BOTH — the sorted, filtered rows come back and the sort
    indicator is preserved."""
    page.click("[data-grid-sort='first']")  # ascending
    page.wait_for_timeout(120)
    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(120)
    # the two Pro rows, still first-name-ascending (Amir before Noah)
    assert _grid_names(page) == ["Amir", "Noah"]
    assert _aria_sort(page, "first") == "ascending", "the active sort survives a filter change"


def test_grid_filter_to_zero_reveals_empty_state(page) -> None:  # type: ignore[no-untyped-def]
    """A filter combination matching no rows returns an empty tbody, and the
    CSS `:has(tbody tr td)`-driven empty-state appears (the server owns emptiness;
    the client invents nothing)."""
    disp = "e => getComputedStyle(e).display"
    assert page.eval_on_selector(".table-empty", disp) == "none", (
        "empty-state hidden while populated"
    )

    # Free + Churned matches nobody (both Free customers are Trialing).
    page.select_option("[data-grid-filter='plan']", "Free")
    page.select_option("[data-grid-filter='status']", "Churned")
    page.wait_for_timeout(150)
    assert _grid_names(page) == [], "no rows match the filter combination"
    assert page.eval_on_selector(".table-empty", disp) != "none", (
        "the empty-state must reveal when the filtered result is empty"
    )


def test_grid_search_narrows_rows_debounced(page) -> None:  # type: ignore[no-untyped-def]
    """Typing in the search box narrows the rows over the wire after a debounce
    (the server matches; the client just adds `q=` to the query). Clearing it
    restores every row (page 1)."""
    assert len(_grid_names(page)) == 4  # page 1 of 6

    page.fill("[data-grid-search]", "chen")
    page.wait_for_timeout(350)  # > the debounce
    assert _grid_names(page) == ["Mia"], "search matches across fields (last name Chen)"

    page.fill("[data-grid-search]", "")
    page.wait_for_timeout(350)
    assert len(_grid_names(page)) == 4, "clearing search restores every row (page 1)"


def _bulk_confirm_delete(page) -> None:  # type: ignore[no-untyped-def]
    """Click the bulk Delete and approve the designed confirm dialog."""
    page.click(".bulk-delete")
    page.wait_for_timeout(150)
    assert page.evaluate("document.querySelector('dialog.alert-dialog').open"), (
        "the bulk Delete must go through the designed confirm dialog"
    )
    page.click("dialog.alert-dialog [data-confirm-accept]")
    page.wait_for_timeout(200)


def test_grid_bulk_delete_removes_selected_rows(page) -> None:  # type: ignore[no-untyped-def]
    """Selecting rows and confirming Delete posts the selection, the server
    removes exactly those rows and returns the refreshed tbody, and the selection
    (and its bar) clears. (Gallery mock mutates its row set.)"""
    page.locator("[data-grid-select]").nth(0).check()  # Mia
    page.locator("[data-grid-select]").nth(1).check()  # Ravi
    page.wait_for_timeout(80)
    assert page.get_attribute("[data-grid]", "data-bulk-count") == "2"

    _bulk_confirm_delete(page)

    names = _grid_names(page)
    assert len(names) == 4 and "Mia" not in names and "Ravi" not in names, (
        f"the two selected rows must be gone: {names}"
    )
    assert page.get_attribute("[data-grid]", "data-bulk-count") == "0", (
        "the selection (and bar) must clear after the action"
    )


def test_grid_bulk_payload_carries_selection_and_query(page) -> None:  # type: ignore[no-untyped-def]
    """The posted payload carries the action, the selected ids, the all-matching /
    excluded shape, AND an echo of the current query — so the server re-scopes the
    action to what the user was viewing and never trusts client ids alone."""
    page.select_option("[data-grid-filter='plan']", "Pro")  # Amir, Noah
    page.wait_for_timeout(120)
    page.locator("[data-grid-select]").first.check()  # Amir
    page.wait_for_timeout(80)
    amir_id = page.eval_on_selector("[data-grid-select]", "b => b.getAttribute('data-grid-row-id')")

    _bulk_confirm_delete(page)

    payload = page.evaluate("window.__lastBulk")
    assert payload["action"] == "delete"
    assert amir_id in payload["selected_ids"], "the payload carries the selected ids"
    assert payload["all_matching_selected"] == "false", (
        "all-matching shape present (false until paging)"
    )
    assert payload["excluded_ids"] == [], "excluded-ids shape present"
    assert payload["plan"] == "Pro", (
        "the payload echoes the current query (re-scope, never trust ids)"
    )
    assert _grid_names(page) == ["Noah"], "only Amir deleted; Noah remains under the Pro filter"


def test_grid_bulk_delete_on_last_page_reclamps(page) -> None:  # type: ignore[no-untyped-def]
    """Deleting the only rows on the last page removes that page — the client
    re-syncs the root's page from the server-rendered footer (which clamped it),
    so no stale page lingers (the classic delete-on-last-page bug)."""
    page.click("[data-grid-page-next]")  # page 2: Noah, Jane
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Noah", "Jane"]
    assert page.get_attribute("[data-grid]", "data-grid-page") == "2"

    page.locator("[data-grid-select]").nth(0).check()  # Noah
    page.locator("[data-grid-select]").nth(1).check()  # Jane
    page.wait_for_timeout(80)
    _bulk_confirm_delete(page)

    # 4 rows remain (one page); the root must re-sync to the clamped page 1.
    assert page.get_attribute("[data-grid]", "data-grid-page") == "1", (
        "the root re-syncs to the server-clamped page after the last page is emptied"
    )
    assert _grid_names(page) == ["Mia", "Ravi", "Amir", "Sofia"], "the surviving page 1 shows"


def test_grid_bulk_payload_keys_win_over_query_echo(page) -> None:  # type: ignore[no-untyped-def]
    """A query param that collides with a bulk-payload key (e.g. a filter named
    'action') must NOT clobber the operation — the payload keys are written last
    so they always win."""
    page.eval_on_selector(
        "[data-grid-body]",
        "b => b.setAttribute('hx-get', b.getAttribute('data-grid-src') + '?action=archive')",
    )
    page.locator("[data-grid-select]").first.check()
    page.wait_for_timeout(80)
    _bulk_confirm_delete(page)
    assert page.evaluate("window.__lastBulk").get("action") == "delete", (
        "the bulk action must win over an echoed query key named 'action'"
    )


def _page_summary(page):  # type: ignore[no-untyped-def]
    return page.eval_on_selector(
        "[data-grid-pagination] .pagination-summary", "e => e.textContent.trim()"
    )


def test_grid_paginates_and_navigates(page) -> None:  # type: ignore[no-untyped-def]
    """The server-rendered footer pages the result set (page_size 4 of 6): prev
    is disabled on page 1, next on the last page, and prev / next / a page number
    each reload the tbody for that page."""
    assert _grid_names(page) == ["Mia", "Ravi", "Amir", "Sofia"], "page 1"
    assert _page_summary(page) == "1-4 of 6"
    assert page.eval_on_selector("[data-grid-page-prev]", "b => b.disabled") is True, (
        "prev is disabled on the first page"
    )

    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Noah", "Jane"], "page 2 shows the remaining rows"
    assert _page_summary(page) == "5-6 of 6"
    assert page.eval_on_selector("[data-grid-page-next]", "b => b.disabled") is True, (
        "next is disabled on the last page"
    )

    page.click("[data-grid-page-prev]")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Mia", "Ravi", "Amir", "Sofia"], "prev returns to page 1"

    page.click("[data-grid-goto='2']")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Noah", "Jane"], "a page-number jump goes straight there"


def test_grid_sort_persists_across_pages(page) -> None:  # type: ignore[no-untyped-def]
    """Sort is applied to the whole result set server-side, so page 2 continues
    the ordered sequence (not a re-sort of the visible page)."""
    page.click("[data-grid-sort='first']")  # ascending
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Amir", "Jane", "Mia", "Noah"], "sorted page 1"
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Ravi", "Sofia"], "sorted page 2 continues the order"


def test_grid_change_resets_to_page_one(page) -> None:  # type: ignore[no-untyped-def]
    """A sort / filter / search change resets the page to 1 (spec) — you never
    land on page 2 of a freshly-narrowed result."""
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-page") == "2"

    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-page") == "1", "sort resets to page 1"
    assert _grid_names(page) == ["Amir", "Jane", "Mia", "Noah"], "page 1 of the sorted set"

    # a filter change also resets to page 1
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-page") == "1", "filter resets to page 1"
    page.select_option("[data-grid-filter='plan']", "")  # clear
    page.wait_for_timeout(150)

    # and a search change resets to page 1
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    page.fill("[data-grid-search]", "chen")
    page.wait_for_timeout(350)
    assert page.get_attribute("[data-grid]", "data-grid-page") == "1", "search resets to page 1"


def test_grid_search_debounce_coalesces_keystrokes(page) -> None:  # type: ignore[no-untyped-def]
    """A burst of keystrokes makes exactly ONE request, not one per key. Counts
    the `dz-grid:refresh` events (un-prefixed `grid:refresh` in the gallery). A
    long debounce makes the timing robust: during the burst nothing fires; one
    request lands after it settles."""
    page.eval_on_selector("[data-grid-search]", "e => e.setAttribute('data-grid-debounce', '400')")
    page.evaluate(
        "window.__gridRefreshes = 0;"
        "document.addEventListener('grid:refresh', () => { window.__gridRefreshes++; });"
    )
    # type 4 chars quickly; each `input` resets the (400ms) timer
    page.type("[data-grid-search]", "amir", delay=20)
    page.wait_for_timeout(150)  # still inside the debounce window
    assert page.evaluate("window.__gridRefreshes") == 0, (
        "keystrokes must NOT each fire a request (debounce still pending)"
    )
    page.wait_for_timeout(450)  # let the debounce settle
    assert page.evaluate("window.__gridRefreshes") == 1, (
        "the burst must coalesce into exactly one request"
    )
    assert _grid_names(page) == ["Amir"], "the one request applied the final search value"


def test_grid_search_composes_with_filter(page) -> None:  # type: ignore[no-untyped-def]
    """Search composes with sort/filter — all read from the DOM into one query."""
    page.select_option("[data-grid-filter='plan']", "Pro")  # Amir, Noah
    page.wait_for_timeout(120)
    page.fill("[data-grid-search]", "okafor")  # last name Okafor → Amir
    page.wait_for_timeout(350)
    assert _grid_names(page) == ["Amir"], "search + filter compose to one matching row"
    assert page.eval_on_selector("[data-grid-filter='plan']", "s => s.value") == "Pro", (
        "the active filter survives a search"
    )


def test_grid_loading_overlay_is_wired_to_htmx_request(page) -> None:  # type: ignore[no-untyped-def]
    """Loading is pure-CSS (#972): htmx's native `.htmx-request` on any grid
    descendant reveals the `.dz-table-loading` overlay — no controller JS, so
    idiomorph can't strip a JS-held loading flag. At rest the overlay is hidden;
    injecting `.htmx-request` (as htmx does mid-flight) shows it."""
    overlay = ".table-loading"
    disp = "e => getComputedStyle(e).display"
    assert page.query_selector(overlay) is not None, "the grid must carry a loading overlay"
    assert page.eval_on_selector(overlay, disp) == "none", "overlay hidden at rest (no request)"

    # htmx adds `.htmx-request` to the request-initiating element in flight.
    page.eval_on_selector("[data-grid-body]", "el => el.classList.add('htmx-request')")
    page.wait_for_timeout(50)
    assert page.eval_on_selector(overlay, disp) != "none", (
        "an in-flight `.htmx-request` on a descendant must reveal the overlay"
    )
    page.eval_on_selector("[data-grid-body]", "el => el.classList.remove('htmx-request')")
    page.wait_for_timeout(50)
    assert page.eval_on_selector(overlay, disp) == "none", "overlay hides when the request settles"


def test_copy_button_copies_and_gives_feedback(_engine_browser) -> None:  # type: ignore[no-untyped-def]
    # Headless WebKit blocks navigator.clipboard.writeText (and rejects the
    # clipboard-* permissions), so the button's feedback never fires there.
    # This is a clipboard-API limitation, not a Safari layout/interaction
    # concern (the palette dismiss is), so the copy contract is Chromium-only.
    if _engine_browser.browser_type.name == "webkit":
        pytest.skip("clipboard write is unavailable in headless WebKit")
    ctx = _engine_browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.goto(_SITE_URI)
    page.wait_for_timeout(200)
    page.evaluate("document.querySelectorAll('.hm-copy')[0].click()")
    page.wait_for_timeout(150)
    assert page.evaluate("document.querySelectorAll('.hm-copy')[0].hasAttribute('data-copied')"), (
        "copy click must flip the button into its Copied state"
    )
    try:
        clip = page.evaluate("navigator.clipboard.readText()")
        assert clip.strip().startswith("<"), "clipboard should hold the snippet HTML"
    except Exception:  # noqa: BLE001 — clipboard read unsupported on this engine
        pass
    # feedback reverts, and no stuck focus/hover state remains
    page.wait_for_timeout(1800)
    assert not page.evaluate(
        "document.querySelectorAll('.hm-copy')[0].hasAttribute('data-copied')"
    ), "Copied state must revert"
    assert page.evaluate("document.activeElement.className") != "hm-copy", (
        "button must blur after copy so no focus state lingers"
    )
    ctx.close()


def test_theme_toggle_flips_rendered_colours(page) -> None:  # type: ignore[no-untyped-def]
    light = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.evaluate("document.querySelector('input[data-hm-theme=dark]').click()")
    page.wait_for_timeout(150)
    dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert dark != light, "selecting Dark must change the rendered background"
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    page.evaluate("document.querySelector('input[data-hm-theme=light]').click()")
    page.wait_for_timeout(150)
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == light


def test_theme_choice_persists_across_reload(page) -> None:  # type: ignore[no-untyped-def]
    page.evaluate("document.querySelector('input[data-hm-theme=dark]').click()")
    page.wait_for_timeout(100)
    page.reload()
    page.wait_for_timeout(200)
    assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "dark"
    assert page.evaluate("document.querySelector('input[data-hm-theme=dark]').checked")


def test_dialog_opens_and_closes_natively(page) -> None:  # type: ignore[no-untyped-def]
    """The dialog opens from its trigger (the one scripted behaviour) and
    closes with no extra JS: the ✕ is a <form method="dialog"> submit, and
    Esc is native <dialog> cancel. Runs in WebKit too — Safari's <dialog>."""
    dlg = "dialog.dialog"
    assert not page.evaluate(f"document.querySelector('{dlg}').open")
    page.click("[data-dialog-open]")
    page.wait_for_timeout(120)
    assert page.evaluate(f"document.querySelector('{dlg}').open"), "trigger must open the dialog"
    # native close via the method="dialog" submit (the ✕ button)
    page.click(f"{dlg} .dialog__close")
    page.wait_for_timeout(120)
    assert not page.evaluate(f"document.querySelector('{dlg}').open"), (
        "a method='dialog' submit (the ✕) must close the dialog — no JS needed"
    )
    # reopen, then Esc (native <dialog> cancel) closes
    page.click("[data-dialog-open]")
    page.wait_for_timeout(120)
    page.keyboard.press("Escape")
    page.wait_for_timeout(120)
    assert not page.evaluate(f"document.querySelector('{dlg}').open"), "Esc must close the dialog"


def test_dialog_instance_isolation(page) -> None:  # type: ignore[no-untyped-def]
    """The opener addresses each dialog by id (getElementById), so a second
    dialog with its own id opens independently — N dialogs coexist with no
    shared global handle (contrast the command palette's page singleton)."""
    page.evaluate(
        "() => { const d = document.querySelector('dialog.dialog');"
        " const c = d.cloneNode(true); c.id = 'hm-dialog-clone';"
        # strip the cloned title id + labelledby so the live DOM has no dup id
        " c.removeAttribute('aria-labelledby');"
        " const h = c.querySelector('.dialog__title'); if (h) h.removeAttribute('id');"
        " const t = document.createElement('button');"
        " t.id = 'clone-trigger'; t.setAttribute('data-dialog-open', 'hm-dialog-clone');"
        " d.after(c); d.after(t); }"
    )
    page.wait_for_timeout(50)
    page.click("#clone-trigger")
    page.wait_for_timeout(120)
    # the CLONE opened; the original stays shut — addressed-by-id isolation
    assert page.evaluate("document.getElementById('hm-dialog-clone').open"), (
        "the clone's trigger must open the clone"
    )
    assert not page.evaluate("document.getElementById('hm-dialog-demo').open"), (
        "opening one dialog must not open the other (instance isolation)"
    )


def test_tabs_switch_and_lazy_load(page) -> None:  # type: ignore[no-untyped-def]
    """dz-tabs.js: clicking a tab reveals its panel (hiding siblings) and moves
    aria-current, all scoped to the .dz-tabs root; revealing a hidden panel
    triggers its `intersect once` lazy load (the mock's IntersectionObserver)."""
    cur = '#tabs .tabs__tab[aria-current="true"]'
    assert page.evaluate(f"document.querySelector('{cur}').textContent") == "Overview"
    assert page.evaluate("document.getElementById('hm-tab-activity').hidden")
    page.click('#tabs .tabs__tab[data-tab-target="hm-tab-activity"]')
    page.wait_for_timeout(400)
    assert not page.evaluate("document.getElementById('hm-tab-activity').hidden"), (
        "clicking a tab reveals its panel"
    )
    assert page.evaluate("document.getElementById('hm-tab-overview').hidden"), (
        "the prior panel hides"
    )
    assert page.evaluate(f"document.querySelector('{cur}').textContent") == "Activity", (
        "aria-current moves to the active tab"
    )
    assert "3 events today" in page.inner_text("#hm-tab-activity"), (
        "revealing a hidden panel triggers its intersect-once lazy load"
    )


def test_slider_updates_value_readout(page) -> None:  # type: ignore[no-untyped-def]
    """dz-slider.js writes the range value into the group's [data-range-value]
    readout on input, scoped to the slider's own group."""
    page.eval_on_selector(
        "#slider input[type=range]",
        "el => { el.value = '30'; el.dispatchEvent(new Event('input', {bubbles: true})); }",
    )
    page.wait_for_timeout(100)
    assert page.inner_text("#slider [data-range-value]").strip() == "30", (
        "the value readout must reflect the slider value on input"
    )


def test_slider_skips_widget_managed_inputs(page) -> None:  # type: ignore[no-untyped-def]
    """The load-bearing guard: HM's dz-slider.js must NOT touch a range managed
    by a widget bridge ([data-widget] wrapper) — that's what keeps it a no-op on
    a host (e.g. Dazzle) that wires its own range controller."""
    page.evaluate(
        "() => { var d = document.createElement('div'); d.id = 'wm';"
        ' d.innerHTML = \'<div data-widget="range-tooltip" class="form-slider-group">'
        '<input type="range" data-slider value="50">'
        "<span data-range-value>UNTOUCHED</span></div>';"
        " document.body.appendChild(d); }"
    )
    page.eval_on_selector(
        "#wm input[type=range]",
        "el => { el.value = '10'; el.dispatchEvent(new Event('input', {bubbles: true})); }",
    )
    page.wait_for_timeout(100)
    assert page.inner_text("#wm [data-range-value]").strip() == "UNTOUCHED", (
        "HM's controller must skip [data-widget]-managed ranges (the host owns them)"
    )


def test_drawer_opens_via_shared_opener_and_closes(page) -> None:  # type: ignore[no-untyped-def]
    """The drawer is a native <dialog> anchored to the edge; it reuses the
    dialog's opener (no drawer-specific JS) and closes natively. Proves the
    shared dz-dialog.js drives a *second* Hyperpart's trigger."""
    dw = "dialog.drawer"
    assert not page.evaluate(f"document.querySelector('{dw}').open")
    page.click('[data-dialog-open="hm-drawer-demo"]')
    page.wait_for_timeout(150)
    assert page.evaluate(f"document.querySelector('{dw}').open"), (
        "drawer opens via the SHARED dz-dialog.js opener (no drawer-specific JS)"
    )
    page.click(f"{dw} .drawer__close")
    page.wait_for_timeout(150)
    assert not page.evaluate(f"document.querySelector('{dw}').open"), (
        "the ✕ (a method=dialog submit) closes the drawer natively"
    )
    # reopen, then Esc (native <dialog> cancel) closes — the headline claim
    page.click('[data-dialog-open="hm-drawer-demo"]')
    page.wait_for_timeout(150)
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    assert not page.evaluate(f"document.querySelector('{dw}').open"), "Esc must close the drawer"


def test_master_detail_selection_and_instance_isolation(page) -> None:  # type: ignore[no-untyped-def]
    """The master-detail composite: clicking a list item selects it (aria-current
    moves) AND the controller is instance-isolated — a second master-detail on
    the page manages its own selection without touching the first."""
    md_item = ".master-detail__item"
    assert len(page.query_selector_all(md_item)) >= 3

    # select item 2 in the (only) master-detail
    page.click('.master-detail__item[hx-get$="inv-002"]')
    page.wait_for_timeout(120)
    cur = lambda sel: page.eval_on_selector(sel, "el => el.getAttribute('aria-current')")  # noqa: E731
    assert cur('.master-detail__item[hx-get$="inv-002"]') == "true"
    assert cur('.master-detail__item[hx-get$="inv-001"]') is None
    # the detail pane loaded the inv-002 card fragment via hx-get
    assert "Globex" in page.inner_text(".master-detail__detail")

    # clone the whole master-detail as a SECOND instance
    page.evaluate(
        "() => { const md = document.querySelector('.master-detail');"
        " const c = md.cloneNode(true); c.setAttribute('data-clone','1');"
        " md.after(c); }"
    )
    page.wait_for_timeout(50)
    # click item 3 inside the CLONE
    page.click('[data-clone] .master-detail__item[hx-get$="inv-003"]')
    page.wait_for_timeout(120)
    # clone selects item 3; the ORIGINAL still has item 2 — isolation holds
    assert cur('[data-clone] .master-detail__item[hx-get$="inv-003"]') == "true"
    assert cur('.master-detail:not([data-clone]) .master-detail__item[hx-get$="inv-002"]') == "true"
