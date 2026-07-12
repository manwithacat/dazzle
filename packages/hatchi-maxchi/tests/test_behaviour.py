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

from conftest import goto_part, part_uri  # noqa: E402

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
    goto_part(page, "command")
    _open_palette(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    page.keyboard.press("Meta+k")
    page.wait_for_timeout(100)
    assert page.evaluate(f"document.querySelector('{PALETTE}').open")


def test_menubar_exclusive_open(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery probe menubar.exclusive_open — File then Edit leaves only Edit open."""
    goto_part(page, "menubar")
    item = "details.dz-menubar__item, details.menubar__item"
    trigger = "summary.dz-menubar__trigger, summary.menubar__trigger"
    page.locator(trigger).filter(has_text="File").first.click()
    page.wait_for_timeout(80)
    page.locator(trigger).filter(has_text="Edit").first.click()
    page.wait_for_timeout(80)
    open_n = page.locator(f"{item}[open]").count()
    labels = page.locator(f"{item}[open] summary").all_text_contents()
    labels = [" ".join(t.split()) for t in labels]
    assert open_n == 1, f"expected exclusive open, got {open_n}: {labels}"
    assert labels == ["Edit"], labels


def test_navigation_menu_exclusive_open(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery probe navigation_menu.exclusive_open — one mega panel at a time."""
    goto_part(page, "navigation-menu")
    root = "[data-dz-navigation-menu], .dz-navigation-menu, .navigation-menu"
    item = f"{root} details"
    trigger = "summary.dz-navigation-menu__trigger, summary.navigation-menu__trigger"
    page.locator(trigger).filter(has_text="Product").first.click()
    page.wait_for_timeout(80)
    page.locator(trigger).filter(has_text="Resources").first.click()
    page.wait_for_timeout(80)
    open_n = page.locator(f"{item}[open]").count()
    labels = page.locator(f"{item}[open] summary").all_text_contents()
    labels = [" ".join(t.split()) for t in labels]
    assert open_n == 1, f"expected exclusive open, got {open_n}: {labels}"
    assert any("Resources" in t for t in labels), labels


def test_tree_multi_open(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery probe tree.multi_open — sibling branches stay open together."""
    goto_part(page, "tree")
    # Scope to gallery demo — contract-live preview mounts a second forest
    scope = page.locator(".hm-preview")
    item = "details.dz-tree-node, details.tree-node"
    trigger = "summary.dz-tree-summary, summary.tree-summary"
    scope.locator(trigger).filter(has_text="Platform").first.click()
    page.wait_for_timeout(80)
    scope.locator(trigger).filter(has_text="Design systems").first.click()
    page.wait_for_timeout(80)
    labels = scope.locator(f"{item}[open] > summary").all_text_contents()
    labels = [" ".join(t.split()) for t in labels]
    joined = " ".join(labels)
    assert "Platform" in joined and "Design systems" in joined, labels
    assert "Engineering" in joined, labels


def test_menubar_dismiss_outside(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery probe menubar.dismiss_outside — click outside closes File."""
    goto_part(page, "menubar")
    scope = page.locator(".hm-preview")
    item = "details.dz-menubar__item, details.menubar__item"
    trigger = "summary.dz-menubar__trigger, summary.menubar__trigger"
    scope.locator(trigger).filter(has_text="File").first.click()
    page.wait_for_timeout(80)
    assert scope.locator(f"{item}[open]").count() == 1
    page.mouse.click(8, 8)
    page.wait_for_timeout(100)
    assert scope.locator(f"{item}[open]").count() == 0


def test_navigation_menu_dismiss_outside(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery probe navigation_menu.dismiss_outside — click outside closes panel."""
    goto_part(page, "navigation-menu")
    scope = page.locator(".hm-preview")
    trigger = "summary.dz-navigation-menu__trigger, summary.navigation-menu__trigger"
    scope.locator(trigger).filter(has_text="Product").first.click()
    page.wait_for_timeout(80)
    assert (
        scope.locator(
            "details.navigation-menu__branch[open], details.dz-navigation-menu__branch[open], "
            ".navigation-menu details[open]"
        ).count()
        >= 1
    )
    page.mouse.click(8, 8)
    page.wait_for_timeout(100)
    open_n = scope.locator(
        "details.navigation-menu__branch[open], details.dz-navigation-menu__branch[open], "
        ".navigation-menu details[open]"
    ).count()
    assert open_n == 0, f"expected dismiss, still open={open_n}"


def test_menu_light_dismiss_esc_and_outside(page) -> None:  # type: ignore[no-untyped-def]
    """Stem overlay-light-dismiss: menu closes on Esc and outside pointer."""
    goto_part(page, "menu")
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.keyboard.press("Escape")
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 0
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.mouse.click(8, 8)
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 0


def test_popover_light_dismiss_esc_and_outside(page) -> None:  # type: ignore[no-untyped-def]
    """Stem overlay-light-dismiss: popover closes on Esc and outside pointer."""
    goto_part(page, "popover")
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.keyboard.press("Escape")
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 0
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    page.mouse.click(8, 8)
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 0


def test_popover_dismiss_none_opts_out(page) -> None:  # type: ignore[no-untyped-def]
    """data-dz-dismiss=none → native toggle only (no Esc / outside).

    Gallery/CDN strip dz- from the controller; set both attr forms so the
    test matches dual-lock source and unprefixed site JS.
    """
    goto_part(page, "popover")
    page.evaluate(
        """() => {
          const d = document.querySelector('.hm-preview details');
          d.setAttribute('data-dz-dismiss', 'none');
          d.setAttribute('data-dismiss', 'none');
        }"""
    )
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.keyboard.press("Escape")
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.mouse.click(8, 8)
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1


def test_popover_temporal_timeout(page) -> None:  # type: ignore[no-untyped-def]
    """data-dz-dismiss-ms arms one timer; closes without polling."""
    goto_part(page, "popover")
    page.evaluate(
        """() => {
          const d = document.querySelector('.hm-preview details');
          d.setAttribute('data-dz-dismiss', 'esc outside');
          d.setAttribute('data-dismiss', 'esc outside');
          d.setAttribute('data-dz-dismiss-ms', '150');
          d.setAttribute('data-dismiss-ms', '150');
        }"""
    )
    page.locator(".hm-preview summary").first.click()
    page.wait_for_timeout(80)
    assert page.locator(".hm-preview details[open]").count() == 1
    page.wait_for_timeout(350)
    assert page.locator(".hm-preview details[open]").count() == 0


def test_command_opener_kbd_is_spatially_secondary(page) -> None:  # type: ignore[no-untyped-def]
    """Stem shortcut-hint-chrome: opener label and ⌘K chip must not be flush (0 gap)."""
    goto_part(page, "command")
    metrics = page.evaluate(
        """() => {
          const btn = document.querySelector('.hm-preview [data-hm-open-command]');
          if (!btn) return null;
          const kbd = btn.querySelector('kbd, .kbd, .dz-kbd');
          if (!kbd) return { err: 'no kbd' };
          const cs = getComputedStyle(btn);
          let textEnd = null;
          const range = document.createRange();
          for (const n of btn.childNodes) {
            if (n.nodeType === 3 && n.textContent && n.textContent.trim()) {
              range.selectNodeContents(n);
              textEnd = range.getBoundingClientRect().right;
            }
          }
          const kr = kbd.getBoundingClientRect();
          return {
            gapCss: cs.gap,
            textEnd,
            kbdLeft: kr.left,
            gapPx: textEnd != null ? kr.left - textEnd : null,
          };
        }"""
    )
    assert metrics is not None and "err" not in metrics, metrics
    # space-sm is typically 8px; allow modest subpixel variance
    assert metrics["gapPx"] is not None and metrics["gapPx"] >= 6, (
        f"adjacent kbd must be spatially secondary (≥~space-sm): {metrics}"
    )


def test_tabs_active_indicator_is_square(page) -> None:  # type: ignore[no-untyped-def]
    """Stem selection-strip-honest: active tab underline must not curve with button radius."""
    goto_part(page, "tabs")
    metrics = page.evaluate(
        """() => {
          const tab = document.querySelector(
            '.hm-preview .tabs__tab[aria-current], .hm-preview .dz-tabs__tab[aria-current]'
          );
          if (!tab) return null;
          const s = getComputedStyle(tab);
          const parse = (v) => parseFloat(v) || 0;
          return {
            tag: tab.tagName,
            bl: parse(s.borderBottomLeftRadius),
            br: parse(s.borderBottomRightRadius),
            tl: parse(s.borderTopLeftRadius),
            tr: parse(s.borderTopRightRadius),
            bbw: parse(s.borderBottomWidth),
            bbc: s.borderBottomColor,
          };
        }"""
    )
    assert metrics is not None, "active tab not found"
    assert metrics["tag"] == "BUTTON"
    assert metrics["bbw"] >= 1, f"expected bottom indicator, got {metrics}"
    # Any non-zero radius curves the bottom border (the human-visible curl)
    assert metrics["bl"] == 0 and metrics["br"] == 0, (
        f"active tab corners must be square so the underline is straight: {metrics}"
    )
    assert metrics["tl"] == 0 and metrics["tr"] == 0, metrics


def test_navigation_menu_disclosure_chevron_scale(page) -> None:  # type: ignore[no-untyped-def]
    """Stem affordance-disclosure-chrome: nav trigger chevron is ~1rem, not Unicode ▾."""
    goto_part(page, "navigation-menu")
    scope = page.locator(".hm-preview")
    # No placeholder Unicode caret spans in the live partial
    assert scope.locator(".navigation-menu__caret, .dz-navigation-menu__caret").count() == 0
    assert "▾" not in (scope.inner_text() or "")
    metrics = page.evaluate(
        """() => {
          const t = document.querySelector(
            '.hm-preview .navigation-menu__trigger, .hm-preview .dz-navigation-menu__trigger'
          );
          if (!t) return null;
          const s = getComputedStyle(t, '::after');
          const parse = (v) => parseFloat(v) || 0;
          return {
            width: parse(s.width),
            height: parse(s.height),
            content: s.content,
            display: s.display,
          };
        }"""
    )
    assert metrics is not None, "trigger not found"
    # 1rem at default 16px root ≈ 16px; allow subpixel / font-size variance
    assert metrics["width"] >= 12, f"chevron width too small: {metrics}"
    assert metrics["height"] >= 12, f"chevron height too small: {metrics}"
    # Open state rotates the same ::after (accordion family)
    scope.locator("summary.navigation-menu__trigger, summary.dz-navigation-menu__trigger").filter(
        has_text="Product"
    ).first.click()
    page.wait_for_timeout(80)
    rot = page.evaluate(
        """() => {
          const t = document.querySelector(
            '.hm-preview details[open] > .navigation-menu__trigger, '
            + '.hm-preview details[open] > .dz-navigation-menu__trigger'
          );
          if (!t) return '';
          return getComputedStyle(t, '::after').transform;
        }"""
    )
    assert rot and rot != "none", f"open trigger should rotate chevron, got {rot!r}"


def test_gallery_preview_hash_links_do_not_scroll(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery presentation: demo <a href="#"> must not jump the host page to top.

    Product markup keeps href=\"#\" (stand-in route). MOCK_HTMX suppresses the
    scroll only inside live demo surfaces so Hyperpart browse is not disrupted.
    """
    goto_part(page, "navigation-menu")
    # Scroll down so a jump-to-top is observable
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(50)
    y_before = page.evaluate("window.scrollY")
    assert y_before >= 200, f"setup: expected scrolled page, got scrollY={y_before}"
    page.locator(
        ".hm-preview a.navigation-menu__link, .hm-preview a.dz-navigation-menu__link"
    ).filter(has_text="Pricing").first.click()
    page.wait_for_timeout(80)
    y_after = page.evaluate("window.scrollY")
    assert y_after >= 200, (
        f"Pricing href=# jumped gallery host (scrollY {y_before} → {y_after}); "
        "inert hash links in .hm-preview must preventDefault"
    )


def test_palette_esc_closes_even_with_query_text(page) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, "command")
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
    goto_part(page, "command")
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
    goto_part(page, "command")
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
    goto_part(page, "command")
    _open_palette(page)
    page.click("[data-hm-close-command]")
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open"), (
        "the close button must close the palette"
    )


def test_palette_arrows_and_enter(page) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, "command")
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
    # Enter activates the inert mock item — close, do not navigate (href=# scroll).
    y_before = page.evaluate("window.scrollY")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open"), (
        "Enter on a mock result must close the palette"
    )
    assert page.evaluate("window.scrollY") == y_before, (
        "activating a mock result must not scroll the host page (no href=# jump)"
    )


