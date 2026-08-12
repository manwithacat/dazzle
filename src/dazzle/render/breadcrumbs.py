"""Breadcrumb trail derivation + HM Breadcrumb fragment bridge.

Pure render-layer helpers (no http/page imports). Path trails feed the
dual-lock ``Breadcrumb`` fragment mounted by app chrome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dazzle.render.fragment.primitives.navigation import Breadcrumb, BreadcrumbItem

if TYPE_CHECKING:
    from dazzle.render.context import PageContext


@dataclass(frozen=True, slots=True)
class Crumb:
    """A single breadcrumb entry."""

    label: str
    url: str | None = None


# Intermediate prefixes that are URL namespaces, not navigable pages.
# Linking them creates smoke-crawl / agent 404s (cycle 1826: bare
# ``/app/workspaces`` parent crumb on every workspace page).
_NON_PAGE_PATH_PREFIXES = frozenset(
    {
        "/app/workspaces",
    }
)


def _has_unresolved_path_placeholder(path: str) -> bool:
    """True when *path* still carries FastAPI-style ``{param}`` segments.

    Those are route templates, not real URLs — linking them 404s (cycle 1952).
    """
    return "{" in path and "}" in path


def _suppress_crumb_url(accumulated: str, *, is_last: bool, multi_segment: bool) -> bool:
    """True when this crumb must not be an ``<a href>``."""
    if is_last and multi_segment:
        return True
    norm = accumulated.rstrip("/") or "/"
    if norm in _NON_PAGE_PATH_PREFIXES:
        return True
    # Defense in depth: never emit a clickable unresolved template path.
    return _has_unresolved_path_placeholder(norm)


def _looks_like_id_segment(segment: str) -> bool:
    """UUID / long hex id — keep raw so crumbs stay copiable."""
    s = segment.strip()
    if len(s) < 8:
        return False
    # UUID (with or without hyphens) or long opaque id
    hexish = s.replace("-", "")
    if len(hexish) >= 16 and all(c in "0123456789abcdefABCDEF" for c in hexish):
        return True
    return False


def _default_segment_label(segment: str) -> str:
    """Humanize a path segment; leave brace placeholders / ids readable."""
    if _has_unresolved_path_placeholder(segment):
        # ``{id}`` → keep as ``id`` rather than title-casing to ``{Id}``
        inner = segment.strip("{}")
        return inner.replace("-", " ").replace("_", " ") or segment
    if _looks_like_id_segment(segment):
        return segment
    return segment.replace("-", " ").replace("_", " ").title()


def build_breadcrumb_trail(
    path: str,
    label_overrides: dict[str, str] | None = None,
) -> list[Crumb]:
    """Build a breadcrumb trail from a URL path.

    Args:
        path: The current request path (e.g., ``/tasks/123/comments``).
        label_overrides: Optional mapping of path prefixes to display labels.

    Returns:
        List of Crumb objects. The last crumb has ``url=None`` (current page)
        when the path has more than one segment after Home. Structural
        namespaces without an index page (e.g. ``/app/workspaces``) also
        emit ``url=None`` so agents do not hop into a 404. Unresolved
        ``{param}`` template segments never get an ``href`` (cycle 1952).
    """
    overrides = label_overrides or {}
    segments = [s for s in path.strip("/").split("/") if s]

    if not segments:
        return [Crumb(label="Home", url="/")]

    crumbs: list[Crumb] = [Crumb(label="Home", url="/")]
    multi = len(segments) > 1

    for i, segment in enumerate(segments):
        accumulated = "/" + "/".join(segments[: i + 1])
        label = overrides.get(accumulated, _default_segment_label(segment))
        is_last = i == len(segments) - 1
        suppress_url = _suppress_crumb_url(accumulated, is_last=is_last, multi_segment=multi)
        crumbs.append(Crumb(label=label, url=None if suppress_url else accumulated))

    return crumbs


def crumbs_to_breadcrumb(crumbs: list[Crumb] | tuple[Crumb, ...]) -> Breadcrumb:
    """Lift path crumbs into the HM ``Breadcrumb`` fragment."""
    items = tuple(BreadcrumbItem(label=c.label, href=c.url) for c in crumbs)
    return Breadcrumb(items=items)


def build_shell_breadcrumb(ctx: PageContext) -> Breadcrumb | None:
    """Shell trail for app chrome from ``PageContext.current_route`` + title.

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
    crumbs = build_breadcrumb_trail(route, overrides or None)
    if len(crumbs) == 1 and title and crumbs[0].label != title:
        crumbs = [crumbs[0], Crumb(label=title, url=None)]
    if not crumbs:
        return None
    return crumbs_to_breadcrumb(crumbs)
