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


def test_copy_button_copies_and_gives_feedback(browser) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    SITE_URI = (Path(__file__).resolve().parents[1] / "site" / "index.html").as_uri()
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    page = ctx.new_page()
    page.goto(SITE_URI)
    page.wait_for_timeout(200)
    page.evaluate("document.querySelectorAll('.hm-copy')[0].click()")
    page.wait_for_timeout(150)
    assert page.evaluate("document.querySelectorAll('.hm-copy')[0].hasAttribute('data-copied')"), (
        "copy click must flip the button into its Copied state"
    )
    clip = page.evaluate("navigator.clipboard.readText()")
    assert clip.strip().startswith("<"), "clipboard should hold the snippet HTML"
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
