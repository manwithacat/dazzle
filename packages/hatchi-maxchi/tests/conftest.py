"""Shared fixtures — a Chromium page pointed at the committed gallery."""

from collections.abc import Iterator
from pathlib import Path

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
