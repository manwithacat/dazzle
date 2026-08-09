"""navigation-menu hyperpart emitter — unit pins (cycle 1773).

Sitespec ``layout.nav`` → shell ``NavigationMenu`` / ``.dz-navigation-menu``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import (
    FragmentRenderer,
    NavigationMenu,
    NavigationMenuBranch,
    NavigationMenuGroup,
    NavigationMenuLink,
)
from dazzle.render.navigation_menu import build_site_navigation_menu

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "examples" / "design_studio"


def test_navigation_menu_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        NavigationMenu(
            items=(
                NavigationMenuLink(label="Home", href="/", current=True),
                NavigationMenuBranch(
                    label="Product",
                    mega=True,
                    groups=(
                        NavigationMenuGroup(
                            title="Build",
                            links=(
                                NavigationMenuLink(
                                    label="DSL apps",
                                    href="/product/dsl",
                                    description="Ship CRUD + workflows",
                                ),
                            ),
                        ),
                        NavigationMenuGroup(
                            title="Operate",
                            links=(NavigationMenuLink(label="Deploy", href="/product/deploy"),),
                        ),
                    ),
                ),
                NavigationMenuLink(label="Pricing", href="/pricing"),
            )
        )
    )
    assert 'class="dz-navigation-menu"' in html
    assert "data-dz-navigation-menu" in html
    assert 'class="dz-navigation-menu__list"' in html
    assert 'class="dz-navigation-menu__link"' in html
    assert 'class="dz-navigation-menu__branch"' in html
    assert 'class="dz-navigation-menu__trigger"' in html
    assert 'class="dz-navigation-menu__panel"' in html
    assert 'data-dz-layout="mega"' in html
    assert 'aria-current="page"' in html
    assert "Home" in html
    assert "Product" in html
    assert "DSL apps" in html
    assert "Ship CRUD + workflows" in html
    assert 'href="/pricing"' in html


def test_build_site_navigation_menu_from_flat_items() -> None:
    items = [
        SimpleNamespace(label="Home", href="/"),
        SimpleNamespace(label="Sign In", href="/login"),
    ]
    menu = build_site_navigation_menu(items, current_route="/")
    assert menu is not None
    assert len(menu.items) == 2
    assert isinstance(menu.items[0], NavigationMenuLink)
    assert menu.items[0].current is True
    html = FragmentRenderer().render(menu)
    assert "data-dz-navigation-menu" in html
    assert "Sign In" in html


def test_build_site_navigation_menu_empty() -> None:
    assert build_site_navigation_menu([]) is None
    assert build_site_navigation_menu(None) is None


def test_design_studio_sitespec_declares_public_nav() -> None:
    text = (DESIGN / "sitespec.yaml").read_text(encoding="utf-8")
    assert "nav:" in text
    assert "Home" in text


def test_navigation_menu_shape_live() -> None:
    snap = shapes_snapshot()
    assert "navigation-menu" not in snap["planned_ids"]
    assert snap["next_planned"] != "navigation-menu"
