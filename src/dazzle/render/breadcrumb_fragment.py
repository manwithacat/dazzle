"""Bridge URL breadcrumb trails into the typed Fragment app chrome."""

from __future__ import annotations

from dazzle.render.breadcrumbs import Crumb, build_breadcrumb_trail
from dazzle.render.context import BreadcrumbCrumbContext, PageContext
from dazzle.render.fragment.primitives.navigation import Breadcrumb, BreadcrumbItem


def crumbs_to_breadcrumb(crumbs: list[Crumb] | tuple[Crumb, ...]) -> Breadcrumb:
    """Lift path crumbs into the HM ``Breadcrumb`` fragment."""
    items = tuple(BreadcrumbItem(label=c.label, href=c.url) for c in crumbs)
    return Breadcrumb(items=items)


def _authored_breadcrumb(trail: list[BreadcrumbCrumbContext]) -> Breadcrumb | None:
    """``ux: breadcrumb:`` replaces the URL trail (#1810); ``off`` (empty) hides it.

    The last crumb is the current page and never links. Crumbs whose label
    rendered empty (a null interpolation) are dropped.
    """
    crumbs = [c for c in trail if c.label.strip()]
    if not crumbs:
        return None
    last = len(crumbs) - 1
    return crumbs_to_breadcrumb(
        [Crumb(label=c.label, url=None if i == last else c.url) for i, c in enumerate(crumbs)]
    )


def build_shell_breadcrumb(ctx: PageContext) -> Breadcrumb | None:
    """Shell trail for app chrome: the surface's authored ``ux: breadcrumb:``
    (#1810) when it declares one, else derived from the URL + page title."""
    authored = getattr(ctx, "breadcrumb_trail", None)
    if authored is not None:
        return _authored_breadcrumb(authored)
    return _url_breadcrumb(ctx)


def _url_breadcrumb(ctx: PageContext) -> Breadcrumb | None:
    """Shell trail from ``PageContext.current_route`` + title.

    Returns ``None`` only when there is nothing useful to show (no route and
    no page title). Chromed app pages almost always get at least Home + leaf.
    """
    route = (getattr(ctx, "current_route", None) or "/").strip() or "/"
    title = (getattr(ctx, "page_title", None) or "").strip()
    overrides: dict[str, str] = {}
    if title and route not in ("/", ""):
        overrides[route.rstrip("/") or route] = title
        if route.endswith("/"):
            overrides[route] = title
    catalog = dict(getattr(ctx, "entity_path_labels", None) or {})
    crumbs = build_breadcrumb_trail(route, overrides or None, entity_labels=catalog or None)
    if len(crumbs) == 1 and title and crumbs[0].label != title:
        crumbs = [crumbs[0], Crumb(label=title, url=None)]
    if not crumbs:
        return None
    return crumbs_to_breadcrumb(crumbs)
