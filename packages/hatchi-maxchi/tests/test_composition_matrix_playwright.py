"""Playwright coherence for composition matrix cells.

Structural validate is browser-free; this module mounts assembled host×guest
HTML with the real HM stylesheet and checks:

- guest root paints a non-zero box
- drawer/dialog body colour is primary (matches form labels when present)
- switch track has geometry
- toggle-group is not collapsed by a legend fork

Keeps the cell set small (PLAYWRIGHT_CELLS) so CI stays fast.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG / "tools"))
sys.path.insert(0, str(PKG))

from build import apply_prefix  # noqa: E402
from composition_matrix import (  # noqa: E402
    GUESTS,
    HOSTS,
    PLAYWRIGHT_CELLS,
    assemble,
    cell_policy,
)

# Gallery stylesheet is unprefixed (empty prefix) — same dialect as site/.
CSS = (PKG / "site" / "hatchi-maxchi.css").read_text(encoding="utf-8")


def _page_html(host_id: str, guest_id: str) -> str:
    # Matrix catalog keeps dual-lock dz-* source; strip for gallery CSS.
    body = apply_prefix(
        assemble(host_id, guest_id, title=f"{host_id} × {guest_id}"),
        "",
    )
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>composition matrix</title>
<style>
{CSS}
body {{ margin: 0; font-family: var(--font-sans, system-ui); background: var(--colour-bg, #fff); }}
</style>
</head>
<body>
{body}
<script>
document.querySelectorAll('dialog').forEach(function (d) {{
  try {{ d.showModal(); }} catch (e) {{ d.setAttribute('open', ''); }}
}});
</script>
</body></html>"""


@pytest.fixture(scope="module")
def browser():  # type: ignore[no-untyped-def]
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser):  # type: ignore[no-untyped-def]
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    yield pg
    pg.close()


@pytest.mark.parametrize("host_id,guest_id", PLAYWRIGHT_CELLS)
def test_matrix_cell_renders_coherently(page, host_id: str, guest_id: str) -> None:  # type: ignore[no-untyped-def]
    ok, reason = cell_policy(host_id, guest_id)
    assert ok, f"PLAYWRIGHT_CELLS must be compatible: {host_id}×{guest_id}: {reason}"
    assert host_id in HOSTS and guest_id in GUESTS

    page.set_content(_page_html(host_id, guest_id), wait_until="domcontentloaded")
    page.wait_for_timeout(80)

    host = HOSTS[host_id]
    guest = GUESTS[guest_id]
    # Unprefixed gallery dialect
    body_sel = f".{host.host}__body"
    assert page.locator(body_sel).count() >= 1

    # Guest root has a painted box (prefer unprefixed selector branch)
    root = guest.root_selector or f".{guest_id}"
    box = page.locator(root).first.bounding_box()
    assert box is not None, f"{host_id}×{guest_id}: guest {root!r} has no box"
    assert box["width"] > 0 and box["height"] > 0, f"{host_id}×{guest_id}: guest collapsed to {box}"

    # Body uses primary text (composition host — not whole-body muted)
    body_color, title_color = page.evaluate(
        f"""() => {{
          const body = document.querySelector({body_sel!r});
          const title = document.querySelector('.{host.host}__title');
          const cs = getComputedStyle(body);
          const ts = title ? getComputedStyle(title) : null;
          return [cs.color, ts ? ts.color : null];
        }}"""
    )
    assert body_color, "body colour missing"
    if title_color:
        assert body_color == title_color, (
            f"body should inherit primary like title "
            f"(body={body_color}, title={title_color}) for {host_id}×{guest_id}"
        )

    if guest_id == "switch":
        track = page.locator(".switch__track").first.bounding_box()
        assert track and track["width"] >= 24 and track["height"] >= 12, (
            f"switch track geometry off: {track}"
        )

    if guest_id == "toggle-group":
        assert page.locator(".toggle-group legend").count() == 0
        tg = page.locator(".toggle-group").first.bounding_box()
        assert tg and tg["width"] > 40, f"toggle-group looks broken: {tg}"

    if guest_id == "card":
        sizes = page.evaluate(
            """() => {
              const label = document.querySelector('.card-label');
              const value = document.querySelector('.card-value');
              if (!label || !value) return null;
              return {
                label: parseFloat(getComputedStyle(label).fontSize),
                value: parseFloat(getComputedStyle(value).fontSize),
              };
            }"""
        )
        assert sizes is not None
        assert sizes["value"] > sizes["label"], f"card value should read larger than label: {sizes}"

    if guest_id == "tabs":
        assert page.locator(".tabs__tab").count() >= 2
        tab = page.locator(".tabs__tab").first.bounding_box()
        assert tab and tab["height"] > 0
