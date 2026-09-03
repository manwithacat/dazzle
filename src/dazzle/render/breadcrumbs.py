"""Breadcrumb trail derivation + HM Breadcrumb fragment bridge.

Pure render-layer helpers (no http/page imports). Path trails feed the
dual-lock ``Breadcrumb`` fragment mounted by app chrome.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dazzle.core.strings import entity_slug
from dazzle.render.fragment.primitives.navigation import Breadcrumb, BreadcrumbItem

if TYPE_CHECKING:
    from dazzle.render.context import PageContext

# PascalCase → clerk words (IssueReport → Issue Report). Digit/acronym
# boundaries keep IBGPolicy → IBG Policy.
_PASCAL_SPLIT = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_DOWNLOAD_UNSAFE = re.compile(r"[^A-Za-z0-9]+")
_LEFTOVER_PATH_TOKENS = frozenset({"zzz", "2abc", "1e2", "ghost"})


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


def clerk_entity_noun(
    name: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Clerk-facing entity noun for toast / fallback detail (oral #192).

    ``IssueReport was created`` dumped PascalCase while the DSL title is
    ``Issue Report``. Catalog hit uses the entity title (name, folded, or
    slug). Leftover junk invents no entity. Else PascalCase-split.
    """
    text = str(name or "").strip()
    if not text:
        return text
    folded = text.lower()
    if folded in _LEFTOVER_PATH_TOKENS:
        return text
    if catalog:
        hit = catalog.get(text) or catalog.get(folded) or catalog.get(entity_slug(text))
        if hit:
            return str(hit)
    parts = [p for p in _PASCAL_SPLIT.split(text) if p]
    return " ".join(parts) or text


def clerk_entity_confirm_noun(
    name: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Mid-sentence entity noun for hx-confirm (oral #194).

    ``Delete this issuereport?`` dumped concatenated slug while toast
    already says ``Issue Report was created``. Catalog / PascalCase-split
    via ``clerk_entity_noun``, then lower for mid-sentence English.
    Leftover junk invents no entity.
    """
    noun = clerk_entity_noun(name, catalog)
    text = str(noun or "").strip()
    if not text:
        return text
    if text.lower() in _LEFTOVER_PATH_TOKENS:
        return text
    return text.lower()


def clerk_entity_download_stem(
    name: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Filesystem stem for clerk downloads (oral #195).

    ``EngagementLetter-{uuid}.pdf`` dumped PascalCase while toast already
    says ``Engagement Letter was created``. Catalog / PascalCase-split via
    ``clerk_entity_noun``, then kebab-case. Leftover junk invents no entity.
    """
    noun = clerk_entity_noun(name, catalog)
    text = str(noun or "").strip()
    if not text:
        return text
    if text.lower() in _LEFTOVER_PATH_TOKENS:
        return text
    kebab = _DOWNLOAD_UNSAFE.sub("-", text).strip("-").lower()
    return kebab or text


def clerk_empty_collection_title(
    name: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Clerk-facing empty-list title (oral #213).

    ``No issuereports found`` dumped concatenated schema while toast already
    says ``Issue Report was created``. Catalog / PascalCase-split via
    ``clerk_entity_confirm_noun``, then the adapter's naive ``s`` plural.
    Leftover junk invents no collection.
    """
    noun = clerk_entity_confirm_noun(name, catalog)
    text = str(noun or "").strip()
    if not text:
        return "No items yet"
    if text.lower() in _LEFTOVER_PATH_TOKENS:
        return "No items yet"
    return f"No {text}s found"


def clerk_related_create_noun(
    name: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Singular entity noun for related-tab ``+ New`` CTAs (oral #214).

    ``+ New Task · Assigned To`` dumped the FK-disambiguated tab label
    while the list CTA already says ``New Task``. Catalog / PascalCase-split
    via ``clerk_entity_noun``. Leftover junk invents no entity.
    """
    noun = clerk_entity_noun(name, catalog)
    text = str(noun or "").strip()
    if not text or text.lower() in _LEFTOVER_PATH_TOKENS:
        return "item"
    return text


def clerk_entity_title(entity: Any) -> str:
    """Clerk-facing entity name: DSL ``title``, else PascalCase split."""
    title = str(getattr(entity, "title", None) or "").strip()
    if title:
        return title
    name = str(getattr(entity, "name", "") or "").strip()
    if not name:
        return ""
    return clerk_entity_noun(name)


def entity_path_labels_from_spec(appspec: Any) -> dict[str, str]:
    """Map ``entity_slug(name)`` → clerk title for breadcrumb path segments."""
    out: dict[str, str] = {}
    domain = getattr(appspec, "domain", None)
    entities = getattr(domain, "entities", None) or ()
    for ent in entities:
        name = str(getattr(ent, "name", "") or "").strip()
        if not name:
            continue
        label = clerk_entity_title(ent)
        slug = entity_slug(name)
        if slug and label:
            out[slug] = label
    return out


def clerk_entity_path_label(
    segment: str,
    catalog: dict[str, str] | None = None,
) -> str:
    """Clerk crumb for one path segment (oral #191).

    ``/app/issuereport`` dumped ``Issuereport`` while the DSL title is
    ``Issue Report``. Catalog hit uses the entity title. Leftover junk
    invents no entity. UUID / ``{id}`` stay copiable / readable.
    """
    text = str(segment or "").strip()
    if not text:
        return text
    if _looks_like_id_segment(text) or _has_unresolved_path_placeholder(text):
        return _default_segment_label(text)
    folded = text.lower()
    if folded in _LEFTOVER_PATH_TOKENS:
        return _default_segment_label(text)
    if catalog:
        hit = catalog.get(folded) or catalog.get(text)
        if hit:
            return str(hit)
    return _default_segment_label(text)


def build_breadcrumb_trail(
    path: str,
    label_overrides: dict[str, str] | None = None,
    entity_labels: dict[str, str] | None = None,
) -> list[Crumb]:
    """Build a breadcrumb trail from a URL path.

    Args:
        path: The current request path (e.g., ``/tasks/123/comments``).
        label_overrides: Optional mapping of path prefixes to display labels.
        entity_labels: Optional ``entity_slug`` → clerk title catalog
            (oral #191). Prefix overrides still win (surface page title).

    Returns:
        List of Crumb objects. The last crumb has ``url=None`` (current page)
        when the path has more than one segment after Home. Structural
        namespaces without an index page (e.g. ``/app/workspaces``) also
        emit ``url=None`` so agents do not hop into a 404. Unresolved
        ``{param}`` template segments never get an ``href`` (cycle 1952).
    """
    overrides = label_overrides or {}
    catalog = entity_labels or {}
    segments = [s for s in path.strip("/").split("/") if s]

    if not segments:
        return [Crumb(label="Home", url="/")]

    crumbs: list[Crumb] = [Crumb(label="Home", url="/")]
    multi = len(segments) > 1

    for i, segment in enumerate(segments):
        accumulated = "/" + "/".join(segments[: i + 1])
        label = overrides.get(accumulated)
        if label is None:
            label = clerk_entity_path_label(segment, catalog)
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
    catalog = dict(getattr(ctx, "entity_path_labels", None) or {})
    crumbs = build_breadcrumb_trail(route, overrides or None, entity_labels=catalog or None)
    if len(crumbs) == 1 and title and crumbs[0].label != title:
        crumbs = [crumbs[0], Crumb(label=title, url=None)]
    if not crumbs:
        return None
    return crumbs_to_breadcrumb(crumbs)
