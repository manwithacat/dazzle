"""Render dispatch — surface-to-fragment + page-chrome composition.

Two entry points:

- ``dispatch_render(surface, ctx, services)`` — looks up the registered
  renderer by ``surface.render`` and invokes its adapter to produce the
  inner-HTML for one surface. Used by ``ui.runtime.page_routes`` when
  building a workspace page.

- ``dispatch_render_page(ctx, inner_html, ...)`` — wraps an already-
  rendered inner-HTML body in a typed ``Page`` (optionally chromed with
  ``AppShell`` + ``Sidebar`` + ``Topbar``) and renders the document.

Both functions live in ``dazzle.render`` — neutral ground between
``back/`` (renderer registry + RuntimeServices) and ``ui/`` (page
routes). Moved here in #1094 (parent #1086) to break the back↔ui
import cycle that previously required a callable-injection shim
(see the `#679` workaround).

Asset URLs (css_links, js_scripts) and theme are intentionally passed
in by the caller as kwargs rather than scraped from PageContext — the
existing template path resolves them via dazzle.toml + asset bundle
detection at render time, and the caller (page_routes) already has
those resolutions in scope. Replicating that resolution logic here
would duplicate a moving target; passing in is honest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import RawHTML

if TYPE_CHECKING:
    from dazzle.core.ir.protocols import SurfaceLike
    from dazzle.render.context import PageContext


def dispatch_render(
    surface: SurfaceLike,
    *,
    ctx: dict[str, Any],
    services: Any,
) -> str:
    """Render ``surface`` using the renderer named by ``surface.render``,
    or ``"fragment"`` if unset. Returns the HTML string.

    ``services`` is a ``RuntimeServices`` instance; typed as ``Any``
    here to avoid the back→render dependency arrow (#1086 layer
    contract). Only the ``renderer_registry.resolve`` /
    ``registered_names`` duck-typed contract is used.

    Raises FragmentError if the named renderer is not registered.
    """
    renderer_name = surface.render or "fragment"
    handler = services.renderer_registry.resolve(renderer_name)
    if handler is None:
        # Mirror the link-time error from `linker._unknown_renderer_message`
        # so an agent encountering either site sees the same two-step
        # remediation recipe (#1117). The link-time error fires before
        # this one in normal boot; this site catches the case where the
        # DSL was accepted (the name is in `[renderers] extra`) but no
        # runtime handler was registered for it.
        registered = sorted(services.renderer_registry.registered_names())
        raise FragmentError(
            f"surface {surface.name!r}: renderer {renderer_name!r} is "
            f"declared in the DSL but no runtime handler is registered "
            f"for that name (registered: {registered}).\n\n"
            "Register a handler at runtime in your app factory or a "
            "startup hook:\n"
            "  services.renderer_registry.register(\n"
            f"      name={renderer_name!r}, handler=MyRendererClass()\n"
            "  )\n\n"
            "See examples/custom_renderer/ for a worked example."
        )

    html: str = handler.render(surface, ctx)
    return html


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
    font_preconnect: tuple[str, ...] = (),
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
        font_preconnect=font_preconnect,
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
    font_preconnect: tuple[str, ...] = (),
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
    # Phase 4 app-shell migration (v0.67.44): thread the contract
    # `data-dazzle-view` / `data-dz-surface` / `data-dz-workspace`
    # attrs from PageContext into the typed AppShell so the same
    # E2E locators / agent observers / accessibility tooling that
    # ran against the legacy Jinja `layouts/app_shell.html` template
    # keep working without changes.
    body = AppShell(
        sidebar=sidebar,
        header=topbar,
        body=RawHTML(inner_html),
        view_name=getattr(ctx, "view_name", "") or "",
        surface_name=getattr(ctx, "surface_name", "") or "",
        workspace_name=getattr(ctx, "workspace_name", "") or "",
        page_purpose=getattr(ctx, "page_purpose", "") or "",
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
        font_preconnect=font_preconnect,
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
    font_preconnect: tuple[str, ...] = (),
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
        font_preconnect=font_preconnect,
    )
    return FragmentRenderer().render(page)
