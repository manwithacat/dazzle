"""`hidden` means hidden (#1799, pinned for #1803).

A layered ``[hidden]:not([hidden="until-found"]) { display: none !important }``
in ``@layer base`` must beat every component's ``display:`` declaration. These
cases load the built bundles and assert primitives that set ``display`` do not
paint when ``hidden``; ``until-found`` keeps its UA behaviour.
"""

from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
BUNDLES = {
    "hm": PKG / "dist" / "hatchi-maxchi.css",
    "dazzle": PKG.parents[1] / "src/dazzle/page/runtime/static/dist/dazzle.min.css",
}


@pytest.fixture(scope="module")
def _browser():  # type: ignore[no-untyped-def]
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 — missing engine binary skips
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.mark.parametrize("bundle", sorted(BUNDLES))
@pytest.mark.parametrize(
    "markup",
    [
        '<button class="dz-button" hidden>x</button>',
        '<div class="dz-alert" hidden>x</div>',
        '<div class="dz-stack" hidden>x</div>',
    ],
)
def test_hidden_primitive_does_not_paint(_browser, bundle, markup) -> None:  # type: ignore[no-untyped-def]
    css = BUNDLES[bundle].read_text()
    page = _browser.new_page()
    page.set_content(f"<style>{css}</style><body>{markup}</body>")
    shown = page.evaluate("getComputedStyle(document.body.firstElementChild).display")
    # Control: without `hidden` the primitive really sets a painting display.
    page.evaluate("document.body.firstElementChild.removeAttribute('hidden')")
    control = page.evaluate("getComputedStyle(document.body.firstElementChild).display")
    page.close()
    assert control != "none", f"{markup} never paints; test is vacuous"
    assert shown == "none"


def test_hidden_until_found_is_left_to_the_ua(_browser) -> None:  # type: ignore[no-untyped-def]
    css = BUNDLES["hm"].read_text()
    page = _browser.new_page()
    page.set_content(
        f'<style>{css}</style><body><div class="dz-stack" hidden="until-found">x</div></body>'
    )
    # UA: content-visibility:hidden, not display:none — the guard must not force it.
    display = page.evaluate("getComputedStyle(document.body.firstElementChild).display")
    page.close()
    assert display != "none"