def test_palette_click_result_closes_without_scroll(page) -> None:  # type: ignore[no-untyped-def]
    """Gallery mocks are unwired — pick must close, not jump the page to top."""
    goto_part(page, "command")
    # Scroll down so a # navigation would be detectable.
    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(50)
    _open_palette(page)
    page.focus(f"{PALETTE} {INPUT}")
    page.wait_for_timeout(200)
    y_before = page.evaluate("window.scrollY")
    page.locator(f"{PALETTE} .command__item").first.click()
    page.wait_for_timeout(100)
    assert not page.evaluate(f"document.querySelector('{PALETTE}').open")
    assert page.evaluate("window.scrollY") == y_before


def test_confirm_dialog_intercepts_hx_confirm(page) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, "confirm")
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
    goto_part(page, "grid")
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
    # EVERY count mirror updates — the footer's "N of M selected" too
    # (querySelector-first once left it stuck at 0; C1.1 review catch).
    assert (
        page.eval_on_selector(
            "[data-grid-pagination] [data-bulk-count-target]", "e => e.textContent.trim()"
        )
        == "1"
    )
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    # The URL must follow the clamp too (page 1 = default → no page param): the
    # address bar mirrors the request query EXACTLY, even when the SERVER moved
    # the page out from under the client.
    assert "page" not in _url_params(page), (
        f"a server clamp must not leave a stale page= in the URL: {_url_params(page)}"
    )


def test_grid_bulk_payload_keys_win_over_query_echo(page) -> None:  # type: ignore[no-untyped-def]
    """A query param that collides with a bulk-payload key (e.g. a filter named
    'action') must NOT clobber the operation — the payload keys are written last
    so they always win."""
    goto_part(page, "grid")
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
    # The summary is the selected/rows PAIR — read the row-window half (the
    # visible one while nothing is selected).
    return page.eval_on_selector(
        "[data-grid-pagination] .bulk-summary-rows", "e => e.textContent.trim()"
    )


def test_grid_paginates_and_navigates(page) -> None:  # type: ignore[no-untyped-def]
    """The server-rendered footer pages the result set (page_size 4 of 6): prev
    is disabled on page 1, next on the last page, and prev / next / a page number
    each reload the tbody for that page."""
    goto_part(page, "grid")
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
    goto_part(page, "grid")
    page.click("[data-grid-sort='first']")  # ascending
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Amir", "Jane", "Mia", "Noah"], "sorted page 1"
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Ravi", "Sofia"], "sorted page 2 continues the order"


def test_grid_change_resets_to_page_one(page) -> None:  # type: ignore[no-untyped-def]
    """A sort / filter / search change resets the page to 1 (spec) — you never
    land on page 2 of a freshly-narrowed result."""
    goto_part(page, "grid")
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


def _enter_all_matching(page) -> None:  # type: ignore[no-untyped-def]
    """Select the visible page, then escalate to all-matching selection."""
    page.check("[data-grid-select-all]")
    page.wait_for_timeout(80)
    page.click("[data-grid-select-all-matching]", timeout=3000)
    page.wait_for_timeout(80)


def test_grid_select_all_matching_spans_pages(page) -> None:  # type: ignore[no-untyped-def]
    """'Select all matching' escalates a page selection to the WHOLE matched
    query (all pages): state lands on the root (data-grid-all-matching), the
    count shows the matched total (from the footer's data-grid-total, not the
    visible boxes), and rows on other pages arrive selected."""
    goto_part(page, "grid")
    page.check("[data-grid-select-all]")
    page.wait_for_timeout(80)
    # the affordance announces the matched total, fed from the server-rendered footer
    assert page.inner_text("[data-grid-matching-total]", timeout=3000).strip() == "6"

    page.click("[data-grid-select-all-matching]", timeout=3000)
    page.wait_for_timeout(80)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") == "true"
    assert page.inner_text("[data-bulk-count-target]").strip() == "6", (
        "the count is the matched TOTAL (6), not the 4 visible boxes"
    )
    # the escalation affordance hides while all-matching is active (it's done its job)
    assert (
        page.eval_on_selector("[data-grid-select-all-matching]", "e => getComputedStyle(e).display")
        == "none"
    )

    # page 2's freshly-rendered rows arrive SELECTED (all-matching spans pages)
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert page.eval_on_selector_all("[data-grid-select]", "els => els.every(b => b.checked)"), (
        "rows on a newly-loaded page must arrive checked in all-matching mode"
    )
    assert page.inner_text("[data-bulk-count-target]").strip() == "6"


def test_grid_all_matching_exclusion_persists_across_pages(page) -> None:  # type: ignore[no-untyped-def]
    """Unchecking a row in all-matching mode records an EXCLUSION on the root —
    it survives paging away and back (state on the root, not the row DOM)."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.locator("[data-grid-select]").nth(1).uncheck()  # Ravi (cust_2)
    page.wait_for_timeout(80)
    assert page.inner_text("[data-bulk-count-target]").strip() == "5", "6 matched − 1 excluded"
    assert "cust_2" in (page.get_attribute("[data-grid]", "data-grid-excluded") or "")
    assert page.eval_on_selector("[data-grid-select-all]", "e => e.indeterminate"), (
        "the header box shows the partial state while an exclusion exists"
    )

    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    page.click("[data-grid-page-prev]")
    page.wait_for_timeout(150)
    state = page.eval_on_selector_all(
        "[data-grid-select]",
        "els => els.map(b => [b.getAttribute('data-grid-row-id'), b.checked])",
    )
    assert dict(state).get("cust_2") is False, f"the exclusion survives the round-trip: {state}"
    assert sum(1 for _, c in state if c) == 3, f"the other page-1 rows stay selected: {state}"


def test_grid_all_matching_bulk_delete_applies_query_minus_exclusions(page) -> None:  # type: ignore[no-untyped-def]
    """A bulk action in all-matching mode sends all_matching_selected=true +
    excluded_ids + the query echo — the server applies it to the whole matched
    set MINUS the exclusions (never just the visible ids)."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.locator("[data-grid-select]").first.uncheck()  # Mia (cust_1) is spared
    page.wait_for_timeout(80)
    _bulk_confirm_delete(page)

    payload = page.evaluate("window.__lastBulk")
    assert payload["all_matching_selected"] == "true"
    assert payload["excluded_ids"] == ["cust_1"]
    names = _grid_names(page)
    assert names == ["Mia"], f"every matched row deletes EXCEPT the excluded one: {names}"
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") is None, (
        "the action consumes the all-matching selection"
    )
    assert page.get_attribute("[data-grid]", "data-bulk-count") == "0"


def test_grid_all_matching_drops_on_query_change(page) -> None:  # type: ignore[no-untyped-def]
    """A filter/search change CHANGES the matched set, so all-matching mode must
    drop (the user never confirmed 'all matching' over the new query) — falling
    back to plain per-row selection."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") is None, (
        "a filter change must drop all-matching (the matched set changed)"
    )
    assert page.get_attribute("[data-grid]", "data-grid-excluded") is None
    assert page.inner_text("[data-grid-matching-total]").strip() == "2", (
        "the matched-total mirror follows the narrowed query (Pro → 2)"
    )


def test_grid_all_matching_survives_net_unchanged_search(page) -> None:  # type: ignore[no-untyped-def]
    """A keystroke that is immediately deleted leaves the matched set UNCHANGED
    — the debounced search must not silently drop a cross-page all-matching
    selection for it (the classic silent-selection-loss before a bulk delete)."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.type("[data-grid-search]", "x")
    page.wait_for_timeout(50)  # inside the 250ms debounce window
    page.press("[data-grid-search]", "Backspace")
    page.wait_for_timeout(500)  # let the coalesced timer fire + rows reload
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") == "true", (
        "a net-unchanged search must keep the all-matching selection"
    )
    assert page.inner_text("[data-bulk-count-target]").strip() == "6"

    # …but a search that actually CHANGES the matched set still drops it.
    page.fill("[data-grid-search]", "pro")
    page.wait_for_timeout(500)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") is None, (
        "a real search change must still drop all-matching"
    )


def test_grid_all_matching_exclusion_survives_resort(page) -> None:  # type: ignore[no-untyped-def]
    """Pin for the afterSwap re-projection: after a re-sort (rows re-rendered,
    order changed, mode kept), an excluded row stays unchecked and the others
    stay checked — the root's state re-projects onto whatever rows render."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.locator("[data-grid-select]").first.uncheck()  # Mia (cust_1)
    page.wait_for_timeout(80)
    page.click("[data-grid-sort='first']")  # ascending: Amir, Jane, Mia, Noah
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") == "true", (
        "a sort re-orders the SAME matched set — the mode survives"
    )
    state = page.eval_on_selector_all(
        "[data-grid-select]",
        "els => els.map(b => [b.getAttribute('data-grid-row-id'), b.checked])",
    )
    assert dict(state).get("cust_1") is False, f"the exclusion re-projects after a sort: {state}"
    assert sum(1 for _, c in state if c) == 3, f"non-excluded rows re-project checked: {state}"
    assert page.inner_text("[data-bulk-count-target]").strip() == "5"


def test_grid_select_all_header_uncheck_exits_all_matching(page) -> None:  # type: ignore[no-untyped-def]
    """Unchecking the header select-all while in all-matching mode deselects
    EVERYTHING — mode, exclusions, and boxes."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.uncheck("[data-grid-select-all]")
    page.wait_for_timeout(80)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") is None
    assert page.get_attribute("[data-grid]", "data-grid-excluded") is None
    assert page.get_attribute("[data-grid]", "data-bulk-count") == "0"


