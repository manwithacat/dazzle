"""Static floors for disclosure affordance chrome (agent-reconstructable)."""

from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
NAV_CSS = (PKG / "components" / "navigation-menu.css").read_text(encoding="utf-8")
ACC_CSS = (PKG / "components" / "accordion.css").read_text(encoding="utf-8")


def test_navigation_menu_partial_has_no_unicode_caret() -> None:
    import sys

    sys.path.insert(0, str(PKG / "site"))
    from registry import HYPERPARTS  # type: ignore[import-not-found]

    h = next(x for x in HYPERPARTS if x.id == "navigation-menu")
    assert "▾" not in h.partial
    assert "navigation-menu__caret" not in h.partial
    assert "dz-navigation-menu__caret" not in h.partial


def test_navigation_menu_css_uses_rem_mask_chevron_not_em_caret() -> None:
    assert "navigation-menu__caret" not in NAV_CSS or "font-size: 0.65em" not in NAV_CSS
    assert "__trigger::after" in NAV_CSS
    assert re.search(r"width:\s*1rem", NAV_CSS)
    assert re.search(r"height:\s*1rem", NAV_CSS)
    assert "mask:" in NAV_CSS or "-webkit-mask:" in NAV_CSS
    # no tiny em-scale caret rule
    assert not re.search(
        r"navigation-menu__caret\s*\{[^}]*font-size:\s*0\.[0-6]\d*em",
        NAV_CSS,
        re.S,
    )


def test_accordion_and_nav_share_disclosure_mask_family() -> None:
    """Both use SVG path mask chevrons — house language (stem)."""
    for css in (ACC_CSS, NAV_CSS):
        assert "m6 9 6 6 6-6" in css or "mask:" in css
        assert "1rem" in css


def test_tabs_css_forces_square_radius_for_underline() -> None:
    """base.css button radius would curve border-block-end — tabs must zero it."""
    tabs_css = (PKG / "components" / "tabs.css").read_text(encoding="utf-8")
    assert "border-radius: 0" in tabs_css
    assert "selection-strip-honest" in tabs_css or "straight" in tabs_css.lower()


def test_shortcut_hint_layout_roles_in_hm_core() -> None:
    """Adjacent gap on button:has(kbd); trailing auto on command items."""
    core = (PKG / "components" / "hm-core.css").read_text(encoding="utf-8")
    assert "shortcut-hint-chrome" in core or ":has(> .dz-kbd)" in core
    assert "gap: var(--space-sm)" in core
    assert ".dz-command__item .dz-kbd" in core
    assert "margin-inline-start: auto" in core
