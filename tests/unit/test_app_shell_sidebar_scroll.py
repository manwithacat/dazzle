"""#1596 — dual-lock long sidebar must scroll on ``.dz-sidebar`` itself.

Persona nav is ``nav.dz-sidebar > details.dz-nav-group…`` with no
``.dz-sidebar-nav`` wrapper, so overflow on ``.dz-sidebar-nav`` alone leaves
bottom groups unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_SHELL = Path(__file__).resolve().parents[2] / "packages/hatchi-maxchi/components/app-shell.css"


@pytest.fixture(scope="module")
def app_shell_css() -> str:
    assert APP_SHELL.is_file(), f"missing {APP_SHELL}"
    return APP_SHELL.read_text(encoding="utf-8")


def test_dz_sidebar_declares_vertical_overflow(app_shell_css: str) -> None:
    """The primary ``.dz-sidebar`` rule must own overflow-y (not only nav)."""
    # Split on the dual-lock/sidebar contract comment so we inspect the
    # fixed panel rule, not a stray utility.
    assert "overflow-y: auto" in app_shell_css
    assert "overscroll-behavior: contain" in app_shell_css
    # sticky brand/header preferred while the panel scrolls
    assert ".dz-sidebar__header" in app_shell_css
    assert "position: sticky" in app_shell_css
    # legacy wrapper still scrolls for brand+nav+footer shells
    assert ".dz-sidebar-nav" in app_shell_css


def test_sidebar_overflow_is_not_only_on_nav_wrapper(app_shell_css: str) -> None:
    """Regression: pre-fix only ``.dz-sidebar-nav`` scrolled."""
    # Crude but stable: after the main ``.dz-sidebar {`` open brace that
    # includes ``position: fixed``, overflow-y must appear before the
    # closing of that rule's property block (next top-level selector).
    marker = ".dz-sidebar {\n  position: fixed;"
    idx = app_shell_css.find(marker)
    assert idx != -1, "expected fixed .dz-sidebar panel rule"
    chunk = app_shell_css[idx : idx + 600]
    assert "overflow-y: auto" in chunk
    assert "overscroll-behavior: contain" in chunk