def test_grid_page_size_rewindows_and_resets_to_page_one(page) -> None:  # type: ignore[no-untyped-def]
    """The page-size select re-WINDOWS the matched set: the server repages for
    the new size (rows + footer from one query), and any size change lands back
    on page 1 — you never keep a page number that no longer exists."""
    goto_part(page, "grid")
    assert _grid_names(page) == ["Mia", "Ravi", "Amir", "Sofia"], "default 4/page"

    page.select_option("[data-grid-page-size]", "8", timeout=3000)
    page.wait_for_timeout(150)
    assert len(_grid_names(page)) == 6, "8/page shows all 6 rows on one page"
    assert _page_summary(page) == "1-6 of 6"
    assert page.eval_on_selector("[data-grid-page-next]", "b => b.disabled") is True

    page.select_option("[data-grid-page-size]", "2")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Mia", "Ravi"], "2/page windows to the first pair"
    assert _page_summary(page) == "1-2 of 6"
    page.click("[data-grid-goto='3']")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Noah", "Jane"], "page 3 of the 2/page windows"

    page.select_option("[data-grid-page-size]", "4")
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-page") == "1", (
        "a size change resets to page 1"
    )
    assert _grid_names(page) == ["Mia", "Ravi", "Amir", "Sofia"]


def test_grid_page_size_keeps_all_matching(page) -> None:  # type: ignore[no-untyped-def]
    """Page size WINDOWS the same matched set (like a page click) — it must NOT
    drop an all-matching selection OR its exclusions the way a filter/search
    scope change does."""
    goto_part(page, "grid")
    _enter_all_matching(page)
    page.locator("[data-grid-select]").first.uncheck()  # exclude Mia (cust_1)
    page.wait_for_timeout(80)
    page.select_option("[data-grid-page-size]", "2", timeout=3000)
    page.wait_for_timeout(150)
    assert page.get_attribute("[data-grid]", "data-grid-all-matching") == "true", (
        "a page-size change re-windows the SAME matched set — the mode survives"
    )
    assert "cust_1" in (page.get_attribute("[data-grid]", "data-grid-excluded") or ""), (
        "the exclusion survives the re-window too"
    )
    assert page.inner_text("[data-bulk-count-target]").strip() == "5", "6 matched − 1 excluded"
    state = page.eval_on_selector_all(
        "[data-grid-select]",
        "els => els.map(b => [b.getAttribute('data-grid-row-id'), b.checked])",
    )
    assert dict(state).get("cust_1") is False, f"the excluded row re-projects unchecked: {state}"
    assert all(c for rid, c in state if rid != "cust_1"), (
        f"the other re-windowed rows arrive selected (afterSwap re-projection): {state}"
    )


def _url_params(page):  # type: ignore[no-untyped-def]
    return page.evaluate("() => Object.fromEntries(new URLSearchParams(location.search).entries())")


def test_grid_url_syncs_state_to_the_address_bar(page) -> None:  # type: ignore[no-untyped-def]
    """With [data-grid-url] on the root, every state change lands in the URL as
    human-readable params (spec §7) — the URL mirrors the request query EXACTLY
    (page_size included: the select always rides the query), so a deep link
    reproduces the request byte-for-byte."""
    goto_part(page, "grid")
    ps = {"page_size": "4"}  # the demo's Per-page select rides every query
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(150)
    assert _url_params(page) == {"sort": "first", "dir": "asc", **ps}

    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(150)
    assert _url_params(page) == {"sort": "first", "dir": "asc", "plan": "Pro", **ps}

    page.select_option("[data-grid-filter='plan']", "")
    page.wait_for_timeout(150)
    page.click("[data-grid-page-next]")
    page.wait_for_timeout(150)
    assert _url_params(page) == {"sort": "first", "dir": "asc", "page": "2", **ps}

    page.fill("[data-grid-search]", "ch")
    page.wait_for_timeout(400)
    p = _url_params(page)
    assert p.get("q") == "ch" and "page" not in p, (
        f"search lands in the URL (and the page-1 reset drops page=): {p}"
    )


def test_grid_url_restores_state_on_load(page) -> None:  # type: ignore[no-untyped-def]
    """Deep link: loading the page WITH grid params applies them — controls
    reflect the state, and the hydration fetch uses the restored query (no
    default-then-correct double fetch)."""
    # Part page, not index — index embeds many sections; bulk-summary text
    # can collide ("42 rows" from another demo) and mask the grid footer.
    page.goto(part_uri("grid") + "?plan=Pro&sort=first&dir=asc")
    page.wait_for_timeout(300)
    assert _grid_names(page) == ["Amir", "Noah"], "rows arrive already narrowed + sorted"
    assert page.eval_on_selector("[data-grid-filter='plan']", "e => e.value") == "Pro"
    assert _aria_sort(page, "first") == "ascending"
    assert _page_summary(page) == "1-2 of 2"


def test_grid_url_back_button_restores_previous_state(page) -> None:  # type: ignore[no-untyped-def]
    """Discrete state changes push history entries, so Back returns to the
    previous grid state — controls, rows, and URL all restore (popstate)."""
    goto_part(page, "grid")
    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Amir", "Noah"]

    page.select_option("[data-grid-filter='plan']", "Free")
    page.wait_for_timeout(150)
    assert _grid_names(page) == ["Sofia", "Jane"]

    page.go_back()
    page.wait_for_timeout(200)
    assert _url_params(page).get("plan") == "Pro"
    assert page.eval_on_selector("[data-grid-filter='plan']", "e => e.value") == "Pro"
    assert _grid_names(page) == ["Amir", "Noah"], "Back restores the previous matched rows"


def test_grid_url_unresolvable_params_do_not_loop(page) -> None:  # type: ignore[no-untyped-def]
    """A deep link whose grid params the DOM cannot express (a renamed sort
    column in a stale bookmark, an out-of-range page_size) must DEGRADE, not
    LOOP: the after-settle re-sync only re-dispatches when the restore
    actually changed the query — else an un-satisfiable URL param re-fetches
    forever (GET storm under real htmx; stack overflow under the synchronous
    gallery mock)."""
    goto_part(page, "grid")
    page.goto(part_uri("grid") + "?sort=renamed_column&dir=asc&page_size=999")
    page.wait_for_timeout(800)
    # The grid still hydrates and works (graceful degradation)…
    assert page.eval_on_selector_all("[data-grid-body] tr td", "tds => tds.length > 0"), (
        "the grid must still hydrate under unresolvable params"
    )
    # …and no error escaped (the page fixture also asserts pageerrors on
    # teardown — a re-sync loop would blow the stack synchronously here).
    page.click("[data-grid-sort='first']")
    page.wait_for_timeout(400)
    assert (
        page.eval_on_selector(
            "[data-grid-sort='first']", "b => b.closest('th').getAttribute('aria-sort')"
        )
        == "ascending"
    ), "the grid stays interactive after the degraded deep link"


def test_grid_url_preserves_unrelated_params(page) -> None:  # type: ignore[no-untyped-def]
    """The grid only owns its OWN keys (q/sort/dir/page/page_size + its filter
    fields) — a foreign query param on the page URL survives grid activity."""
    page.goto(part_uri("grid") + "?foo=bar")
    page.wait_for_timeout(300)
    page.click("[data-grid-sort='plan']")
    page.wait_for_timeout(150)
    p = _url_params(page)
    assert p.get("foo") == "bar", f"foreign params must survive: {p}"
    assert p.get("sort") == "plan"


def test_grid_announces_result_window_changes(page) -> None:  # type: ignore[no-untyped-def]
    """The footer is server-repainted wholesale, so screen readers can't track
    it — the controller mirrors the result-window summary into a visually-hidden
    polite live region on every data change."""
    goto_part(page, "grid")
    announce = "[data-grid-announce]"
    assert page.inner_text(announce, timeout=3000).strip() == "Showing 1-4 of 6", (
        "hydration announces the initial window"
    )
    assert page.get_attribute(announce, "aria-live") == "polite"
    assert page.eval_on_selector(
        announce,
        "e => { const r = e.getBoundingClientRect(); return r.width <= 1 && r.height <= 1; }",
    ), "the announcer must be visually hidden (SR-only box)"

    page.select_option("[data-grid-filter='plan']", "Pro")
    page.wait_for_timeout(150)
    assert page.inner_text(announce).strip() == "Showing 1-2 of 2", (
        "a filter change announces the narrowed window"
    )

    page.fill("[data-grid-search]", "zzz")
    page.wait_for_timeout(400)
    assert page.inner_text(announce).strip() == "Showing 0 of 0", (
        "an empty result announces too (the SR user hears the dead end)"
    )


def test_grid_pagination_restores_keyboard_focus(page) -> None:  # type: ignore[no-untyped-def]
    """Every page change repaints the footer wholesale — without restoration,
    the keyboard user's focus silently falls to <body> and they lose their
    place. Focus must land on the repainted equivalent control (or the
    current-page button when the equivalent is now disabled)."""
    goto_part(page, "grid")
    page.click("[data-grid-goto='2']")
    page.wait_for_timeout(150)
    focused = page.evaluate(
        "() => { const a = document.activeElement;"
        " return a ? (a.getAttribute('data-grid-goto') || a.tagName) : null; }"
    )
    assert focused == "2", f"focus must land on the repainted goto control: {focused}"

    # prev back to page 1: the repainted prev is DISABLED there, so focus falls
    # through to the current-page button instead of vanishing to <body>.
    page.click("[data-grid-page-prev]")
    page.wait_for_timeout(150)
    focused = page.evaluate(
        "() => { const a = document.activeElement;"
        " return a ? (a.getAttribute('data-grid-goto') || a.tagName) : null; }"
    )
    assert focused == "1", f"disabled-equivalent falls back to the current page: {focused}"


