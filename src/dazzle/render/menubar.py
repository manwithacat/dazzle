"""Shell menubar builder — app chrome File/Edit-style strip from nav.

When the app opts in with ``menubar: true`` (app config features map), the
shell mounts an HM Menubar dual-lock strip in the topbar leading slot.
Menus are derived from titled nav groups (or a flat Go menu from items).
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment.primitives.navigation import (
    Menubar,
    MenubarAction,
    MenubarMenu,
)


def _feature_menubar_enabled(ctx: Any) -> bool:
    if bool(getattr(ctx, "shell_menubar", False)):
        return True
    extra = getattr(ctx, "extra", None) or {}
    if isinstance(extra, dict) and extra.get("menubar"):
        return True
    return False


def _actions_from_links(links: list[Any]) -> tuple[MenubarAction, ...]:
    actions: list[MenubarAction] = []
    for link in links:
        label = str(getattr(link, "label", None) or getattr(link, "title", None) or "").strip()
        if not label and isinstance(link, dict):
            label = str(link.get("label") or link.get("title") or "").strip()
        if not label:
            continue
        route = getattr(link, "route", None) or getattr(link, "href", None)
        if route is None and isinstance(link, dict):
            route = link.get("route") or link.get("href")
        href = str(route).strip() if route else None
        if href == "":
            href = None
        actions.append(MenubarAction(label=label, href=href))
    return tuple(actions)


def _menus_from_nav_model(model: Any) -> list[MenubarMenu]:
    menus: list[MenubarMenu] = []
    flat_actions: list[MenubarAction] = []
    for ng in getattr(model, "groups", None) or []:
        label = str(getattr(ng, "label", "") or "").strip()
        links = list(getattr(ng, "links", None) or [])
        actions = _actions_from_links(links)
        if not actions:
            continue
        if label:
            menus.append(MenubarMenu(label=label, actions=actions))
        else:
            flat_actions.extend(actions)
    if flat_actions and not menus:
        menus.append(MenubarMenu(label="Go", actions=tuple(flat_actions)))
    elif flat_actions:
        # Prefer titled groups; append remaining flat links under Go.
        menus.append(MenubarMenu(label="Go", actions=tuple(flat_actions)))
    return menus


def _menus_from_legacy_nav(ctx: Any) -> list[MenubarMenu]:
    menus: list[MenubarMenu] = []
    for group in getattr(ctx, "nav_groups", None) or []:
        if not isinstance(group, dict):
            continue
        label = str(group.get("label") or "").strip()
        children = list(group.get("children") or [])
        actions = _actions_from_links(children)
        if label and actions:
            menus.append(MenubarMenu(label=label, actions=actions))
    if menus:
        return menus
    flat = _actions_from_links(list(getattr(ctx, "nav_items", None) or []))
    if flat:
        return [MenubarMenu(label="Go", actions=flat)]
    return []


def _fallback_app_menus(ctx: Any) -> list[MenubarMenu]:
    """Minimal File/Edit/View chrome when opt-in is on but nav is empty."""
    app = str(getattr(ctx, "app_name", None) or "App").strip() or "App"
    home = getattr(ctx, "current_route", None) or "/app"
    home_s = str(home).strip() or "/app"
    return [
        MenubarMenu(
            label="File",
            actions=(
                MenubarAction(label=f"Open {app}", href=home_s),
                MenubarAction(label="Export…", href=None),
            ),
        ),
        MenubarMenu(
            label="Edit",
            actions=(MenubarAction(label="Preferences", href=None),),
        ),
        MenubarMenu(
            label="View",
            actions=(MenubarAction(label="Home", href=home_s),),
        ),
    ]


def build_shell_menubar(ctx: Any) -> Menubar | None:
    """Return a Menubar for app chrome when the app opted in, else None.

    Opt-in: ``PageContext.shell_menubar`` (stamped from ``menubar: true`` on
    the app block) or ``ctx.extra['menubar']``.
    """
    if not _feature_menubar_enabled(ctx):
        return None

    menus: list[MenubarMenu] = []
    model = getattr(ctx, "nav_model", None)
    if model is not None:
        menus = _menus_from_nav_model(model)
    if not menus:
        menus = _menus_from_legacy_nav(ctx)
    if not menus:
        menus = _fallback_app_menus(ctx)
    if not menus:
        return None
    # Cap menus so the topbar stays a strip, not a second sidebar.
    return Menubar(menus=tuple(menus[:6]), aria_label="App")
