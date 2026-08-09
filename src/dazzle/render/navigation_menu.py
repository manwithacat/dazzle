"""Site navigation-menu builder — product top nav from sitespec.

Sitespec ``layout.nav`` public/authenticated items become an HM
``NavigationMenu`` dual-lock strip (``.dz-navigation-menu``), distinct from
app-chrome menubar and the app-shell sidebar.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment.primitives.navigation import (
    NavigationMenu,
    NavigationMenuBranch,
    NavigationMenuGroup,
    NavigationMenuLink,
)


def _href_of(item: Any) -> str:
    href = getattr(item, "href", None)
    if href is None and isinstance(item, dict):
        href = item.get("href")
    return str(href or "").strip()


def _label_of(item: Any) -> str:
    label = getattr(item, "label", None)
    if label is None and isinstance(item, dict):
        label = item.get("label")
    return str(label or "").strip()


def _is_current(href: str, current_route: str) -> bool:
    if not href or not current_route:
        return False
    a = href.rstrip("/") or "/"
    b = current_route.rstrip("/") or "/"
    return a == b


def _link_from(raw: Any, route: str) -> NavigationMenuLink | None:
    label = _label_of(raw)
    if not label:
        return None
    href = _href_of(raw) or None
    desc = getattr(raw, "description", None)
    if desc is None and isinstance(raw, dict):
        desc = raw.get("description") or raw.get("sublabel")
    return NavigationMenuLink(
        label=label,
        href=href,
        current=_is_current(href or "", route),
        description=str(desc or "").strip(),
    )


def _group_from(child: Any, route: str) -> NavigationMenuGroup | None:
    """Accept a titled group dict/object or a bare link."""
    if isinstance(child, dict) and ("links" in child or "title" in child):
        title = str(child.get("title") or "").strip()
        raw_links = list(child.get("links") or [])
    elif hasattr(child, "links"):
        title = str(getattr(child, "title", "") or "").strip()
        raw_links = list(getattr(child, "links", None) or [])
    else:
        title = ""
        raw_links = [child]
    links = tuple(link for raw in raw_links if (link := _link_from(raw, route)) is not None)
    if not links:
        return None
    return NavigationMenuGroup(links=links, title=title)


def _children_of(raw: Any) -> list[Any] | None:
    children = getattr(raw, "children", None)
    if children is None and isinstance(raw, dict):
        children = raw.get("children") or raw.get("groups")
    if not children:
        return None
    return list(children)


def _branch_from(raw: Any, route: str, label: str) -> NavigationMenuBranch | None:
    children = _children_of(raw)
    if children is None:
        return None
    groups = tuple(g for child in children if (g := _group_from(child, route)) is not None)
    if not groups:
        return None
    mega = bool(getattr(raw, "mega", False))
    if not mega and isinstance(raw, dict):
        mega = bool(raw.get("mega"))
    if not mega:
        mega = len(groups) > 1
    return NavigationMenuBranch(label=label, groups=groups, mega=mega)


def _item_from(raw: Any, route: str) -> NavigationMenuLink | NavigationMenuBranch | None:
    label = _label_of(raw)
    if not label:
        return None
    branch = _branch_from(raw, route, label)
    if branch is not None:
        return branch
    return _link_from(raw, route)


def build_site_navigation_menu(
    nav_items: Any,
    *,
    current_route: str = "",
    aria_label: str = "Product",
) -> NavigationMenu | None:
    """Build a NavigationMenu from sitespec-style nav items, or None if empty.

    Flat ``label``/``href`` rows become top-level links. Dict/object items with
    ``children`` / ``groups`` become mega branches (first-class fragment path
    for richer sitespec later; examples today are flat).
    """
    if not nav_items:
        return None
    route = str(current_route or "").strip()
    items = tuple(item for raw in nav_items if (item := _item_from(raw, route)) is not None)
    if not items:
        return None
    return NavigationMenu(items=items, aria_label=aria_label or "Product")