def test_grid_search_debounce_coalesces_keystrokes(page) -> None:  # type: ignore[no-untyped-def]
    """A burst of keystrokes makes exactly ONE request, not one per key. Counts
    the `dz-grid:refresh` events (un-prefixed `grid:refresh` in the gallery). A
    long debounce makes the timing robust: during the burst nothing fires; one
    request lands after it settles."""
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    goto_part(page, "grid")
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
    # Code Hyperpart owns the copy chrome (data-code-copy) — not gallery
    # hm-copy, which the index no longer ships on every section.
    page.goto(part_uri("code"))
    page.wait_for_timeout(200)
    btn = page.locator("[data-code-copy]").first
    assert btn.count() == 1, "code part page must ship a copy control"
    btn.click()
    page.wait_for_timeout(150)
    assert btn.get_attribute("data-copied") is not None, (
        "copy click must flip the button into its Copied state"
    )
    try:
        clip = page.evaluate("navigator.clipboard.readText()")
        assert len(clip.strip()) > 0, "clipboard should hold the snippet text"
    except Exception:  # noqa: BLE001 — clipboard read unsupported on this engine
        pass
    # feedback reverts, and no stuck focus/hover state remains
    page.wait_for_timeout(1800)
    assert btn.get_attribute("data-copied") is None, "Copied state must revert"
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
    goto_part(page, "dialog")
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
    goto_part(page, "dialog")
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
    goto_part(page, "tabs")
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


def test_carousel_prev_next_and_dots_change_active_slide(page) -> None:  # type: ignore[no-untyped-def]
    """dz-carousel.js: next/prev/dots move data-active and aria-current.

    The gallery used to ship inert prev/next (controller deferred) — no
    visible state change on click. Demo must exercise the behaviour.
    """
    goto_part(page, "carousel")
    root = page.locator("#carousel [data-carousel], #carousel .carousel").first
    assert root.count() == 1
    slides = root.locator(".carousel__slide")
    assert slides.count() == 3

    def active_text() -> str:
        return page.evaluate(
            """() => {
              const r = document.querySelector('#carousel [data-carousel], #carousel .carousel');
              const a = r && r.querySelector('.carousel__slide[data-active]');
              return a ? a.textContent.trim() : '';
            }"""
        )

    def index_attr() -> str | None:
        return root.get_attribute("data-carousel-index")

    assert "Slide 1" in active_text()
    assert index_attr() in (None, "0")
    prev = root.locator("[data-carousel-prev]")
    next_btn = root.locator("[data-carousel-next]")
    assert prev.is_disabled()
    assert not next_btn.is_disabled()

    next_btn.click()
    page.wait_for_timeout(100)
    assert "Slide 2" in active_text(), f"next should show slide 2, got {active_text()!r}"
    assert index_attr() == "1"
    assert not prev.is_disabled()
    dots = root.locator(".carousel__dot")
    assert dots.nth(1).get_attribute("aria-current") == "true"
    assert dots.nth(0).get_attribute("aria-current") is None

    dots.nth(2).click()
    page.wait_for_timeout(100)
    assert "Slide 3" in active_text()
    assert index_attr() == "2"
    assert next_btn.is_disabled()
    assert dots.nth(2).get_attribute("aria-current") == "true"

    prev.click()
    page.wait_for_timeout(100)
    assert "Slide 2" in active_text()
    assert index_attr() == "1"
    assert not next_btn.is_disabled()


def test_slider_updates_value_readout(page) -> None:  # type: ignore[no-untyped-def]
    """dz-slider.js writes the range value into the group's [data-range-value]
    readout on input, scoped to the slider's own group."""
    goto_part(page, "slider")
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
    goto_part(page, "slider")
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
    goto_part(page, "drawer")
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


def test_drawer_open_does_not_focus_header_chrome(page) -> None:  # type: ignore[no-untyped-def]
    """Pointer open must not leave focus on header chrome controls.

    showModal focuses the first focusable. WebKit paints that as
    :focus-visible, so the control looks "active" until click-away.
    UA may assign that focus *after* showModal returns — settle must
    re-run (rAF/timeout), not only when active is .drawer__close.
    Gate both demos at t≈0 and after a delayed re-check.
    """
    goto_part(page, "drawer")

    def _focus_info(dlg_id: str) -> dict:
        return page.evaluate(
            """(id) => {
              const dlg = document.getElementById(id);
              const active = document.activeElement;
              const close = dlg && dlg.querySelector('.drawer__close');
              const expand = dlg && (
                dlg.querySelector('[data-drawer-expand]') ||
                dlg.querySelector('[data-dz-drawer-expand]') ||
                dlg.querySelector('[data-drawer-widen]') ||
                dlg.querySelector('[data-dz-drawer-widen]')
              );
              const header = dlg && dlg.querySelector('.drawer__header');
              const body = dlg && dlg.querySelector('.drawer__body');
              const inHeader = !!(
                header && active && header.contains(active) && active !== dlg
              );
              return {
                open: !!(dlg && dlg.open),
                activeIsClose: active === close,
                activeIsExpand: active === expand,
                activeInHeaderChrome: inHeader,
                activeIsBody: active === body,
                activeIsShell: active === dlg,
                activeIsInside: !!(dlg && active && dlg.contains(active)),
                closeFocusVisible: !!(close && close.matches(':focus-visible')),
                expandFocusVisible: !!(expand && expand.matches(':focus-visible')),
                activeClass: active ? active.className : '',
                activeTag: active ? active.tagName : '',
              };
            }""",
            dlg_id,
        )

    for dlg_id, open_sel in (
        ("hm-drawer-demo", '[data-dialog-open="hm-drawer-demo"]'),
        ("hm-drawer-lazy", '[data-dialog-open="hm-drawer-lazy"]'),
    ):
        page.click(open_sel)
        # Immediate + delayed: catches the post-showModal focus race
        for wait_ms in (80, 200):
            page.wait_for_timeout(wait_ms if wait_ms == 80 else 120)
            info = _focus_info(dlg_id)
            assert info["open"], f"{dlg_id} must be open (@{wait_ms}ms)"
            assert info["activeIsInside"], (
                f"{dlg_id}: focus must remain inside the dialog (@{wait_ms}ms)"
            )
            assert not info["activeIsClose"], (
                f"{dlg_id}: close must not hold focus after pointer open "
                f"(@{wait_ms}ms active={info['activeTag']}.{info['activeClass']})"
            )
            assert not info["activeIsExpand"], (
                f"{dlg_id}: Expand must not hold focus after pointer open "
                f"(@{wait_ms}ms active={info['activeTag']}.{info['activeClass']})"
            )
            assert not info["activeInHeaderChrome"], (
                f"{dlg_id}: no header chrome control should hold focus "
                f"(@{wait_ms}ms active={info['activeTag']}.{info['activeClass']})"
            )
            assert not info["closeFocusVisible"], (
                f"{dlg_id}: close must not be :focus-visible (@{wait_ms}ms)"
            )
            assert not info["expandFocusVisible"], (
                f"{dlg_id}: Expand must not be :focus-visible (@{wait_ms}ms)"
            )
        # Esc still works with body/shell focus
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert page.get_attribute(f"#{dlg_id}", "open") is None, f"{dlg_id} Esc close"


def test_master_detail_selection_and_instance_isolation(page) -> None:  # type: ignore[no-untyped-def]
    """The master-detail composite: clicking a list item selects it (aria-current
    moves) AND the controller is instance-isolated — a second master-detail on
    the page manages its own selection without touching the first."""
    goto_part(page, "master-detail")
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


# === Grid extensions (promoted from Dazzle, 0.1.26): col-vis / resize / edit ===


def _hydrate_grid(page):  # type: ignore[no-untyped-def]
    """Wait for the grid tbody to hold real (non-skeleton) rows."""
    page.wait_for_selector("[data-grid-body] tr[id]", timeout=3000)


def test_grid_column_resize_drags_col_width_and_persists(page) -> None:  # type: ignore[no-untyped-def]
    """grid-resize extension: a pointer drag on a header handle widens the
    column's <col> (snap-8, live), and the width survives a reload
    (localStorage). The handle lives INSIDE the th (never clipped by the
    scroll container) and a drag must not fire the header's sort."""
    goto_part(page, "grid")
    _hydrate_grid(page)
    handle = page.query_selector('[data-grid-resize="first"]')
    assert handle is not None, "the First-name header must carry a resize handle"
    # raw mouse events use viewport coords — the grid sits below the fold
    handle.scroll_into_view_if_needed()
    page.wait_for_timeout(50)
    col = '[data-grid] col[data-col="first"]'
    start = page.eval_on_selector(col, "c => c.offsetWidth || c.getBoundingClientRect().width")
    if not start:  # engines where col boxes don't report: baseline from the th
        start = page.eval_on_selector(
            '[data-grid-resize="first"]',
            "h => Math.round(h.closest('th').getBoundingClientRect().width)",
        )
    box = handle.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    sort_before = page.get_attribute('[data-grid-resize="first"]', "data-grid-resize")
    assert sort_before == "first"
    aria_before = page.eval_on_selector(
        '[data-grid-resize="first"]', "h => h.closest('th').getAttribute('aria-sort')"
    )
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 64, y, steps=4)
    page.mouse.up()
    page.wait_for_timeout(80)
    width = page.eval_on_selector(col, "c => parseInt(c.style.width, 10) || 0")
    assert abs(width - (start + 64)) <= 16, (
        f"drag +64 from {start} must land within a snap step: got {width}"
    )
    # the drag must NOT have cycled the sort
    aria_after = page.eval_on_selector(
        '[data-grid-resize="first"]', "h => h.closest('th').getAttribute('aria-sort')"
    )
    assert aria_after == aria_before, "a resize drag must not trigger the header sort"
    # persistence: reload → the stored width re-applies to the fresh <col>
    page.reload()
    page.wait_for_timeout(300)
    _hydrate_grid(page)
    width2 = page.eval_on_selector(col, "c => parseInt(c.style.width, 10) || 0")
    assert width2 == width, "the column width must persist across a reload"


