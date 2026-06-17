"""Shell-family render mixin.

Houses the 12 shell primitives — outermost framing for full pages
(AppShell, Page, ErrorPage) plus the workspace-shell composite that
nests Sidebar / Topbar / Drawer / Toolbar / ContextSelector:

  - _emit_page
  - _emit_app_shell
  - _emit_error_page
  - _emit_skip_link
  - _emit_topbar
  - _emit_nav_item
  - _emit_nav_group
  - _emit_sidebar
  - _emit_workspace_context_selector
  - _emit_workspace_drawer
  - _emit_workspace_toolbar
  - _emit_workspace_shell

Also houses the 3 workspace HTML constants used by these methods:
`_WORKSPACE_DRAWER_HTML`, `_WORKSPACE_CONTEXT_SCRIPT_TEMPLATE`,
`_WORKSPACE_TOOLBAR_HTML`. The first two are re-exported from
`renderer/__init__.py` for the legacy packaging test.

All methods only call `self._emit(child, ctx)` (or cross-family
`self._emit_nav_item` / `_emit_nav_group` / `_emit_skip_link` —
all shell-internal). Dispatch goes back through the match block.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    AppShell,
    ErrorPage,
    NavGroup,
    NavItem,
    Page,
    Sidebar,
    SkipLink,
    Topbar,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspaceShell,
    WorkspaceToolbar,
)


def _load_static(name: str) -> str:
    """Read a literal HTML/JS asset bundled under
    `src/dazzle/render/fragment/static/`.

    Used by chrome primitives that emit large, fixed-shape blobs (the
    WorkspaceDrawer markup + IIFE, the context-selector script). Cached
    at module-import time — the file content is read once.

    Lived in `_emit.py` until #1064 PR 6; moved here alongside the
    workspace HTML constants that are its only callers.
    """
    from importlib.resources import files

    return (files("dazzle.render.fragment.static") / name).read_text(encoding="utf-8")


if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


# Workspace drawer — backdrop + aside + IIFE that wires `dzDrawer.open()` /
# `.close()` and the document-level htmx:after:settle defensive close
# (#934). Loaded from the static asset because the IIFE is ~120 lines
# of mixed HTML + JS with quote-density that's painful to inline as a
# Python f-string. Read once at module-import time, then cached.
_WORKSPACE_DRAWER_HTML = _load_static("workspace_drawer.html")

# Workspace context selector — `<script>` body with `{WS_NAME_JSON}` and
# `{OPTIONS_URL_JSON}` placeholders the renderer fills in via
# `json.dumps()`. Same loading pattern as the drawer.
_WORKSPACE_CONTEXT_SCRIPT_TEMPLATE = _load_static("workspace_context_script.html")


# Workspace toolbar — emitted byte-for-byte by `_emit_workspace_toolbar`
# (Phase 4B.5.b.2.i). Fixed shape: Reset button + Save button with
# five x-cloak+x-show saveState spans (clean/dirty/saving/saved/error).
# Spinner SVG (24×24) + checkmark SVG (20×20) are inlined verbatim
# from the legacy `_content.html` template.
_WORKSPACE_TOOLBAR_HTML = (
    '<div class="dz-workspace-toolbar">'
    '<div class="dz-workspace-toolbar-spacer"></div>'
    '<button @click="resetLayout()" class="dz-workspace-reset">Reset</button>'
    '<button @click="save()" '
    ":disabled=\"saveState === 'clean' || saveState === 'saving' || "
    "saveState === 'saved'\" "
    ':data-dz-save-state="saveState" '
    ":title=\"saveState === 'error' ? _saveError : ''\" "
    'class="dz-workspace-save">'
    "<span x-cloak x-show=\"saveState === 'clean'\">Saved</span>"
    "<span x-cloak x-show=\"saveState === 'dirty'\">Save layout</span>"
    "<span x-cloak x-show=\"saveState === 'saving'\" "
    'class="dz-workspace-save-busy">'
    '<svg class="dz-workspace-save-busy-icon" viewBox="0 0 24 24" fill="none">'
    '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" '
    'stroke-width="4"/>'
    '<path class="opacity-75" fill="currentColor" '
    'd="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>'
    "</svg>"
    "Saving"
    "</span>"
    "<span x-cloak x-show=\"saveState === 'saved'\" "
    'class="dz-workspace-save-busy">'
    '<svg class="dz-workspace-save-busy-icon" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" '
    'd="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 '
    '011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/>'
    "</svg>"
    "Saved"
    "</span>"
    "<span x-cloak x-show=\"saveState === 'error'\">Retry</span>"
    "</button>"
    "</div>"
)


class _RenderShellMixin:
    """Mixin adding the 12 shell-family `_emit_*` methods to
    `FragmentRenderer`. Same pattern as the other render mixins.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    def _emit_page(self, p: Page, ctx: RenderContext) -> str:
        """Emit `<!DOCTYPE html><html>...<head>...</head><body>...</body></html>`.

        Page chrome is intentionally rendered as a single string —
        unlike content primitives, the document outer is structurally
        fixed and not composable. Conditional asset/theme decisions
        belong in the PageBuilder (Phase 2), not in the renderer.
        """
        parts: list[str] = ["<!DOCTYPE html>"]
        # #1280: `data-theme` carries the user's colour-scheme preference
        # (`light` / `dark`) and is rewritten by `static/js/site.js` on
        # first paint; `data-theme-name` carries the project theme
        # identity (e.g. `stripe`) and is never rewritten. CSS theme
        # selectors that scope by identity must use
        # `[data-theme-name="<name>"]`; selectors that scope by colour
        # scheme continue to use `[data-theme="dark"]`. The two
        # attributes are emitted independently — `data-theme` defaults
        # to absent (JS resolves at paint time), `data-theme-name` is
        # only emitted when a project theme is configured.
        theme_name_attr = f' data-theme-name="{ctx.escape_attr(p.theme)}"' if p.theme else ""
        lang_attr = f' lang="{ctx.escape_attr(p.lang)}"'
        parts.append(f"<html{lang_attr}{theme_name_attr}>")

        # ── <head> ──
        parts.append("<head>")
        parts.append('<meta charset="UTF-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        for name, content in p.meta:
            parts.append(
                f'<meta name="{ctx.escape_attr(name)}" content="{ctx.escape_attr(content)}">'
            )
        for prop, content in p.og_meta:
            parts.append(
                f'<meta property="{ctx.escape_attr(prop)}" content="{ctx.escape_attr(content)}">'
            )
        parts.append(f"<title>{ctx.escape(p.title)}</title>")
        parts.append(f'<link rel="icon" href="{ctx.escape_attr(p.favicon)}" type="image/svg+xml">')
        # Font preconnects come before stylesheets so the browser can
        # open the TCP+TLS handshake while the rest of <head> parses.
        for origin in p.font_preconnect:
            parts.append(f'<link rel="preconnect" href="{ctx.escape_attr(origin)}" crossorigin>')
        parts.append(f"<style>@layer {ctx.escape(p.cascade_layer_order)};</style>")
        for css_url in p.css_links:
            parts.append(f'<link rel="stylesheet" href="{ctx.escape_attr(css_url)}">')
        for js_url in p.js_scripts:
            parts.append(f'<script defer src="{ctx.escape_attr(js_url)}"></script>')
        parts.append("</head>")

        # ── <body> ──
        parts.append('<body class="dz-page">')
        parts.append(self._emit(p.body, ctx))  # type: ignore[arg-type]
        if p.toast_container:
            parts.append('<div id="dz-toast" class="dz-toast-stack" aria-live="polite"></div>')
        if p.modal_slot:
            parts.append('<div id="dz-modal-slot"></div>')
        if p.page_announcer:
            parts.append(
                '<div id="dz-page-announcer" aria-live="assertive" '
                'aria-atomic="true" class="visually-hidden"></div>'
            )
        parts.append("</body>")
        parts.append("</html>")
        return "".join(parts)

    def _emit_app_shell(self, a: AppShell, ctx: RenderContext) -> str:
        """Emit the `dz-app-shell` layout — sidebar + content (header,
        main, footer). Mirrors the legacy `app_shell.html` structure
        so existing component CSS continues to apply.

        Slots are rendered as their primitive type dictates; the
        primitive itself is structural-only (no Alpine state, no theme
        switcher — those live inside the slot fragments the caller
        provides).

        A11y: AppShell auto-emits a SkipLink targeting its own
        `<main id="main-content">` so keyboard users have a stable
        bypass for the navigation. Set `skip_link_text=""` to disable
        (rare — almost always wrong).
        """
        # #1294 — emit the sidebar open/closed state on the shell root so
        # CSS slides the sidebar on-screen + offsets the content. Without
        # it the sidebar parks off-screen (translateX(-100%)) and the nav
        # is unreachable. Sanitised to the two valid values so a bad
        # primitive value can't inject arbitrary attribute content.
        sidebar_state = a.sidebar_state if a.sidebar_state in ("open", "closed") else "open"
        parts: list[str] = [f'<div class="dz-app-shell" data-dz-sidebar="{sidebar_state}">']
        if a.skip_link_text:
            # Emit via the SkipLink primitive's renderer so the markup
            # stays consistent if someone composes one explicitly
            # elsewhere. Hardcoded target — AppShell guarantees its
            # own #main-content id.
            parts.append(self._emit_skip_link(SkipLink(text=a.skip_link_text), ctx))
        if a.sidebar is not None:
            # id anchors the topbar toggle's aria-controls (#1294).
            parts.append(
                f'<aside class="dz-app-sidebar" id="dz-app-sidebar">{self._emit(a.sidebar, ctx)}</aside>'  # type: ignore[arg-type]
            )
        parts.append('<div class="dz-app-content">')
        if a.header is not None:
            parts.append(
                f'<header class="dz-app-header">{self._emit(a.header, ctx)}</header>'  # type: ignore[arg-type]
            )
        # Contract data-* attrs (Phase 4 app-shell migration, v0.67.44).
        # The legacy `layouts/app_shell.html` emitted these on the
        # `<main>` element; downstream tooling (E2E locators, agent
        # observers, accessibility scanners) reads them by name.
        main_attrs = ' class="dz-app-main" id="main-content"'
        if a.view_name:
            main_attrs += f' data-dazzle-view="{ctx.escape_attr(a.view_name)}"'
        if a.surface_name:
            main_attrs += f' data-dz-surface="{ctx.escape_attr(a.surface_name)}"'
        if a.workspace_name:
            main_attrs += f' data-dz-workspace="{ctx.escape_attr(a.workspace_name)}"'
        main_inner: list[str] = []
        if a.page_purpose:
            main_inner.append(
                f'<p class="dz-page-purpose" data-dazzle-purpose>{ctx.escape(a.page_purpose)}</p>'
            )
        main_inner.append(self._emit(a.body, ctx))  # type: ignore[arg-type]
        parts.append(f"<main{main_attrs}>{''.join(main_inner)}</main>")
        if a.footer is not None:
            parts.append(
                f'<footer class="dz-app-footer">{self._emit(a.footer, ctx)}</footer>'  # type: ignore[arg-type]
            )
        parts.append("</div>")
        parts.append("</div>")
        return "".join(parts)

    def _emit_error_page(self, e: ErrorPage, ctx: RenderContext) -> str:
        """Standalone error page — `<section>` with code + message +
        optional home link. Composes inside `Page.body` for routes
        that don't use AppShell (404, 500, auth pages)."""
        from dazzle.render.fragment.htmx import URL

        code = ctx.escape(str(e.code))
        message = ctx.escape(e.message)
        home_html = ""
        if isinstance(e.home_href, URL):
            href = ctx.escape_attr(e.home_href.value)
            label = ctx.escape(e.home_label)
            home_html = f'<a class="dz-error-page__action" href="{href}">{label}</a>'
        return (
            f'<section class="dz-error-page" data-dz-error-code="{ctx.escape_attr(str(e.code))}">'
            f'<h1 class="dz-error-page__code">{code}</h1>'
            f'<p class="dz-error-page__message">{message}</p>'
            f"{home_html}"
            f"</section>"
        )

    def _emit_skip_link(self, s: SkipLink, ctx: RenderContext) -> str:
        """A11y skip-link — `<a class="dz-skip-link">` matching the
        legacy `macros/a11y.html::skip_link` macro. CSS in
        `components/fragments.css` keeps it visually hidden until
        focused."""
        target = ctx.escape_attr(s.target)
        text = ctx.escape(s.text)
        return f'<a href="{target}" class="dz-skip-link">{text}</a>'

    def _emit_topbar(self, t: Topbar, ctx: RenderContext) -> str:
        """`<div class="dz-topbar">` with leading / title / trailing.

        All three sub-areas are emitted unconditionally so CSS layout
        (flexbox `space-between` etc.) has stable elements to lay out
        even when slots are empty. Empty slots emit empty containers,
        not absent ones."""
        leading_html = (
            self._emit(t.leading, ctx) if t.leading is not None else ""  # type: ignore[arg-type]
        )
        trailing_html = (
            self._emit(t.trailing, ctx) if t.trailing is not None else ""  # type: ignore[arg-type]
        )
        # #1294 — built-in sidebar toggle. Emitted at the start of the
        # leading area so the sidebar nav is reachable (and collapsible)
        # on every app-shell page. The JS controller (dz-alpine.js) wires
        # the click → flip `data-dz-sidebar` on `.dz-app-shell` + persist
        # the `dz_sidebar` cookie; aria-expanded is synced on load + click.
        toggle_html = ""
        if t.show_sidebar_toggle:
            toggle_html = (
                '<button type="button" class="dz-sidebar-toggle" '
                'data-dz-sidebar-toggle aria-controls="dz-app-sidebar" '
                'aria-expanded="true" aria-label="Toggle navigation">'
                '<span class="dz-sidebar-toggle__icon" aria-hidden="true"></span>'
                "</button>"
            )
        title_html = ""
        if t.title:
            title_html = f'<span class="dz-topbar-title-text">{ctx.escape(t.title)}</span>'
        return (
            f'<div class="dz-topbar">'
            f'<div class="dz-topbar-leading">{toggle_html}{leading_html}</div>'
            f'<div class="dz-topbar-title">{title_html}</div>'
            f'<div class="dz-topbar-trailing">{trailing_html}</div>'
            f"</div>"
        )

    def _emit_nav_item(self, n: NavItem, ctx: RenderContext) -> str:
        """`<li>` wrapping an `<a>` with `aria-current="page"` when active.
        Mirrors the legacy template's nav-link convention so existing
        `[aria-current="page"]` CSS keys off the same attribute."""
        href = ctx.escape_attr(n.href.value)
        label = ctx.escape(n.label)
        current_attr = ' aria-current="page"' if n.active else ""
        icon_html = ""
        if n.icon:
            icon_html = (
                f'<span class="dz-nav-link__icon" '
                f'data-dz-icon="{ctx.escape_attr(n.icon)}" '
                f'aria-hidden="true"></span>'
            )
        return (
            f'<li class="dz-nav-item">'
            f'<a class="dz-nav-link" href="{href}"{current_attr}>'
            f"{icon_html}"
            f'<span class="dz-nav-link__label">{label}</span>'
            f"</a></li>"
        )

    def _emit_nav_group(self, g: NavGroup, ctx: RenderContext) -> str:
        """Native `<details>` so collapsed/expanded works without JS."""
        label = ctx.escape(g.label)
        open_attr = "" if g.collapsed else " open"
        icon_html = ""
        if g.icon:
            icon_html = (
                f'<span class="dz-nav-group__icon" '
                f'data-dz-icon="{ctx.escape_attr(g.icon)}" '
                f'aria-hidden="true"></span>'
            )
        items_html = "".join(self._emit_nav_item(item, ctx) for item in g.items)
        return (
            f'<details class="dz-nav-group"{open_attr}>'
            f'<summary class="dz-nav-group__header">'
            f"{icon_html}"
            f'<span class="dz-nav-group__label">{label}</span>'
            f"</summary>"
            f'<ul class="dz-nav-group__items">{items_html}</ul>'
            f"</details>"
        )

    def _emit_sidebar(self, s: Sidebar, ctx: RenderContext) -> str:
        """`<nav class="dz-sidebar">` — header (free Fragment slot) +
        flat items (`<ul>`) + groups (`<details>` blocks)."""
        parts: list[str] = ['<nav class="dz-sidebar" aria-label="Primary">']
        if s.header is not None:
            parts.append(
                f'<div class="dz-sidebar__header">{self._emit(s.header, ctx)}</div>'  # type: ignore[arg-type]
            )
        if s.items:
            items_html = "".join(self._emit_nav_item(item, ctx) for item in s.items)
            parts.append(f'<ul class="dz-sidebar__items">{items_html}</ul>')
        for group in s.groups:
            parts.append(self._emit_nav_group(group, ctx))
        parts.append("</nav>")
        return "".join(parts)

    def _emit_workspace_context_selector(
        self, c: WorkspaceContextSelector, ctx: RenderContext
    ) -> str:
        """Render a WorkspaceContextSelector matching legacy `_content.html`
        context-selector block byte-for-byte (Phase 4B.5.b.3).

        Two parts: the `<div class="dz-workspace-context">` markup
        (label + select with default `All` option), and the IIFE that
        fetches the options, restores dzPrefs, and updates region
        hx-get URLs on change. The IIFE template carries `WS_NAME_JSON`
        and `OPTIONS_URL_JSON` placeholders that we fill via
        `json.dumps` to match legacy Jinja `tojson` behaviour."""
        from json import dumps as _json_dumps

        markup = (
            f'<div class="dz-workspace-context">'
            f'<label class="dz-workspace-context-label" for="dz-context-selector">'
            f"{ctx.escape(c.label)}:</label>"
            f'<select id="dz-context-selector" class="dz-workspace-context-select">'
            f'<option value="">All</option>'
            f"</select>"
            f"</div>"
        )
        script = _WORKSPACE_CONTEXT_SCRIPT_TEMPLATE.replace(
            "{WS_NAME_JSON}", _json_dumps(c.workspace_name)
        ).replace("{OPTIONS_URL_JSON}", _json_dumps(c.options_url))
        return markup + script

    def _emit_workspace_drawer(self, _d: WorkspaceDrawer, _ctx: RenderContext) -> str:
        """Render a WorkspaceDrawer matching legacy `_content.html`
        drawer block byte-for-byte (Phase 4B.5.b.3).

        Fixed-shape singleton — no parameters. Markup + IIFE loaded
        from the canonical static asset
        (`render/fragment/static/workspace_drawer.html`). The IIFE
        installs an init guard so the document-level listeners
        (`dz:drawerOpen`, body click delegation, escape keydown,
        htmx:after:settle defensive close) are registered exactly
        once across the session — the drawer markup gets re-emitted
        on every workspace nav swap, but the listeners are only added
        on the first emission."""
        return _WORKSPACE_DRAWER_HTML

    def _emit_workspace_toolbar(self, _t: WorkspaceToolbar, _ctx: RenderContext) -> str:
        """Render a WorkspaceToolbar matching legacy `_content.html`
        toolbar section byte-for-byte (Phase 4B.5.b.2.i).

        Fixed shape singleton — no parameters. The Alpine state machine
        (`saveState`, `resetLayout()`, `save()`, `_saveError`) is owned
        by the parent `dzDashboardBuilder()` x-data; this primitive
        emits the markup that binds to it.

        Five `x-cloak`+`x-show` spans cover the saveState states:
        clean / dirty / saving / saved / error. The two busy states
        (`saving`, `saved`) carry their own SVG icons (spinner +
        checkmark respectively)."""
        return _WORKSPACE_TOOLBAR_HTML

    def _emit_workspace_shell(self, w: WorkspaceShell, ctx: RenderContext) -> str:
        """Render a WorkspaceShell matching legacy `workspace/_content.html`
        outer wrapper + heading section byte-for-byte (Phase 4B.5.b.1).

        Emits:
          - `<div class="dz-workspace" x-data="dzDashboardBuilder()" ...>`
            with `data-workspace-name` (always) and optional
            `data-fold-count`.
          - `<div class="dz-workspace-heading">` carrying the title `<h2>`
            and an optional primary-actions row (each action is an
            `<a class="dz-workspace-action" hx-boost="true">` with a
            leading `+` SVG icon).
          - The body slot rendered after the heading; the closing
            `</div>` of the outer wrapper.

        4B.5.b.2 will fill the body slot with the slot grid; 4B.5.b.3
        will add the context selector + drawer + picker. Until those
        ships land, this primitive is consumed standalone for unit
        tests; the runtime workspace handler still uses the legacy
        Jinja path."""
        primary_actions_html = ""
        if w.primary_actions:
            actions_inner = "".join(
                f'<a href="{ctx.escape_attr(a.route)}" hx-boost="true" '
                f'class="dz-workspace-action">'
                f'<svg width="14" height="14" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" '
                f'stroke-width="2" d="M12 4v16m8-8H4"/>'
                f"</svg>"
                f"{ctx.escape(a.label)}"
                f"</a>"
                for a in w.primary_actions
            )
            primary_actions_html = (
                f'<div class="dz-workspace-primary-actions" '
                f'data-test-id="dz-workspace-primary-actions">'
                f"{actions_inner}"
                f"</div>"
            )

        fold_attr = f' data-fold-count="{w.fold_count}"' if w.fold_count is not None else ""
        body_html = self._emit(w.body, ctx)  # type: ignore[arg-type]

        return (
            f'<div class="dz-workspace" '
            f'x-data="dzDashboardBuilder()" '
            f'data-workspace-name="{ctx.escape_attr(w.workspace_name)}"'
            f"{fold_attr}>"
            f'<div class="dz-workspace-heading">'
            f'<h2 class="dz-workspace-title">{ctx.escape(w.title)}</h2>'
            f"{primary_actions_html}"
            f"</div>"
            f"{body_html}"
            f"</div>"
        )
