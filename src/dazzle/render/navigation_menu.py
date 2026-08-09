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
    items: list[NavigationMenuLink | NavigationMenuBranch] = []
    route = str(current_route or "").strip()
    for raw in nav_items:
        label = _label_of(raw)
        if not label:
            continue
        children = getattr(raw, "children", None)
        if children is None and isinstance(raw, dict):
            children = raw.get("children") or raw.get("groups")
        if children:
            groups: list[NavigationMenuGroup] = []
            for child in children:
                g_title = ""
                g_links_raw: list[Any]
                if isinstance(child, dict) and ("links" in child or "title" in child):
                    g_title = str(child.get("title") or "").strip()
                    g_links_raw = list(child.get("links") or [])
                elif hasattr(child, "links"):
                    g_title = str(getattr(child, "title", "") or "").strip()
                    g_links_raw = list(getattr(child, "links", None) or [])
                else:
                    g_links_raw = [child]
                links: list[NavigationMenuLink] = []
                for link in g_links_raw:
                    ll = _label_of(link)
                    if not ll:
                        continue
                    lh = _href_of(link) or None
                    desc = getattr(link, "description", None)
                    if desc is None and isinstance(link, dict):
                        desc = link.get("description") or link.get("sublabel")
                    links.append(
                        NavigationMenuLink(
                            label=ll,
                            href=lh,
                            current=_is_current(lh or "", route),
                            description=str(desc or "").strip(),
                        )
                    )
                if links:
                    groups.append(NavigationMenuGroup(links=tuple(links), title=g_title))
            if groups:
                mega = bool(getattr(raw, "mega", False))
                if not mega and isinstance(raw, dict):
                    mega = bool(raw.get("mega"))
                if not mega:
                    mega = len(groups) > 1
                items.append(NavigationMenuBranch(label=label, groups=tuple(groups), mega=mega))
            continue
        href = _href_of(raw) or None
        items.append(
            NavigationMenuLink(
                label=label,
                href=href,
                current=_is_current(href or "", route),
            )
        )
    if not items:
        return None
    return NavigationMenu(items=tuple(items), aria_label=aria_label or "Product")