def test_grid_column_visibility_menu_toggles_and_persists(page) -> None:  # type: ignore[no-untyped-def]
    """grid-cols extension: unchecking a column in the native <details> menu
    hides every cell of that column (header + hydrated data cells + its <col>),
    the preference persists across a reload, and re-checking restores it."""
    goto_part(page, "grid")
    _hydrate_grid(page)
    toggle = '[data-grid-col-toggle="plan"]'
    assert page.query_selector(toggle) is not None, "the grid must render a column menu"
    plan_cells = '[data-grid] [data-col="plan"]'
    n = page.eval_on_selector_all(plan_cells, "els => els.length")
    assert n >= 2, "th + hydrated tds must carry the column key"
    visible = "els => els.filter(e => getComputedStyle(e).display !== 'none').length"

    page.eval_on_selector(
        toggle, "t => { t.checked = false; t.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    page.wait_for_timeout(80)
    assert page.eval_on_selector_all(plan_cells, visible) == 0, "every plan cell must hide"

    # hydrated rows arriving AFTER the toggle stay hidden (after-swap re-apply)
    page.eval_on_selector(
        "[data-grid-body]",
        "b => b.dispatchEvent(new CustomEvent('grid:refresh', {bubbles: true}))",
    )
    page.wait_for_timeout(120)
    assert page.eval_on_selector_all(plan_cells, visible) == 0, (
        "re-fetched rows must re-hide the column"
    )

    # persists across reload
    page.reload()
    page.wait_for_timeout(300)
    _hydrate_grid(page)
    assert page.eval_on_selector_all(plan_cells, visible) == 0
    assert page.eval_on_selector(toggle, "t => t.checked") is False

    # restore
    page.eval_on_selector(
        toggle, "t => { t.checked = true; t.dispatchEvent(new Event('change', {bubbles: true})); }"
    )
    page.wait_for_timeout(80)
    assert page.eval_on_selector_all(plan_cells, visible) >= n - 1


def test_grid_inline_edit_commits_via_put_and_refreshes(page) -> None:  # type: ignore[no-untyped-def]
    """grid-edit extension: dblclick an editable cell's display span opens an
    in-cell editor; Enter commits a single-field PUT to the grid's edit URL
    (the entity's standard update route); on success the controller refreshes
    the rows and the server-rendered cell shows the new value. Escape cancels
    without a request."""
    goto_part(page, "grid")
    _hydrate_grid(page)
    span = page.query_selector('[data-grid-body] [data-grid-edit="first"]')
    assert span is not None, "hydrated editable cells must carry the edit seam span"

    # Escape cancels: no editor left behind, value unchanged
    span.dblclick()
    page.wait_for_timeout(80)
    editor = page.query_selector("[data-grid-editor]")
    assert editor is not None, "dblclick must open the in-cell editor"
    page.keyboard.press("Escape")
    page.wait_for_timeout(80)
    assert page.query_selector("[data-grid-editor]") is None

    # Enter commits: PUT applied to the mock data, refresh renders it
    span = page.query_selector('[data-grid-body] [data-grid-edit="first"]')
    span.dblclick()
    page.wait_for_timeout(80)
    page.fill("[data-grid-editor]", "Renamed")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    assert page.query_selector("[data-grid-editor]") is None, "commit must close the editor"
    names = page.eval_on_selector_all(
        '[data-grid-body] [data-grid-edit="first"]',
        "els => els.map(e => e.textContent.trim())",
    )
    assert "Renamed" in names, f"the committed value must render from the server: {names}"


def test_grid_touch_resize_and_edit_accommodations(_engine_browser) -> None:  # type: ignore[no-untyped-def]
    """Touch (coarse pointer) accommodations for the grid extensions,
    chromium-only (WebKit has no mobile/pointer:coarse emulation):
    - the resize handle widens to a 24px strip and its hairline is visible
      WITHOUT hover (touch has no hover);
    - a touch-pointer drag resizes the column (touch-action:none keeps the
      gesture out of scroll panning; this synthetic-event test pins the
      controller contract — gesture arbitration itself needs a real device);
    - editable cells carry touch-action:manipulation so a double-tap opens
      the editor instead of zooming."""
    if _engine_browser.browser_type.name != "chromium":
        pytest.skip("pointer:coarse emulation (is_mobile) is chromium-only")
    ctx = _engine_browser.new_context(
        viewport={"width": 834, "height": 1112},  # iPad Pro 11" portrait
        is_mobile=True,
        has_touch=True,
    )
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(_SITE_URI)
    page.wait_for_selector("[data-grid-body] tr[id]", timeout=3000)

    # coarse-pointer CSS actually applied (guards the emulation itself)
    assert page.evaluate("matchMedia('(pointer: coarse)').matches"), (
        "mobile emulation must flip pointer:coarse for this test to mean anything"
    )
    handle = '[data-grid-resize="first"]'
    assert page.eval_on_selector(handle, "h => getComputedStyle(h).width") == "24px"
    hairline = page.eval_on_selector(handle, "h => getComputedStyle(h, '::after').backgroundColor")
    assert hairline not in ("rgba(0, 0, 0, 0)", "transparent"), (
        "the resize hairline must be visible without hover on touch"
    )
    assert (
        page.eval_on_selector(
            '[data-grid-body] [data-grid-edit="first"]',
            "s => getComputedStyle(s).touchAction",
        )
        == "manipulation"
    )

    # synthetic touch-pointer drag → the controller resizes the col
    width = page.evaluate(
        """() => new Promise((resolve) => {
          const h = document.querySelector('[data-grid-resize="first"]');
          const r = h.getBoundingClientRect();
          const x = r.x + r.width / 2, y = r.y + r.height / 2;
          const ev = (type, cx) => new PointerEvent(type, {
            bubbles: true, pointerType: 'touch', isPrimary: true,
            clientX: cx, clientY: y,
          });
          h.dispatchEvent(ev('pointerdown', x));
          window.dispatchEvent(ev('pointermove', x + 64));
          window.dispatchEvent(ev('pointerup', x + 64));
          const col = document.querySelector('[data-grid] col[data-col="first"]');
          resolve(parseInt(col.style.width, 10) || 0);
        })"""
    )
    assert width > 0, "a touch-pointer drag must resize the column"
    assert not errors, f"gallery page threw JS errors: {errors}"
    ctx.close()


def test_grid_column_visibility_reset_shows_all_and_clears(page) -> None:  # type: ignore[no-untyped-def]
    """grid-cols #853 escape hatch: after hiding columns, the menu's
    "Show all columns" button reveals every cell and CLEARS the stored
    preference (a reload stays all-visible)."""
    goto_part(page, "grid")
    _hydrate_grid(page)
    visible = "els => els.filter(e => getComputedStyle(e).display !== 'none').length"
    for key in ("plan", "signed"):
        page.eval_on_selector(
            f'[data-grid-col-toggle="{key}"]',
            "t => { t.checked = false; t.dispatchEvent(new Event('change', {bubbles: true})); }",
        )
    page.wait_for_timeout(80)
    assert page.eval_on_selector_all('[data-grid] [data-col="plan"]', visible) == 0

    reset = page.query_selector("[data-grid-cols-reset]")
    assert reset is not None, "the column menu must carry the Show-all reset"
    page.eval_on_selector("[data-grid-cols-reset]", "b => b.click()")
    page.wait_for_timeout(80)
    n_plan = page.eval_on_selector_all('[data-grid] [data-col="plan"]', visible)
    n_signed = page.eval_on_selector_all('[data-grid] [data-col="signed"]', visible)
    assert n_plan > 0 and n_signed > 0, "reset must reveal every hidden column"
    assert page.eval_on_selector('[data-grid-col-toggle="plan"]', "t => t.checked")

    # cleared, not just re-shown: a reload stays all-visible
    page.reload()
    page.wait_for_timeout(300)
    _hydrate_grid(page)
    assert page.eval_on_selector_all('[data-grid] [data-col="plan"]', visible) > 0


# ── confirm-panel gate (dz-confirm-gate.js) ─────────────────────────


def test_confirm_gate_arms_primary_only_when_required_boxes_checked(page) -> None:  # type: ignore[no-untyped-def]
    """The consent gate is state-in-DOM: the primary anchor ships
    aria-disabled with its destination parked in data-confirm-href.
    Checking ALL required boxes (and only required ones — the optional
    box must not count) promotes the href and drops aria-disabled;
    unchecking re-disarms."""
    goto_part(page, "confirm-panel")
    root = "#confirm-panel [data-confirm-gate]"
    primary = f"{root} .confirm-primary"

    assert page.get_attribute(primary, "aria-disabled") == "true"
    assert page.get_attribute(primary, "href") is None

    # The optional box alone must NOT arm the gate.
    page.check(f"{root} li[data-required='false'] input[type=checkbox]")
    assert page.get_attribute(primary, "aria-disabled") == "true"

    required = page.query_selector_all(f"{root} input[data-required='true']")
    assert len(required) == 2, "demo carries two required boxes"
    required[0].check()
    assert page.get_attribute(primary, "aria-disabled") == "true", (
        "one of two required boxes must not arm the gate"
    )
    required[1].check()
    assert page.get_attribute(primary, "aria-disabled") is None
    assert page.get_attribute(primary, "href") == "#go-live"

    # Unchecking a required box re-disarms (recount, not a +/- counter).
    required[0].uncheck()
    assert page.get_attribute(primary, "aria-disabled") == "true"
    assert page.get_attribute(primary, "href") is None


def test_confirm_gate_never_promotes_a_dangerous_scheme_href(page) -> None:  # type: ignore[no-untyped-def]
    """The gate promotes the parked destination into the live ``href`` when
    armed — but a hostile scheme (``javascript:``/``data:``) must never reach
    the DOM sink. Even with such a URL parked in ``data-confirm-href``, arming
    the gate leaves the anchor without that href (no DOM-XSS via click)."""
    goto_part(page, "confirm-panel")
    root = "#confirm-panel [data-confirm-gate]"
    primary = f"{root} .confirm-primary"

    # Park a hostile scheme where the safe destination normally sits.
    page.eval_on_selector(
        primary,
        "el => el.setAttribute('data-confirm-href', 'javascript:alert(1)')",
    )

    # Tick both required boxes to arm the gate.
    required = page.query_selector_all(f"{root} input[data-required='true']")
    assert len(required) == 2
    required[0].check()
    required[1].check()

    # The gate is logically armed (aria-disabled dropped) but the dangerous
    # scheme is NOT promoted into the live href.
    href = page.get_attribute(primary, "href")
    assert href != "javascript:alert(1)", "javascript: scheme must never be promoted"
    assert href is None or href.startswith(("#", "/", "http")), href


def test_drawer_lazy_trigger_opens_dialog_and_loads_body(page) -> None:  # type: ignore[no-untyped-def]
    """The Dazzle peek slide_over contract: ONE trigger carrying BOTH an
    hx-get (body content) and data-dz-dialog-open (the drawer id). The
    dialog opener calls preventDefault(), which must NOT suppress the
    htmx exchange — both fire; the drawer opens showing the fetched
    body. Native close (Esc) dismisses."""
    goto_part(page, "drawer")
    # gallery strips the dz- prefix from data attrs
    trigger = '#drawer [data-dialog-open="hm-drawer-lazy"]'
    page.click(trigger)
    page.wait_for_timeout(150)
    assert page.get_attribute("#hm-drawer-lazy", "open") is not None
    body_text = page.inner_text("#hm-drawer-lazy-body")
    assert "Aurora Substation" in body_text, (
        "the hx-get must have fired alongside the dialog opener"
    )
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert page.get_attribute("#hm-drawer-lazy", "open") is None


def test_drawer_filters_compose_honest_guests(page) -> None:  # type: ignore[no-untyped-def]
    """Filters form_shell: switch track anatomy + toggle-group without legend
    + body text colour is primary (not host-muted inheritance)."""
    goto_part(page, "drawer")
    page.click('[data-dialog-open="hm-drawer-demo"]')
    page.wait_for_timeout(150)
    demo = "#hm-drawer-demo"
    assert page.evaluate(f"document.querySelector('{demo}').open")
    # Switch Hyperpart (not controls pill)
    assert page.locator(f"{demo} .switch__track").count() == 1
    assert page.locator(f"{demo} input[data-switch]").count() == 1
    assert page.locator(f"{demo} input.switch").count() == 0
    # Toggle-group: no legend inside fieldset
    assert page.locator(f"{demo} .toggle-group legend").count() == 0
    assert page.locator(f"{demo} .toggle-group").count() == 1
    # Body colour is primary (composition host)
    body_color = page.evaluate(
        """() => {
          const b = document.querySelector('#hm-drawer-demo .drawer__body');
          return getComputedStyle(b).color;
        }"""
    )
    label_color = page.evaluate(
        """() => {
          const el = document.querySelector('#hm-drawer-demo .form-label');
          return getComputedStyle(el).color;
        }"""
    )
    # Both should be the same primary (or label matches body); not a washed body
    assert body_color == label_color, (
        f"drawer body should use primary text so guests match standalone "
        f"(body={body_color}, label={label_color})"
    )
    page.keyboard.press("Escape")


def test_drawer_peek_composes_honest_kpi_cards(page) -> None:  # type: ignore[no-untyped-def]
    """exchange_shell peek: one card per metric, no form-field meta fork."""
    goto_part(page, "drawer")
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(200)
    body = "#hm-drawer-lazy-body"
    assert page.locator(f"{body} .card.card-body").count() >= 3, (
        "peek should mount one KPI card per metric (Card hyperpart scale)"
    )
    assert page.locator(f"{body} .form-field").count() == 0, (
        "read-only meta must not use form-field (hint is help, not value)"
    )
    assert page.locator(f'{body} .alert[role="alert"]').count() >= 1
    # Chrome symmetry: header/body/footer classes present
    for part in ("drawer__header", "drawer__body", "drawer__footer"):
        assert page.locator(f"#hm-drawer-lazy .{part}").count() == 1
    page.keyboard.press("Escape")


def test_drawer_open_full_page_is_real_navigation(page) -> None:  # type: ignore[no-untyped-def]
    """Open full page is an <a href> to the record Blueprint — not a no-op button."""
    goto_part(page, "drawer")
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(150)
    link = page.locator('#hm-drawer-lazy a.button[data-variant="primary"]')
    assert link.count() == 1
    href = link.get_attribute("href") or ""
    assert "blueprints/record-page" in href, (
        f"full-page CTA must point at record-page Blueprint, got {href!r}"
    )
    assert href.endswith(".html") or "record-page" in href
    assert link.evaluate("el => el.tagName") == "A"
    # Follow the link — full page document, not a widened dialog
    link.click()
    page.wait_for_timeout(300)
    assert "record-page" in page.url, f"expected navigation to record-page, url={page.url}"
    assert "Aurora Substation" in page.inner_text("body")
    assert page.locator("h1").count() >= 1


def test_drawer_expand_restore_toggles_width_without_navigation(page) -> None:  # type: ignore[no-untyped-def]
    """Expand/Restore is a 2-state chrome toggle — not full-page navigation.

    Labels name the next action; aria-pressed reflects expanded state.
    Assert *computed* width change (attr-only gates miss CSS/media bugs).
    """
    goto_part(page, "drawer")
    # Ensure viewport is wide enough for md vs xl presets (min-width: 40rem)
    page.set_viewport_size({"width": 1280, "height": 800})
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(200)
    dlg = page.locator("#hm-drawer-lazy")
    btn = page.locator(
        "#hm-drawer-lazy [data-drawer-expand], #hm-drawer-lazy [data-dz-drawer-expand]"
    )
    assert btn.count() == 1
    assert (
        dlg.get_attribute("data-width") in (None, "md") or dlg.get_attribute("data-width") == "md"
    )
    assert btn.get_attribute("aria-pressed") in (None, "false")
    label0 = (btn.inner_text() or "").strip().lower()
    assert "expand" in label0, f"resting label should be Expand, got {label0!r}"

    def _geom() -> dict:
        return page.evaluate(
            """() => {
              const d = document.getElementById('hm-drawer-lazy');
              const r = d.getBoundingClientRect();
              return {
                attr: d.getAttribute('data-width') || d.getAttribute('data-dz-width'),
                w: Math.round(r.width),
              };
            }"""
        )

    before = _geom()
    assert before["attr"] in (None, "md")
    assert before["w"] > 100

    # Real pointer (not only locator.click) — same path as a human
    box = btn.bounding_box()
    assert box is not None
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(200)
    after = _geom()
    assert after["attr"] == "xl", f"Expand should set xl, got {after['attr']!r}"
    assert after["w"] > before["w"] + 80, (
        f"Expand must visibly widen the panel (before={before['w']} after={after['w']})"
    )
    assert btn.get_attribute("aria-pressed") == "true"
    label1 = (btn.inner_text() or "").strip().lower()
    assert "restore" in label1, f"expanded label should be Restore, got {label1!r}"
    assert page.url.endswith("drawer.html") or "drawer" in page.url
    assert page.get_attribute("#hm-drawer-lazy", "open") is not None

    box2 = btn.bounding_box()
    assert box2 is not None
    page.mouse.click(box2["x"] + box2["width"] / 2, box2["y"] + box2["height"] / 2)
    page.wait_for_timeout(200)
    restored = _geom()
    assert restored["attr"] == "md", f"Restore should return to md, got {restored['attr']!r}"
    assert restored["w"] < after["w"] - 80, (
        f"Restore must visibly narrow (expanded={after['w']} restored={restored['w']})"
    )
    assert btn.get_attribute("aria-pressed") == "false"
    label2 = (btn.inner_text() or "").strip().lower()
    assert "expand" in label2, f"after restore label should be Expand, got {label2!r}"


def test_drawer_peek_body_scrolls_independently(page) -> None:  # type: ignore[no-untyped-def]
    """Peek fragment must be tall enough that drawer__body overflows.

    Demo obligation (stem host-chrome-symmetry): claiming independent body
    scroll requires content that actually overflows — short peeks hide the
    contract from agents and humans.
    """
    goto_part(page, "drawer")
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(250)
    # Wait for mock fragment (Aurora + activity)
    page.wait_for_selector("#hm-drawer-lazy-body .card-value", timeout=3000)
    assert "Aurora" in page.inner_text("#hm-drawer-lazy-body")
    metrics = page.evaluate(
        """() => {
          const body = document.getElementById('hm-drawer-lazy-body');
          if (!body) return null;
          const beforeWin = window.scrollY;
          const sh = body.scrollHeight;
          const ch = body.clientHeight;
          body.scrollTop = Math.min(sh - ch, 120);
          return {
            scrollHeight: sh,
            clientHeight: ch,
            bodyScrollTop: body.scrollTop,
            windowScrollY: window.scrollY,
            windowScrollYBefore: beforeWin,
            overflowY: getComputedStyle(body).overflowY,
          };
        }"""
    )
    assert metrics is not None
    assert metrics["scrollHeight"] > metrics["clientHeight"] + 40, (
        f"peek body must overflow to demo independent scroll "
        f"(scrollHeight={metrics['scrollHeight']}, clientHeight={metrics['clientHeight']})"
    )
    assert metrics["bodyScrollTop"] > 0, "body should accept scrollTop"
    assert metrics["windowScrollY"] == metrics["windowScrollYBefore"], (
        "scrolling the drawer body must not move the host window"
    )
    assert metrics["overflowY"] in ("auto", "scroll", "overlay")


def test_drawer_composed_badge_icon_matches_raw_badge(page) -> None:  # type: ignore[no-untyped-def]
    """Composed peek badges must size icons like the raw Badge gallery.

    Mock {i:} used to wrap icons in .icon--size-sm (1rem), fighting
    .badge-icon { width/height: 0.875em }. Product {svg:} emits bare svg.icon
    sized by the parent — mock must match.
    """
    goto_part(page, "badge")
    raw = page.evaluate(
        """() => {
          const b = document.querySelector('.hm-preview .badge[data-tone="success"]');
          const svg = b && b.querySelector('svg');
          const wrap = b && b.querySelector('.badge-icon');
          if (!svg || !wrap) return null;
          const sr = svg.getBoundingClientRect();
          const wr = wrap.getBoundingClientRect();
          return {
            svgW: Math.round(sr.width * 10) / 10,
            svgH: Math.round(sr.height * 10) / 10,
            wrapW: Math.round(wr.width * 10) / 10,
            nestedSizeSm: !!b.querySelector('.icon--size-sm, .dz-icon--size-sm'),
            svgParent: svg.parentElement && svg.parentElement.className,
          };
        }"""
    )
    assert raw is not None, "raw success badge missing from Badge gallery"
    assert not raw["nestedSizeSm"], "raw badge must not nest --size-sm"

    goto_part(page, "drawer")
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(250)
    page.wait_for_selector('#hm-drawer-lazy-body .badge[data-tone="success"]', timeout=3000)
    composed = page.evaluate(
        """() => {
          const b = document.querySelector('#hm-drawer-lazy-body .badge[data-tone="success"]');
          const svg = b && b.querySelector('svg');
          const wrap = b && b.querySelector('.badge-icon');
          if (!svg || !wrap) return null;
          const sr = svg.getBoundingClientRect();
          const wr = wrap.getBoundingClientRect();
          return {
            svgW: Math.round(sr.width * 10) / 10,
            svgH: Math.round(sr.height * 10) / 10,
            wrapW: Math.round(wr.width * 10) / 10,
            nestedSizeSm: !!b.querySelector('.icon--size-sm, .dz-icon--size-sm'),
            svgParent: svg.parentElement && svg.parentElement.className,
            html: b.outerHTML.slice(0, 200),
          };
        }"""
    )
    assert composed is not None, "composed Online badge missing from drawer peek"
    assert not composed["nestedSizeSm"], (
        f"composed badge must not nest --size-sm (mock expand regression): {composed['html']}"
    )
    assert composed["svgParent"] and "badge-icon" in composed["svgParent"], (
        f"svg should be direct child of .badge-icon like raw gallery, parent={composed['svgParent']!r}"
    )
    # Sizes should match raw within a pixel (same 0.875em contract)
    assert abs(composed["svgW"] - raw["svgW"]) <= 1.5, (
        f"composed badge svg width {composed['svgW']} vs raw {raw['svgW']}"
    )
    assert abs(composed["svgH"] - raw["svgH"]) <= 1.5, (
        f"composed badge svg height {composed['svgH']} vs raw {raw['svgH']}"
    )


def test_drawer_record_actions_load_panels(page) -> None:  # type: ignore[no-untyped-def]
    """Work orders / Show on map are independent actions with real fragments.

    Not a tab strip (equal outline + verb labels). Map must not be a no-op.
    """
    goto_part(page, "drawer")
    page.click('#drawer [data-dialog-open="hm-drawer-lazy"]')
    page.wait_for_timeout(250)
    page.wait_for_selector("#hm-drawer-record-panel", timeout=3000)
    body = "#hm-drawer-lazy-body"
    actions = page.locator(f'{body} [role="group"][aria-labelledby="hm-drawer-actions-label"]')
    assert actions.count() == 1
    wo = actions.locator("button", has_text="Work orders")
    show_map = actions.locator("button", has_text="Show on map")
    assert wo.count() == 1 and show_map.count() == 1
    # Same visual weight — not outline+ghost tab illusion
    assert wo.get_attribute("data-variant") == "outline"
    assert show_map.get_attribute("data-variant") == "outline"
    # Icon + label spacing comes from .button gap (not a text-node space)
    gap = wo.evaluate("el => getComputedStyle(el).gap")
    assert gap not in ("0px", "normal", ""), f"button icon gap missing: {gap!r}"

    show_map.click()
    page.wait_for_timeout(200)
    panel = page.inner_text("#hm-drawer-record-panel")
    assert "Site location" in panel or "Coordinates" in panel, (
        f"Show on map must load a location panel, got: {panel[:200]!r}"
    )
    assert "54.978" in panel or "N," in panel
    # Actions chrome stays; only the panel swapped
    assert actions.locator("button", has_text="Show on map").count() == 1

    wo.click()
    page.wait_for_timeout(200)
    panel2 = page.inner_text("#hm-drawer-record-panel")
    assert "WO-1842" in panel2 and "WO-1799" in panel2, (
        f"Work orders must list open WOs, got: {panel2[:200]!r}"
    )

    page.locator("#hm-drawer-record-panel button", has_text="Overview").click()
    page.wait_for_timeout(200)
    assert "Open WOs" in page.inner_text("#hm-drawer-record-panel") or "Region" in page.inner_text(
        "#hm-drawer-record-panel"
    )


def test_search_box_coaching_hides_on_type_via_pure_css(page) -> None:  # type: ignore[no-untyped-def]
    """The search-box coaching line is toggled by CSS alone
    (`:has(input:not(:placeholder-shown))`) — no client state. Typing
    hides it (before any swap); clearing brings it back; the debounced
    hx-get lands the results fragment."""
    goto_part(page, "search-box")
    # Scope to the first demo region — the part page also embeds contracts
    # with a second search-box; is_visible on a multi-match can hit the
    # still-empty second coaching line and false-fail.
    region = page.locator("#search-box .search-box-region").first
    coaching = region.locator(".search-box-empty")
    inp = region.locator("input[type=search]")

    assert coaching.is_visible()
    inp.fill("substation")
    # CSS hide and/or results swap remove the coaching line
    assert coaching.count() == 0 or not coaching.is_visible(), (
        "typing must hide the coaching line (CSS :has)"
    )
    page.wait_for_timeout(400)  # past the 250ms debounce
    assert "Aurora" in region.locator(".search-box-results").inner_text()
    # results were swapped in, so the coaching line is gone from the DOM —
    # but an untouched box (fresh reload) shows it again when empty
    page.reload()
    page.wait_for_timeout(300)
    assert (
        page.locator("#search-box .search-box-region")
        .first.locator(".search-box-empty")
        .is_visible()
    )


def test_search_box_no_results_state_survives_the_css_toggle(page) -> None:  # type: ignore[no-untyped-def]
    """SEV-1 regression pin (F3 review): the coaching-hide rule must NOT
    catch the server's zero-hit state — `dz-search-box-empty
    --no-results` arrives while the input is non-empty by construction,
    and hiding it would render a blank panel."""
    goto_part(page, "search-box")
    box = "#search-box .search-box-region"
    page.fill(f"{box} input[type=search]", "zzz-no-such")
    page.eval_on_selector(
        f"{box} .search-box-results",
        """el => { el.innerHTML =
          '<div class="search-box-empty search-box-empty--no-results">' +
          'No results for “zzz-no-such”</div>'; }""",
    )
    assert page.is_visible(f"{box} .search-box-empty--no-results"), (
        "the no-results line must stay visible while the input is non-empty"
    )
    page.reload()


def test_related_tables_tab_strip_rides_dz_tabs(page) -> None:  # type: ignore[no-untyped-def]
    """F4: the related-tables tab strip is the tabs Hyperpart (no Alpine
    activeTab island) — clicking Files reveals its panel and marks the
    tab current, scoped to the related group's own .dz-tabs root."""
    goto_part(page, "related-tables")
    root = "#related-tables .tabs"
    files_tab = f'{root} [data-tab-target="hm-rel-files"]'
    assert page.is_hidden("#hm-rel-files")
    page.click(files_tab)
    assert page.is_visible("#hm-rel-files")
    assert page.is_hidden("#hm-rel-invoices")
    assert page.get_attribute(files_tab, "aria-current") == "true"
    assert "contract.pdf" in page.inner_text("#hm-rel-files")


def test_search_select_opens_on_focus_and_survives_row_click(page) -> None:  # type: ignore[no-untyped-def]
    """F4b: open state is data-open / aria-expanded on the widget.

    Focus opens the panel; a result-row click (which blurs the input) must
    land its htmx select exchange within the blur grace. After select, the
    confirm fragment stays visible for data-confirm-hold-ms (gallery: 1800)
    — not hidden by the 200ms blur grace alone.
    """
    goto_part(page, "search-select")
    root = "#search-select .search-select"
    inp = f"{root} input[type=text]"
    panel = f"{root} .search-select-results"

    assert page.is_hidden(panel)
    page.focus(inp)
    assert page.is_visible(panel)

    page.fill(inp, "auro")
    page.wait_for_timeout(450)  # past the 300ms debounce
    assert "Aurora Energy" in page.inner_text(panel)
    # Optional media: company rows may be text-only; person rows carry media.
    assert page.locator(f"{panel} .search-result-row").count() >= 1

    page.click(f"{panel} .search-result-row >> nth=0")
    page.wait_for_timeout(300)
    # Select exchange landed within blur grace...
    assert "Selected" in page.inner_text(panel)
    # ...and confirm-hold keeps the panel open well past blur grace.
    assert page.is_visible(panel)
    page.wait_for_timeout(1000)  # still inside 1800ms hold
    assert page.is_visible(panel), "confirm-hold must keep panel open at ~1.3s"
    # After confirm hold (gallery sets 1800ms) the panel auto-dismisses.
    page.wait_for_timeout(1200)
    assert page.is_hidden(panel)
    page.reload()


def test_money_field_syncs_minor_carrier_and_normalizes(page) -> None:  # type: ignore[no-untyped-def]
    """F4c: typing a major amount keeps the hidden minor carrier in sync
    (input event); blur normalizes the display to the scale."""
    goto_part(page, "money")
    root = "#money [data-money]"
    inp = f"{root} input[inputmode=decimal]"
    minor = f"{root} input[name=amount_minor]"

    assert page.input_value(minor) == "1500"  # SSR'd from edit mode
    page.fill(inp, "12.5")
    assert page.input_value(minor) == "1250"
    page.eval_on_selector(inp, "el => el.blur()")
    page.wait_for_timeout(50)
    assert page.input_value(inp) == "12.50", "blur must normalize to scale"
    page.fill(inp, "")
    page.eval_on_selector(inp, "el => el.blur()")
    page.wait_for_timeout(50)
    assert page.input_value(minor) == "", "empty display clears the carrier"
    page.reload()


def test_wizard_forward_gated_on_validity_back_free(page) -> None:  # type: ignore[no-untyped-def]
    """F4d: forward navigation requires the current stage's required
    inputs to be valid; back navigation is always free; completed steps
    swap to the CSS checkmark."""
    goto_part(page, "wizard")
    root = "#wizard [data-wizard]"
    step2 = f'{root} [data-step-to="1"]'
    stage0 = f'{root} [data-stage="0"]'
    stage1 = f'{root} [data-stage="1"]'

    page.click(step2)  # required name is empty → blocked
    assert page.is_visible(stage0) and page.is_hidden(stage1)

    page.fill(f"{stage0} input[type=text]", "Aurora refit")
    page.click(step2)
    assert page.is_hidden(stage0) and page.is_visible(stage1)
    li0 = f'{root} li:has([data-step-to="0"])'
    li1 = f'{root} li:has([data-step-to="1"])'
    assert page.get_attribute(li0, "data-state") == "complete"
    assert page.get_attribute(li1, "aria-current") == "step"

    # skipping ahead two steps from a fresh stage is blocked (one at a time)
    page.click(f'{root} [data-step-to="0"]')  # back is free
    assert page.is_visible(stage0)
    page.click(f'{root} [data-step-to="2"]')
    assert page.is_visible(stage0), "forward is one validated step at a time"
    page.reload()


def test_pdf_viewer_renders_and_pages(page) -> None:  # type: ignore[no-untyped-def]
    """hx-pdf P2: the viewer lazy-loads PDF.js, renders page 1 of the
    real sample.pdf to a canvas, pages forward/back, and reports the
    count. Skips when the CDN is unreachable (offline CI runners) —
    the Dazzle-side P3 e2e is the vendored-lib oracle."""
    import urllib.request

    try:
        urllib.request.urlopen(
            "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/legacy/build/pdf.min.mjs",
            timeout=10,
        )
    except Exception:
        import pytest

        pytest.skip("PDF.js CDN unreachable")

    # PDF.js fetches the document — fetch() is blocked on file:// pages,
    # so this test serves the built site over an EPHEMERAL http port
    # (port 0; the fixed-port pdf-viewer-gates flake class is avoided).
    import functools
    import http.server
    import socketserver
    import threading
    from pathlib import Path

    site_dir = Path(__file__).resolve().parents[1] / "site"
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site_dir))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            page.goto(f"http://127.0.0.1:{port}/hyperparts/pdf.html")
            page.wait_for_timeout(300)
            _assert_pdf_viewer(page)
        finally:
            httpd.shutdown()


