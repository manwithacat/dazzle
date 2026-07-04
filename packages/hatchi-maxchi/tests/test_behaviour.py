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
    page.click("[hx-confirm]")
    page.wait_for_timeout(150)
    assert page.evaluate(
        "!!document.querySelector('dialog.alert-dialog') && "
        "document.querySelector('dialog.alert-dialog').open"
    ), "clicking an hx-confirm element must open the designed dz-alert-dialog"


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
