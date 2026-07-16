"""Render dispatch — surface-to-fragment + page-chrome composition.

Two entry points:

- ``dispatch_render(surface, ctx, services)`` — looks up the registered
  renderer by ``surface.render`` and invokes its adapter to produce the
  inner-HTML for one surface. Used by ``back.runtime.page_routes`` when
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

from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any

from dazzle.core.condition_eval import evaluate_condition
from dazzle.core.renderer_registry import default_renderer_names
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
    from dazzle.render.context import CustomRenderCtx, PageContext


def dispatch_render(
    surface: SurfaceLike,
    *,
    ctx: dict[str, Any] | CustomRenderCtx,
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
            "See fixtures/custom_renderer/ for a worked example."
        )

    rendered = handler.render(surface, ctx)
    # #1392: custom renderers opt back into the framework's output guarantee.
    # The built-in `fragment` renderer is the trusted typed substrate; a custom
    # renderer (any name not in the framework defaults) bypasses it entirely, so
    # nothing previously stopped it returning a blank string — which ships as an
    # empty 200 (the AegisMark "passes render, blank screen" failure). The
    # framework now asserts non-blank, well-formed output on every custom-renderer
    # path. On by default; raises a typed FragmentError naming the renderer.
    if renderer_name not in default_renderer_names():
        return _assert_custom_render_output(rendered, surface.name, renderer_name)
    html: str = rendered  # framework `fragment` path: trusted typed substrate
    return html


class _OutputWellFormedProbe(HTMLParser):
    """Tolerant parse pass for the #1392 output guarantee.

    We only need the stdlib parser to *consume* the string without raising —
    that catches binary/garbled output, not HTML5 implicit-close nuances
    (unclosed ``<li>``/``<p>``, void ``<br>``/``<img>``, custom elements like
    ``<dz-onboarding-step>``), which are all valid and must never be flagged.
    """


def _assert_custom_render_output(html: object, surface_name: str, renderer_name: str) -> str:
    """Enforce the #1392 non-blank / well-formed guarantee for custom renderers.

    Returns the validated HTML unchanged, or raises :class:`FragmentError`
    naming the offending surface + renderer with a directed remediation.
    """
    if not isinstance(html, str):
        raise FragmentError(
            f"surface {surface_name!r}: custom renderer {renderer_name!r} returned "
            f"{type(html).__name__}, not an HTML string. A renderer's render() must "
            "return a non-empty HTML string (#1392 output guarantee)."
        )
    if not html.strip():
        raise FragmentError(
            f"surface {surface_name!r}: custom renderer {renderer_name!r} returned a "
            "blank string. A blank body renders as an empty 200 — return an explicit "
            "empty-state element instead of '' (#1392 output guarantee)."
        )
    try:
        probe = _OutputWellFormedProbe(convert_charrefs=True)
        probe.feed(html)
        probe.close()
    except Exception as exc:  # noqa: BLE001 — any parse failure is a guarantee breach
        raise FragmentError(
            f"surface {surface_name!r}: custom renderer {renderer_name!r} produced "
            f"output that is not parseable as HTML ({exc}). Return well-formed HTML "
            "(#1392 output guarantee)."
        ) from exc
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


def _sidebar_from_nav_model(model: Any, ctx: PageContext) -> Sidebar:
    """Translate a precomputed `NavModel` into a typed Sidebar primitive (#1324).

    Each `NavGroup` with a non-empty label becomes a collapsible fragment
    `NavGroup` (curated section). The auto-discover path emits a single group
    with `label == ""` (flat) — its links render as top-level `Sidebar.items`,
    not a titled group. Active state mirrors `current_route` against each
    link's route, matching the legacy `_build_sidebar_from_ctx` behaviour.
    """
    # #1324 FR-4: evaluate nav ``when`` conditions at render time. The NavModel
    # is precomputed at boot (tenant-independent), so visibility against the
    # request's roles + per-tenant config is resolved here. Build the eval
    # context once: strip the ``role_`` prefix from roles (matching
    # page_routes' role_ctx) and pass per-tenant config so ``tenant_config.<key>``
    # references resolve. Visibility only — route access (RBAC) is unchanged.
    eval_ctx = {
        "user_roles": [r.removeprefix("role_") for r in (getattr(ctx, "user_roles", None) or [])],
        "tenant_config": getattr(ctx, "tenant_config", {}) or {},
    }

    current = (getattr(ctx, "current_route", "") or "").rstrip("/")

    flat_items: list[NavItem] = []
    groups: list[NavGroup] = []
    for ng in model.groups:
        # Group-level ``when``: hide the whole group (header + links) if falsy.
        group_when = getattr(ng, "when", None)
        if group_when and not evaluate_condition(group_when, {}, eval_ctx):
            continue
        nav_items: list[NavItem] = []
        for link in ng.links:
            # Link-level ``when``: drop this link if it evaluates falsy.
            link_when = getattr(link, "when", None)
            if link_when and not evaluate_condition(link_when, {}, eval_ctx):
                continue
            href = _safe_url(getattr(link, "route", "") or "")
            if href is None:
                continue
            nav_items.append(
                NavItem(
                    label=getattr(link, "label", "") or "",
                    href=href,
                    active=(href.value.rstrip("/") == current),
                    icon=getattr(link, "icon", None) or "",
                )
            )
        if not nav_items:
            continue
        if (ng.label or "").strip():
            # Curated, titled group → collapsible NavGroup.
            groups.append(
                NavGroup(
                    label=ng.label,
                    items=tuple(nav_items),
                    icon=getattr(ng, "icon", None) or "",
                    collapsed=bool(getattr(ng, "collapsed", False)),
                )
            )
        else:
            # Flat (auto-discovered) group → top-level sidebar items.
            flat_items.extend(nav_items)

    app_name = (ctx.app_name or "Dazzle").strip()
    return Sidebar(
        items=tuple(flat_items),
        groups=tuple(groups),
        header=Text(app_name),
        show_sidebar_toggle=True,
    )


def _build_sidebar_from_ctx(ctx: PageContext) -> Sidebar:
    """Translate PageContext nav data into a typed Sidebar primitive.

    #1324 slice 3b: when the precomputed per-persona/anon `NavModel` is set on
    the context (`ctx.nav_model`), build the sidebar from it via
    `_sidebar_from_nav_model`. The legacy `nav_items`/`nav_groups` logic below
    stays as a fallback for any render path that hasn't set `nav_model` yet
    (its removal is a later task once every path sets nav_model).

    `nav_items` (flat) and `nav_groups` (collapsible) both flow through;
    the Sidebar header carries the app name. Active state mirrors
    `current_route` against each item's route.
    """
    model = getattr(ctx, "nav_model", None)
    if model is not None:
        return _sidebar_from_nav_model(model, ctx)

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
        show_sidebar_toggle=True,
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
    sidebar_state: str = "open",
) -> Page:
    """Build a fully-chromed Page — `Page → AppShell → Sidebar/Topbar
    + body` — from PageContext's nav data.

    `sidebar_state` ("open"/"closed", #1294) is emitted as
    `data-dz-sidebar` on the shell root so the sidebar nav renders
    on-screen (default "open"); callers thread the persisted
    `theme.get_sidebar_state()` cookie value. The topbar always gets a
    sidebar toggle so the nav is collapsible/reachable at all viewports.

    Use this for primary app surfaces (workspace pages, list/view/
    create/edit). For routes without an app shell (errors, auth),
    use `build_page` directly with `body=ErrorPage(...)` etc.
    """
    page_title = ctx.page_title.strip() if ctx.page_title else ""
    app_name = (ctx.app_name or "Dazzle").strip()
    title = f"{page_title} — {app_name}" if page_title else app_name
    sidebar = _build_sidebar_from_ctx(ctx)
    topbar = Topbar(title=app_name, show_sidebar_toggle=True)
    # Phase 4 app-shell migration (v0.67.44): thread the contract
    # `data-dazzle-view` / `data-dz-surface` / `data-dz-workspace`
    # attrs from PageContext into the typed AppShell so the same
    # E2E locators / agent observers / accessibility tooling that
    # ran against the legacy Jinja `layouts/app_shell.html` template
    # keep working without changes.
    # Command palette endpoint (tranche 2B): present whenever the app has a
    # sidebar (i.e. real navigation). app_prefix defaults to /app.
    app_prefix = getattr(ctx, "app_prefix", "") or "/app"
    command_endpoint = f"{app_prefix}/command" if sidebar is not None else ""
    body = AppShell(
        sidebar=sidebar,
        header=topbar,
        body=RawHTML(inner_html),
        view_name=getattr(ctx, "view_name", "") or "",
        surface_name=getattr(ctx, "surface_name", "") or "",
        workspace_name=getattr(ctx, "workspace_name", "") or "",
        page_purpose=getattr(ctx, "page_purpose", "") or "",
        sidebar_state=sidebar_state,
        command_endpoint=command_endpoint,
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
    sidebar_state: str = "open",
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

    # sidebar_state (#1294) only applies to the app-shell builder;
    # build_page (error/auth routes) has no sidebar. Kwargs are passed
    # explicitly per branch (not via a shared **dict) so the heterogeneous
    # param types stay checkable by mypy.
    if chrome:
        page: Page = build_app_chrome_page(
            ctx,
            inner_html,
            css_links=css_links,
            js_scripts=js_scripts,
            theme=theme,
            favicon=favicon,
            extra_meta=extra_meta,
            og_meta=og_meta,
            font_preconnect=font_preconnect,
            sidebar_state=sidebar_state,
        )
    else:
        page = build_page(
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