def _assert_pdf_viewer(page) -> None:  # type: ignore[no-untyped-def]
    root = "#pdf [data-pdf]"
    page.eval_on_selector(root, "el => el.scrollIntoView()")
    page.wait_for_selector(f'{root}[data-pdf-ready="true"]', timeout=30000)
    assert page.query_selector(f"{root} [data-pdf-viewer] canvas") is not None
    assert page.inner_text(f"{root} [data-pdf-page-count]") == "of 2"
    assert page.input_value(f"{root} [data-pdf-page]") == "1"

    page.click(f"{root} [data-pdf-next]")
    page.wait_for_function(f"document.querySelector('{root} [data-pdf-page]').value === '2'")
    page.click(f"{root} [data-pdf-prev]")
    page.wait_for_function(f"document.querySelector('{root} [data-pdf-page]').value === '1'")


def test_wizard_submit_jumps_to_first_invalid_stage(page) -> None:  # type: ignore[no-untyped-def]
    """#1548: submitting the enclosing form with an invalid required
    field in a LATER (hidden) stage must not be a silent no-op — the
    wizard intercepts at capture phase, jumps to the first invalid
    stage, and surfaces the validity bubble. A fully-valid form
    submits normally."""
    goto_part(page, "wizard")
    root = "#wizard [data-wizard]"
    # Wrap the demo wizard in a form with a submit button and make the
    # stage-1 date required — the page shape the experience renderer
    # produces (one form around all stages, always-visible Submit).
    page.evaluate(
        """() => {
          const wiz = document.querySelector('#wizard [data-wizard]');
          const form = document.createElement('form');
          form.id = 'wiz-form';
          form.addEventListener('submit', (e) => {
            e.preventDefault();
            window.__wizSubmitted = true;
          });
          wiz.parentElement.insertBefore(form, wiz);
          form.appendChild(wiz);
          const btn = document.createElement('button');
          btn.type = 'submit';
          btn.id = 'wiz-submit';
          btn.textContent = 'Submit';
          form.appendChild(btn);
          document.querySelector('#wizard [data-stage="1"] input[type=date]')
            .setAttribute('required', '');
        }"""
    )
    # Stage 0 valid; stage 1's required date is empty and HIDDEN.
    page.fill(f'{root} [data-stage="0"] input[type=text]', "Aurora refit")
    page.click("#wiz-submit")
    page.wait_for_timeout(50)
    # Not submitted; the wizard jumped forward to the invalid stage.
    assert page.evaluate("window.__wizSubmitted || false") is False
    assert page.is_visible(f'{root} [data-stage="1"]')
    assert page.is_hidden(f'{root} [data-stage="0"]')
    focused = page.evaluate("document.activeElement && document.activeElement.type")
    assert focused == "date", "the invalid input is focused for the validity bubble"

    # Fill it → submit proceeds.
    page.fill(f'{root} [data-stage="1"] input[type=date]', "2026-07-07")
    page.click("#wiz-submit")
    page.wait_for_timeout(50)
    assert page.evaluate("window.__wizSubmitted") is True
    page.reload()


