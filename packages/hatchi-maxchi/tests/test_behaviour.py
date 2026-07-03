"""Console-domain behaviour gates — the interactive contracts, in a real
browser against the committed gallery (file://, mock htmx).

Regression pins for the two launch bugs:
- Esc must close the palette on the FIRST press even mid-query
  (input type="search" natively swallows Esc to clear its value).
- The light/dark toggle must actually flip rendered colours (a page-level
  color-scheme declaration once overrode the [data-theme] binding).
"""

PALETTE = "dialog.dz-command"
INPUT = ".dz-command__input"


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


def test_palette_arrows_and_enter(page) -> None:  # type: ignore[no-untyped-def]
    _open_palette(page)
    page.focus(f"{PALETTE} {INPUT}")  # focus triggers the mock hx-get
    page.wait_for_timeout(200)
    count = page.evaluate(f"document.querySelectorAll('{PALETTE} .dz-command__item').length")
    assert count >= 3, "mock results should populate on focus"
    # afterSwap preselects index 0; two ArrowDowns land on index 2
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    selected = page.evaluate(
        f"document.querySelectorAll('{PALETTE} .dz-command__item')[2].getAttribute('aria-selected')"
    )
    assert selected == "true"


def test_confirm_dialog_intercepts_hx_confirm(page) -> None:  # type: ignore[no-untyped-def]
    page.click("[hx-confirm]")
    page.wait_for_timeout(150)
    assert page.evaluate(
        "!!document.querySelector('dialog.dz-alert-dialog') && "
        "document.querySelector('dialog.dz-alert-dialog').open"
    ), "clicking an hx-confirm element must open the designed dz-alert-dialog"


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
