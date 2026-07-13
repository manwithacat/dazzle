"""Shared fixtures — a Chromium page pointed at the committed gallery.

Settlement helpers (decision 0010): wait for DOM attrs **and** layout bands so
WebKit/Chromium mid-transition flakes do not require per-test copy-paste.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

PKG = Path(__file__).resolve().parents[1]
SITE_URI = (PKG / "site" / "index.html").as_uri()


def part_uri(part_id: str) -> str:
    """file:// URI of a part's standalone page — the atomic fixture."""
    return (PKG / "site" / "hyperparts" / f"{part_id}.html").as_uri()


def goto_part(page, part_id: str) -> None:  # type: ignore[no-untyped-def]
    """Navigate to a part's atomic page. Behaviour scenarios call this first;
    the coverage meta-gate greps for these calls to prove per-part coverage."""
    page.goto(part_uri(part_id))
    page.wait_for_timeout(200)


def wait_for_attr(
    page,  # type: ignore[no-untyped-def]
    selector: str,
    attr: str,
    value: str | None,
    *,
    timeout: float = 4000,
) -> None:
    """Wait until ``selector`` has ``attr`` equal to ``value`` (or absent if None)."""
    page.wait_for_function(
        """([sel, attr, want]) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          const got = el.getAttribute(attr);
          if (want === null) return got === null;
          return got === want;
        }""",
        arg=[selector, attr, value],
        timeout=timeout,
    )


def wait_for_layout(
    page,  # type: ignore[no-untyped-def]
    selector: str,
    *,
    attr: str | None = None,
    attr_value: str | None = None,
    attr_fallback: str | None = None,
    attr_default: str | None = None,
    min_w: float | None = None,
    max_w: float | None = None,
    min_h: float | None = None,
    max_h: float | None = None,
    require_open: bool = False,
    timeout: float = 4000,
    settle_ms: int = 50,
) -> dict[str, Any]:
    """Wait until selector matches optional attr + layout bands; return geometry.

    Use for post-transition checks (drawer expand width, stage size, etc.).
    ``attr_fallback`` is a second attribute name to read when ``attr`` is empty
    (dual-lock: e.g. ``data-width`` then ``data-dz-width``).
    ``attr_default`` is used when both attrs are absent (e.g. resting ``md``).
    """
    page.wait_for_function(
        """([sel, attr, want, fallback, defVal, minW, maxW, minH, maxH, requireOpen]) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          if (requireOpen && !el.open && el.getAttribute('open') === null) return false;
          if (attr != null && want != null) {
            let a = el.getAttribute(attr);
            if ((a == null || a === '') && fallback) a = el.getAttribute(fallback);
            if (a == null || a === '') a = defVal;
            if (a !== want) return false;
          }
          const r = el.getBoundingClientRect();
          if (minW != null && r.width < minW) return false;
          if (maxW != null && r.width > maxW) return false;
          if (minH != null && r.height < minH) return false;
          if (maxH != null && r.height > maxH) return false;
          return true;
        }""",
        arg=[
            selector,
            attr,
            attr_value,
            attr_fallback,
            attr_default,
            min_w,
            max_w,
            min_h,
            max_h,
            require_open,
        ],
        timeout=timeout,
    )
    if settle_ms:
        # One extra paint after the band check so WebKit finishes layout
        page.wait_for_timeout(settle_ms)
    return page.evaluate(
        """(sel) => {
          const el = document.querySelector(sel);
          if (!el) return { missing: true };
          const r = el.getBoundingClientRect();
          return {
            w: Math.round(r.width),
            h: Math.round(r.height),
            open: !!(el.open || el.getAttribute('open') !== null),
          };
        }""",
        selector,
    )


def prefer_reduced_motion(page, reduce: bool = True) -> None:  # type: ignore[no-untyped-def]
    """Emulate prefers-reduced-motion for autoplay / transition-sensitive demos."""
    page.emulate_media(reduced_motion="reduce" if reduce else "no-preference")


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser):  # type: ignore[no-untyped-def]
    pg = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(SITE_URI)
    pg.wait_for_timeout(200)
    yield pg
    assert not errors, f"gallery page threw JS errors: {errors}"
    pg.close()