# ── Combobox / tags / app-shell (drain PENDING_BEHAVIOUR) ──────────────
# Gallery strips the dz- prefix — selectors match the unprefixed dist.


def test_combobox_enhances_and_selects(page) -> None:  # type: ignore[no-untyped-def]
    """Native <select data-combobox> upgrades on interaction; pick writes select."""
    goto_part(page, "combobox")
    # Scope to the gallery preview — contract sections also render live exemplars.
    preview = page.locator(".hm-preview")
    # First select is the closed priority enum in the dual demo.
    sel = preview.locator("select[data-combobox]").first
    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = preview.locator(".combobox[data-enhanced]").first
    assert root.count() == 1
    assert root.get_attribute("data-open") == "true"
    # Keyboard-select High: value commits and listbox stays closed.
    root.locator(".combobox-input").fill("Hi")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert sel.input_value() == "high"
    assert root.locator(".combobox-input").input_value() == "High"
    assert root.get_attribute("data-open") is None
    # Default focus-after-select=blur — leave free-text / I-beam mode.
    assert not root.locator(".combobox-input").evaluate("el => el === document.activeElement")


def test_combobox_enhance_preserves_field_box(page) -> None:  # type: ignore[no-untyped-def]
    """Progressive enhance must not jump width/height (box-sizing / legacy class).

    Regression: <select class=form-input> is border-box; bare <input> was
    content-box, so min-height 2.5rem grew by padding+border (~18px) and
    width:100% overflowed by horizontal padding. Also a dead fragment
    `.combobox { display:flex; flex-direction:column }` stole the root.
    """
    goto_part(page, "combobox")
    preview = page.locator(".hm-preview")
    sel = preview.locator("select[data-combobox]").first
    before = sel.evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return {w: r.width, h: r.height, box: cs.boxSizing};
        }"""
    )
    assert before["box"] == "border-box"
    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = preview.locator(".combobox[data-enhanced]").first
    # Close listbox so root height is the field only (listbox is absolute either way).
    page.keyboard.press("Escape")
    page.wait_for_timeout(50)
    after = root.locator(".combobox-input").evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return {w: r.width, h: r.height, box: cs.boxSizing, display: cs.display};
        }"""
    )
    root_box = root.evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return {w: r.width, h: r.height, display: cs.display};
        }"""
    )
    assert after["box"] == "border-box", after
    assert root_box["display"] == "block", root_box
    assert abs(after["h"] - before["h"]) <= 1.0, (before, after)
    assert abs(after["w"] - before["w"]) <= 2.0, (before, after)
    assert abs(root_box["h"] - before["h"]) <= 1.0, (before, root_box)


def test_combobox_click_option_closes_listbox(page) -> None:  # type: ignore[no-untyped-def]
    """Pointer pick must close the picker (not re-open via focusin)."""
    goto_part(page, "combobox")
    preview = page.locator(".hm-preview")
    sel = preview.locator("select[data-combobox]").first
    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = preview.locator(".combobox[data-enhanced]").first
    assert root.get_attribute("data-open") == "true"
    root.locator('.combobox-option[data-value="high"]').click()
    page.wait_for_timeout(50)
    assert sel.input_value() == "high"
    assert root.locator(".combobox-input").input_value() == "High"
    assert root.get_attribute("data-open") is None
    assert not root.locator(".combobox-input").evaluate("el => el === document.activeElement")


def test_combobox_focus_after_select_keep(page) -> None:  # type: ignore[no-untyped-def]
    """data-focus-after-select=keep leaves the overlay input focused for re-filter."""
    goto_part(page, "combobox")
    preview = page.locator(".hm-preview")
    sel = preview.locator("select[data-combobox]").first
    sel.evaluate("el => el.setAttribute('data-focus-after-select', 'keep')")
    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = preview.locator(".combobox[data-enhanced]").first
    root.locator('.combobox-option[data-value="high"]').click()
    page.wait_for_timeout(50)
    assert sel.input_value() == "high"
    assert root.locator(".combobox-input").evaluate("el => el === document.activeElement")


def test_combobox_allow_create_appends_option(page) -> None:  # type: ignore[no-untyped-def]
    """Growing-list recipe: data-allow-create offers Add "…"; pick appends <option>."""
    goto_part(page, "combobox")
    preview = page.locator(".hm-preview")
    sel = preview.locator("select[data-allow-create], select[data-dz-allow-create]")
    assert sel.count() == 1
    sel.dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = sel.locator(
        "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' combobox ')][1]"
    )
    inp = root.locator(".combobox-input")
    inp.fill("docs")
    page.wait_for_timeout(50)
    create = root.locator(".combobox-create")
    assert create.is_visible()
    assert 'Add "docs"' in create.inner_text()
    create.click()
    page.wait_for_timeout(50)
    assert sel.input_value() == "docs"
    values = sel.evaluate("el => Array.from(el.options).map(o => o.value)")
    assert "docs" in values


def test_combobox_type_filters_options(page) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, "combobox")
    preview = page.locator(".hm-preview")
    preview.locator("select[data-combobox]").first.dispatch_event("pointerdown")
    page.wait_for_timeout(80)
    root = preview.locator(".combobox[data-enhanced]").first
    root.locator(".combobox-input").fill("ur")
    page.wait_for_timeout(50)
    visible = root.locator(".combobox-option:not([hidden]):not(.combobox-create)")
    # "Urgent" matches; empty placeholder is not an option row
    labels = [t.strip() for t in visible.all_text_contents() if t.strip() != "No matches"]
    assert labels == ["Urgent"], labels


def test_tags_seed_and_add_chip(page) -> None:  # type: ignore[no-untyped-def]
    """Native data-tags input upgrades; seeds from comma value; Enter adds chip."""
    goto_part(page, "tags")
    preview = page.locator(".hm-preview")
    preview.locator("input[data-tags]").dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    root = preview.locator(".tags[data-enhanced]")
    assert root.count() == 1
    chips = preview.locator(".tags-chip")
    assert chips.count() == 2  # seeded from "urgent,backend"
    preview.locator(".tags-entry").fill("frontend")
    page.keyboard.press("Enter")
    page.wait_for_timeout(50)
    assert chips.count() == 3
    assert preview.locator("input[data-tags]").input_value() == "urgent,backend,frontend"


def test_tags_remove_chip(page) -> None:  # type: ignore[no-untyped-def]
    goto_part(page, "tags")
    preview = page.locator(".hm-preview")
    preview.locator("input[data-tags]").dispatch_event("pointerdown")
    page.wait_for_timeout(100)
    preview.locator('button[aria-label="Remove urgent"]').click()
    page.wait_for_timeout(50)
    assert preview.locator(".tags-chip").count() == 1
    assert preview.locator("input[data-tags]").input_value() == "backend"


def test_app_shell_sidebar_toggle(page) -> None:  # type: ignore[no-untyped-def]
    """Live document: hamburger flips data-sidebar open↔closed.

    App-shell is framed=True in the part page (own browsing context for the
    fixed sidebar). Drive the same live document directly so the controller
    and hit-targets are top-level (iframe layout can mask the toggle).
    """
    goto_part(page, "app-shell")  # coverage meta-gate declaration
    live = (
        Path(__file__).resolve().parents[1] / "site" / "hyperparts" / "app-shell-live.html"
    ).as_uri()
    page.goto(live)
    page.wait_for_timeout(150)
    shell = page.locator(".app-shell")
    assert shell.get_attribute("data-sidebar") == "open"
    page.locator("[data-sidebar-toggle]").click()
    page.wait_for_timeout(80)
    assert shell.get_attribute("data-sidebar") == "closed"
    assert page.locator("[data-sidebar-toggle]").get_attribute("aria-expanded") == "false"
    page.locator("[data-sidebar-toggle]").click()
    page.wait_for_timeout(80)
    assert shell.get_attribute("data-sidebar") == "open"


def test_code_copy_uses_source_text(page) -> None:  # type: ignore[no-untyped-def]
    """code Hyperpart: copy control writes the plain source (textContent) and
    shows the data-copied feedback. Clipboard is stubbed — file:// hosts often
    deny the real Clipboard API."""
    goto_part(page, "code")
    page.evaluate(
        """() => {
          window.__hmCopied = null;
          navigator.clipboard.writeText = (t) => {
            window.__hmCopied = t;
            return Promise.resolve();
          };
        }"""
    )
    # Unprefixed gallery: data-code / .code__* (not data-dz-*)
    preview = page.locator("#code .hm-preview")
    preview.locator("[data-code-copy]").click()
    page.wait_for_timeout(120)
    copied = page.evaluate("window.__hmCopied")
    assert copied is not None, "copy control must call clipboard.writeText"
    assert "def greet" in copied
    assert "<span" not in copied, "clipboard must be plain text, not highlighted HTML"
    assert preview.locator("[data-code-copy][data-copied]").count() == 1
