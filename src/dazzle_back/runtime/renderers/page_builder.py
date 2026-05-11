"""PageContext → Page primitive adapter (Plan 17 P2).

The Fragment substrate ships a typed `Page` primitive that wraps an
HTML document. This module is the bridge from the runtime's
`PageContext` (carrying surface-level metadata + an already-rendered
inner HTML body) to a `Page` primitive ready for the Fragment renderer.

Asset URLs (css_links, js_scripts) and theme are intentionally passed
in by the caller as kwargs rather than scraped from PageContext — the
existing template path resolves them via dazzle.toml + asset bundle
detection at render time, and the caller (page_routes) already has
those resolutions in scope. Replicating that resolution logic here
would duplicate a moving target; passing in is honest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment import (
    URL,
    AppShell,
    NavGroup,
    NavItem,
    Page,
    Sidebar,
    Text,
    Topbar,
)
from dazzle.render.fragment.escape import RawHTML

if TYPE_CHECKING:
    from dazzle_ui.runtime.template_context import PageContext


def build_page(
    ctx: PageContext,
    inner_html: str,
    *,
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
    theme: str | None = None,
    favicon: str = "/static/assets/dazzle-favicon.svg",
    extra_meta: tuple[tuple[str, str], ...] = (),
    og_meta: tuple[tuple[str, str], ...] = (),
) -> Page:
    """Build a Page primitive from PageContext + already-rendered inner HTML.

    `inner_html` is the surface body the Fragment adapter produced —
    typically a `<section class="dz-surface">…</section>` block. This is
    wrapped in `RawHTML` so it composes into Page.body as a single Fragment
    leaf without re-escaping.

    Phase 4 (v0.67.42): the `og_meta` kwarg carries Open-Graph-style
    `<meta property="og:*">` tags. Twitter cards use `name="twitter:*"`
    so they continue to thread through `extra_meta`. Closes the parity
    gap that prevented chrome=on from being the default for marketing
    pages.
    """
    page_title = ctx.page_title.strip() if ctx.page_title else ""
    app_name = (ctx.app_name or "Dazzle").strip()
    title = f"{page_title} — {app_name}" if page_title else app_name
    return Page(
        title=title,
        body=RawHTML(inner_html),
        theme=theme,
        css_links=css_links,
        js_scripts=js_scripts,
        favicon=favicon,
        meta=extra_meta,
        og_meta=og_meta,
    )


def _safe_url(value: str) -> URL | None:
    """Construct a URL primitive defensively — bad/empty values return
    None instead of raising. Used for nav-item route translation where
    the runtime may produce odd values for synthetic surfaces."""
    try:
        return URL(value) if value else None
    except (ValueError, TypeError):
        return None


def _build_sidebar_from_ctx(ctx: PageContext) -> Sidebar:
    """Translate PageContext nav data into a typed Sidebar primitive.

    `nav_items` (flat) and `nav_groups` (collapsible) both flow through;
    the Sidebar header carries the app name. Active state mirrors
    `current_route` against each item's route.
    """
    current = (getattr(ctx, "current_route", "") or "").rstrip("/")

    flat_items: list[NavItem] = []
    for item in getattr(ctx, "nav_items", []) or []:
        href = _safe_url(getattr(item, "route", "") or "")
        if href is None:
            continue
        flat_items.append(
            NavItem(
                label=getattr(item, "label", "") or "",
                href=href,
                active=(href.value.rstrip("/") == current),
            )
        )

    groups: list[NavGroup] = []
    for raw_group in getattr(ctx, "nav_groups", []) or []:
        # Each entry is a dict {label, icon, collapsed, children}
        children = raw_group.get("children", []) if isinstance(raw_group, dict) else []
        group_items: list[NavItem] = []
        for child in children:
            child_route = (
                child.get("route", "") if isinstance(child, dict) else getattr(child, "route", "")
            )
            href = _safe_url(child_route or "")
            if href is None:
                continue
            child_label = (
                child.get("label", "") if isinstance(child, dict) else getattr(child, "label", "")
            )
            group_items.append(
                NavItem(
                    label=child_label or "",
                    href=href,
                    active=(href.value.rstrip("/") == current),
                )
            )
        if not group_items:
            continue  # NavGroup requires at least one item
        groups.append(
            NavGroup(
                label=(raw_group.get("label") if isinstance(raw_group, dict) else "") or "Group",
                items=tuple(group_items),
                collapsed=bool(
                    raw_group.get("collapsed") if isinstance(raw_group, dict) else False
                ),
            )
        )

    app_name = (ctx.app_name or "Dazzle").strip()
    return Sidebar(
        items=tuple(flat_items),
        groups=tuple(groups),
        header=Text(app_name),
    )


def build_app_chrome_page(
    ctx: PageContext,
    inner_html: str,
    *,
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
    theme: str | None = None,
    favicon: str = "/static/assets/dazzle-favicon.svg",
    extra_meta: tuple[tuple[str, str], ...] = (),
    og_meta: tuple[tuple[str, str], ...] = (),
) -> Page:
    """Build a fully-chromed Page — `Page → AppShell → Sidebar/Topbar
    + body` — from PageContext's nav data.

    Use this for primary app surfaces (workspace pages, list/view/
    create/edit). For routes without an app shell (errors, auth),
    use `build_page` directly with `body=ErrorPage(...)` etc.
    """
    page_title = ctx.page_title.strip() if ctx.page_title else ""
    app_name = (ctx.app_name or "Dazzle").strip()
    title = f"{page_title} — {app_name}" if page_title else app_name
    sidebar = _build_sidebar_from_ctx(ctx)
    topbar = Topbar(title=app_name)
    body = AppShell(
        sidebar=sidebar,
        header=topbar,
        body=RawHTML(inner_html),
    )
    return Page(
        title=title,
        body=body,
        theme=theme,
        css_links=css_links,
        js_scripts=js_scripts,
        favicon=favicon,
        meta=extra_meta,
        og_meta=og_meta,
    )


def dispatch_render_page(
    ctx: PageContext,
    inner_html: str,
    *,
    css_links: tuple[str, ...] = (),
    js_scripts: tuple[str, ...] = (),
    theme: str | None = None,
    favicon: str = "/static/assets/dazzle-favicon.svg",
    extra_meta: tuple[tuple[str, str], ...] = (),
    og_meta: tuple[tuple[str, str], ...] = (),
    chrome: bool = True,
) -> str:
    """Build a Page and render it to HTML — convenience wrapper.

    `chrome=True` (default) wraps `inner_html` in a full app chrome
    (Page → AppShell → Sidebar/Topbar + body). `chrome=False` wraps
    in a bare Page (Page → body) — use for error/auth routes that
    don't want navigation.

    Page chrome is a one-shot render (the document is structurally
    fixed); no need for renderer-registry indirection like surface
    bodies have. Direct construction + render is the fastest path.
    """
    from dazzle.render.fragment.renderer import FragmentRenderer

    builder = build_app_chrome_page if chrome else build_page
    page = builder(
        ctx,
        inner_html,
        css_links=css_links,
        js_scripts=js_scripts,
        theme=theme,
        favicon=favicon,
        extra_meta=extra_meta,
        og_meta=og_meta,
    )
    return FragmentRenderer().render(page)
