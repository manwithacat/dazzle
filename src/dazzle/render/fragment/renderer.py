"""FragmentRenderer — emits HTML from Fragment trees.

Single-class renderer. The `render` method match-dispatches on the Fragment
union; per-primitive emit methods produce HTML strings. The match block is
the runtime exhaustiveness check — adding a new primitive without adding a
match arm causes mypy to flag the unreachable case (with `--strict`) and
the test_fragment_exhaustiveness test to fail.
"""

from html import escape as _escape

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives import (
    KPI,
    ActionCard,
    AppShell,
    Badge,
    BarChart,
    BoxPlot,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    Diagram,
    Drawer,
    EmptyState,
    ErrorPage,
    Field,
    FormStack,
    Fragment,
    Grid,
    Heading,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    Link,
    MetricTile,
    Modal,
    NavGroup,
    NavItem,
    Page,
    PivotTable,
    ProfileCard,
    Radar,
    RefPicker,
    Region,
    Row,
    Sidebar,
    Skeleton,
    SkipLink,
    Split,
    Stack,
    Submit,
    Surface,
    Table,
    Tabs,
    Text,
    Timeline,
    TimeSeries,
    Toolbar,
    Topbar,
)


class FragmentRenderer:
    """Emit HTML from a Fragment tree.

    Stateless — a single instance can be reused across requests. The
    RenderContext is per-render-call and threads tokens through descent.
    """

    def render(self, fragment: Fragment, ctx: RenderContext | None = None) -> str:
        ctx = ctx if ctx is not None else RenderContext()
        return self._emit(fragment, ctx)

    def _emit(self, fragment: Fragment, ctx: RenderContext) -> str:
        match fragment:
            # Escape hatches first — most likely path is RawHTML interop
            case RawHTML(html=html):
                return html
            case Slot(name=name):
                raise FragmentError(
                    f"unfilled slot {name!r} reached the renderer; "
                    f"slots must be substituted before render() is called"
                )
            # Content
            case Text():
                return self._emit_text(fragment, ctx)
            case Heading():
                return self._emit_heading(fragment, ctx)
            # Layout
            case Stack():
                return self._emit_stack(fragment, ctx)
            case Row():
                return self._emit_row(fragment, ctx)
            case Split():
                return self._emit_split(fragment, ctx)
            case Grid():
                return self._emit_grid(fragment, ctx)
            # Containers
            case Page():
                return self._emit_page(fragment, ctx)
            case AppShell():
                return self._emit_app_shell(fragment, ctx)
            case Surface():
                return self._emit_surface(fragment, ctx)
            case Card():
                return self._emit_card(fragment, ctx)
            case Region():
                return self._emit_region(fragment, ctx)
            case Drawer():
                return self._emit_drawer(fragment, ctx)
            case Modal():
                return self._emit_modal(fragment, ctx)
            case Tabs():
                return self._emit_tabs(fragment, ctx)
            case ErrorPage():
                return self._emit_error_page(fragment, ctx)
            # Navigation
            case Sidebar():
                return self._emit_sidebar(fragment, ctx)
            case Topbar():
                return self._emit_topbar(fragment, ctx)
            case NavGroup():
                return self._emit_nav_group(fragment, ctx)
            case NavItem():
                return self._emit_nav_item(fragment, ctx)
            case SkipLink():
                return self._emit_skip_link(fragment, ctx)
            # Content
            case Icon():
                return self._emit_icon(fragment, ctx)
            case Badge():
                return self._emit_badge(fragment, ctx)
            case EmptyState():
                return self._emit_empty_state(fragment, ctx)
            case Skeleton():
                return self._emit_skeleton(fragment, ctx)
            # Interactive
            case Button():
                return self._emit_button(fragment, ctx)
            case Link():
                return self._emit_link(fragment, ctx)
            case Interactive():
                return self._emit_interactive(fragment, ctx)
            case InlineEdit():
                return self._emit_inline_edit(fragment, ctx)
            case Toolbar():
                return self._emit_toolbar(fragment, ctx)
            # Data
            case Table():
                return self._emit_table(fragment, ctx)
            case KPI():
                return self._emit_kpi(fragment, ctx)
            case BarChart():
                return self._emit_bar_chart(fragment, ctx)
            case PivotTable():
                return self._emit_pivot_table(fragment, ctx)
            case Timeline():
                return self._emit_timeline(fragment, ctx)
            case KanbanBoard():
                return self._emit_kanban_board(fragment, ctx)
            case CalendarGrid():
                return self._emit_calendar_grid(fragment, ctx)
            case Diagram():
                return self._emit_diagram(fragment, ctx)
            case TimeSeries():
                return self._emit_time_series(fragment, ctx)
            case Radar():
                return self._emit_radar(fragment, ctx)
            case BoxPlot():
                return self._emit_box_plot(fragment, ctx)
            case ActionCard():
                return self._emit_action_card(fragment, ctx)
            case ProfileCard():
                return self._emit_profile_card(fragment, ctx)
            case MetricTile():
                return self._emit_metric_tile(fragment, ctx)
            # Forms
            case FormStack():
                return self._emit_form_stack(fragment, ctx)
            case Field():
                return self._emit_field(fragment, ctx)
            case Combobox():
                return self._emit_combobox(fragment, ctx)
            case RefPicker():
                return self._emit_ref_picker(fragment, ctx)
            case Submit():
                return self._emit_submit(fragment, ctx)
            # Defensive fallback — exhaustiveness is verified by
            # test_fragment_exhaustiveness via property tests.
            case _:
                raise FragmentError(
                    f"renderer has no emit for {type(fragment).__name__!r} yet — "
                    f"add a match arm in FragmentRenderer._emit"
                )

    # --- per-primitive emitters ---

    def _emit_text(self, t: Text, ctx: RenderContext) -> str:
        body = ctx.escape(t.body)
        cls = f"dz-text dz-text--tone-{t.tone}"
        return f'<span class="{cls}">{body}</span>'

    def _emit_heading(self, h: Heading, ctx: RenderContext) -> str:
        body = ctx.escape(h.body)
        cls = f"dz-heading dz-heading--level-{h.level}"
        return f'<h{h.level} class="{cls}">{body}</h{h.level}>'

    def _emit_stack(self, s: Stack, ctx: RenderContext) -> str:
        cls = f"dz-stack dz-stack--gap-{s.gap}"
        body = "".join(self._emit(c, ctx) for c in s.children)  # type: ignore[arg-type]
        return f'<div class="{cls}">{body}</div>'

    def _emit_row(self, r: Row, ctx: RenderContext) -> str:
        cls = f"dz-row dz-row--gap-{r.gap} dz-row--align-{r.align}"
        body = "".join(self._emit(c, ctx) for c in r.children)  # type: ignore[arg-type]
        return f'<div class="{cls}">{body}</div>'

    def _emit_split(self, s: Split, ctx: RenderContext) -> str:
        # The colon in ratio strings is invalid in CSS class names; replace
        # with underscore. Both renderers (here and Jinja) must use the same
        # convention — see classes.py for the shared rule once we move it.
        ratio_class = s.ratio.replace(":", "_")
        cls = f"dz-split dz-split--ratio-{ratio_class}"
        start_html = self._emit(s.start, ctx)  # type: ignore[arg-type]
        end_html = self._emit(s.end, ctx)  # type: ignore[arg-type]
        return (
            f'<div class="{cls}">'
            f'<div class="dz-split__start">{start_html}</div>'
            f'<div class="dz-split__end">{end_html}</div>'
            f"</div>"
        )

    def _emit_grid(self, g: Grid, ctx: RenderContext) -> str:
        cls = f"dz-grid dz-grid--columns-{g.columns}"
        body = "".join(self._emit(c, ctx) for c in g.children)  # type: ignore[arg-type]
        return f'<div class="{cls}">{body}</div>'

    def _emit_card(self, c: Card, ctx: RenderContext) -> str:
        tokens = c.tokens if c.tokens is not None else ctx.tokens.card
        cls_parts = [
            "dz-card",
            f"dz-card--radius-{tokens.radius}",
            f"dz-card--border-{tokens.border}",
            f"dz-card--padding-{tokens.padding}",
            f"dz-card--shadow-{tokens.shadow}",
        ]
        cls = " ".join(cls_parts)
        parts = [f'<div class="{cls}">']
        if c.header is not None:
            parts.append(
                f'<div class="dz-card__header">{self._emit(c.header, ctx)}</div>'  # type: ignore[arg-type]
            )
        parts.append(
            f'<div class="dz-card__body">{self._emit(c.body, ctx)}</div>'  # type: ignore[arg-type]
        )
        if c.footer is not None:
            parts.append(
                f'<div class="dz-card__footer">{self._emit(c.footer, ctx)}</div>'  # type: ignore[arg-type]
            )
        parts.append("</div>")
        return "".join(parts)

    def _emit_page(self, p: Page, ctx: RenderContext) -> str:
        """Emit `<!DOCTYPE html><html>...<head>...</head><body>...</body></html>`.

        Page chrome is intentionally rendered as a single string —
        unlike content primitives, the document outer is structurally
        fixed and not composable. Conditional asset/theme decisions
        belong in the PageBuilder (Phase 2), not in the renderer.
        """
        parts: list[str] = ["<!DOCTYPE html>"]
        theme_attr = f' data-theme="{ctx.escape_attr(p.theme)}"' if p.theme else ""
        lang_attr = f' lang="{ctx.escape_attr(p.lang)}"'
        parts.append(f"<html{lang_attr}{theme_attr}>")

        # ── <head> ──
        parts.append("<head>")
        parts.append('<meta charset="UTF-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        for name, content in p.meta:
            parts.append(
                f'<meta name="{ctx.escape_attr(name)}" content="{ctx.escape_attr(content)}">'
            )
        parts.append(f"<title>{ctx.escape(p.title)}</title>")
        parts.append(f'<link rel="icon" href="{ctx.escape_attr(p.favicon)}" type="image/svg+xml">')
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
        parts: list[str] = ['<div class="dz-app-shell">']
        if a.skip_link_text:
            # Emit via the SkipLink primitive's renderer so the markup
            # stays consistent if someone composes one explicitly
            # elsewhere. Hardcoded target — AppShell guarantees its
            # own #main-content id.
            parts.append(self._emit_skip_link(SkipLink(text=a.skip_link_text), ctx))
        if a.sidebar is not None:
            parts.append(
                f'<aside class="dz-app-sidebar">{self._emit(a.sidebar, ctx)}</aside>'  # type: ignore[arg-type]
            )
        parts.append('<div class="dz-app-content">')
        if a.header is not None:
            parts.append(
                f'<header class="dz-app-header">{self._emit(a.header, ctx)}</header>'  # type: ignore[arg-type]
            )
        parts.append(
            f'<main class="dz-app-main" id="main-content">{self._emit(a.body, ctx)}</main>'  # type: ignore[arg-type]
        )
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
        title_html = ""
        if t.title:
            title_html = f'<span class="dz-topbar-title-text">{ctx.escape(t.title)}</span>'
        return (
            f'<div class="dz-topbar">'
            f'<div class="dz-topbar-leading">{leading_html}</div>'
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

    def _emit_surface(self, s: Surface, ctx: RenderContext) -> str:
        parts = ['<section class="dz-surface">']
        if s.header is not None:
            parts.append(
                f'<header class="dz-surface__header">{self._emit(s.header, ctx)}</header>'  # type: ignore[arg-type]
            )
        parts.append(
            f'<div class="dz-surface__body">{self._emit(s.body, ctx)}</div>'  # type: ignore[arg-type]
        )
        if s.footer is not None:
            parts.append(
                f'<footer class="dz-surface__footer">{self._emit(s.footer, ctx)}</footer>'  # type: ignore[arg-type]
            )
        parts.append("</section>")
        return "".join(parts)

    def _emit_region(self, r: Region, ctx: RenderContext) -> str:
        cls = f"dz-region dz-region--kind-{r.kind}"
        data_attr = f' data-dazzle-table="{ctx.escape_attr(r.data_table)}"' if r.data_table else ""
        body_html = self._emit(r.body, ctx)  # type: ignore[arg-type]
        return f'<section class="{cls}"{data_attr}>{body_html}</section>'

    def _emit_drawer(self, d: Drawer, ctx: RenderContext) -> str:
        cls = f"dz-drawer dz-drawer--side-{d.side}"
        return f'<aside class="{cls}">{self._emit(d.body, ctx)}</aside>'  # type: ignore[arg-type]

    def _emit_modal(self, m: Modal, ctx: RenderContext) -> str:
        cls = f"dz-modal dz-modal--size-{m.size}"
        return f'<div class="{cls}" role="dialog">{self._emit(m.body, ctx)}</div>'  # type: ignore[arg-type]

    def _emit_tabs(self, t: Tabs, ctx: RenderContext) -> str:
        tab_buttons = "".join(
            f'<button class="dz-tabs__button" data-tab="{ctx.escape_attr(key)}">'
            f"{ctx.escape(key)}</button>"
            for key, _panel in t.tabs
        )
        panels = "".join(
            f'<div class="dz-tabs__panel" data-tab="{ctx.escape_attr(key)}">'
            f"{self._emit(panel, ctx)}</div>"  # type: ignore[arg-type]
            for key, panel in t.tabs
        )
        return (
            f'<div class="dz-tabs"><div class="dz-tabs__buttons">{tab_buttons}</div>{panels}</div>'
        )

    def _emit_icon(self, i: Icon, ctx: RenderContext) -> str:
        name = ctx.escape_attr(i.name)
        cls = f"dz-icon dz-icon--size-{i.size}"
        return f'<span class="{cls}" data-icon="{name}" aria-hidden="true"></span>'

    def _emit_badge(self, b: Badge, ctx: RenderContext) -> str:
        cls = f"dz-badge dz-badge--variant-{b.variant}"
        return f'<span class="{cls}">{ctx.escape(b.label)}</span>'

    def _emit_empty_state(self, e: EmptyState, ctx: RenderContext) -> str:
        action_html = self._emit(e.action, ctx) if e.action is not None else ""  # type: ignore[arg-type]
        return (
            f'<div class="dz-empty-state">'
            f'<h3 class="dz-empty-state__title">{ctx.escape(e.title)}</h3>'
            f'<p class="dz-empty-state__description">{ctx.escape(e.description)}</p>'
            f'<div class="dz-empty-state__action">{action_html}</div>'
            f"</div>"
        )

    def _emit_skeleton(self, s: Skeleton, ctx: RenderContext) -> str:
        lines = "".join('<div class="dz-skeleton__line"></div>' for _ in range(s.lines))
        return f'<div class="dz-skeleton">{lines}</div>'

    @staticmethod
    def _hx_attrs(
        *,
        hx_get: object,
        hx_post: object,
        hx_target: object,
        hx_swap: object | None,
        hx_trigger: object | None = None,
        hx_indicator: object | None = None,
        hx_confirm: object | None = None,
    ) -> str:
        """Build the htmx attribute string for an interactive primitive.

        All values are escaped for attribute context. Wrapper types (URL,
        TargetSelector, HxTrigger) are validated at construction; this
        escape pass converts characters like `&` in query strings to their
        HTML entity form so the output is valid HTML5."""
        parts: list[str] = []
        if hx_get is not None:
            parts.append(f'hx-get="{_escape(str(hx_get), quote=True)}"')
        if hx_post is not None:
            parts.append(f'hx-post="{_escape(str(hx_post), quote=True)}"')
        if hx_target is not None:
            parts.append(f'hx-target="{_escape(str(hx_target), quote=True)}"')
        if hx_swap is not None:
            parts.append(f'hx-swap="{_escape(str(hx_swap), quote=True)}"')
        if hx_trigger is not None:
            parts.append(f'hx-trigger="{_escape(str(hx_trigger), quote=True)}"')
        if hx_indicator is not None:
            parts.append(f'hx-indicator="{_escape(str(hx_indicator), quote=True)}"')
        if hx_confirm is not None:
            parts.append(f'hx-confirm="{_escape(str(hx_confirm), quote=True)}"')
        return " ".join(parts)

    def _emit_button(self, b: Button, ctx: RenderContext) -> str:
        tokens = b.tokens if b.tokens is not None else ctx.tokens.button
        cls_parts = [
            "dz-button",
            f"dz-button--variant-{b.variant}",
            f"dz-button--size-{tokens.size}",
            f"dz-button--visibility-{b.visibility}",
        ]
        cls = " ".join(cls_parts)
        attrs = self._hx_attrs(
            hx_get=b.hx_get,
            hx_post=b.hx_post,
            hx_target=b.hx_target,
            hx_swap=b.hx_swap,
            hx_trigger=b.hx_trigger,
            hx_indicator=b.hx_indicator,
            hx_confirm=b.hx_confirm,
        )
        attr_str = f" {attrs}" if attrs else ""
        disabled = ' disabled="disabled"' if b.visibility == "disabled" else ""
        label = ctx.escape(b.label)
        return f'<button type="button" class="{cls}"{attr_str}{disabled}>{label}</button>'

    def _emit_link(self, link: Link, ctx: RenderContext) -> str:
        href = ctx.escape_attr(str(link.href))
        return f'<a class="dz-link" href="{href}">{ctx.escape(link.label)}</a>'

    def _emit_interactive(self, iw: Interactive, ctx: RenderContext) -> str:
        attrs = self._hx_attrs(
            hx_get=iw.hx_get,
            hx_post=iw.hx_post,
            hx_target=iw.hx_target,
            hx_swap=iw.hx_swap,
            hx_trigger=iw.hx_trigger,
        )
        attr_str = f" {attrs}" if attrs else ""
        child_html = self._emit(iw.child, ctx)  # type: ignore[arg-type]
        return f'<div class="dz-interactive"{attr_str}>{child_html}</div>'

    def _emit_inline_edit(self, ie: InlineEdit, ctx: RenderContext) -> str:
        # InlineEdit value should be escaped — it's user-supplied content.
        # The placeholder is developer-supplied but escape anyway as a safety net.
        value = ctx.escape(ie.value)
        placeholder = ctx.escape_attr(ie.placeholder)
        return (
            f'<span class="dz-inline-edit" data-field="{ctx.escape_attr(ie.field_name)}" '
            f'data-placeholder="{placeholder}">{value}</span>'
        )

    def _emit_toolbar(self, t: Toolbar, ctx: RenderContext) -> str:
        actions_html = "".join(self._emit(a, ctx) for a in t.actions)  # type: ignore[arg-type]
        label = ctx.escape_attr(t.label)
        return f'<div class="dz-toolbar" aria-label="{label}">{actions_html}</div>'

    def _emit_table(self, t: Table, ctx: RenderContext) -> str:
        head_cells = "".join(f"<th>{ctx.escape(c)}</th>" for c in t.columns)
        body_rows = "".join(
            "<tr>" + "".join(f"<td>{ctx.escape(cell)}</td>" for cell in row) + "</tr>"
            for row in t.rows
        )
        return (
            f'<table class="dz-table">'
            f"<thead><tr>{head_cells}</tr></thead>"
            f"<tbody>{body_rows}</tbody>"
            f"</table>"
        )

    def _emit_kpi(self, k: KPI, ctx: RenderContext) -> str:
        cls = f"dz-kpi dz-kpi--trend-{k.trend}"
        delta_html = f'<span class="dz-kpi__delta">{ctx.escape(k.delta)}</span>' if k.delta else ""
        return (
            f'<div class="{cls}">'
            f'<div class="dz-kpi__label">{ctx.escape(k.label)}</div>'
            f'<div class="dz-kpi__value">{ctx.escape(k.value)}</div>'
            f"{delta_html}"
            f"</div>"
        )

    def _emit_bar_chart(self, b: BarChart, ctx: RenderContext) -> str:
        bars = "".join(
            f'<div class="dz-bar-chart__bar" data-label="{ctx.escape_attr(label)}">'
            f'<span class="dz-bar-chart__label">{ctx.escape(label)}</span>'
            f'<span class="dz-bar-chart__value">{count}</span>'
            f"</div>"
            for label, count in b.buckets
        )
        return (
            f'<div class="dz-bar-chart">'
            f'<div class="dz-bar-chart__title">{ctx.escape(b.label)}</div>'
            f'<div class="dz-bar-chart__bars">{bars}</div>'
            f"</div>"
        )

    def _emit_pivot_table(self, p: PivotTable, ctx: RenderContext) -> str:
        head = "".join(f"<th>{ctx.escape(c)}</th>" for c in p.columns)
        body = "".join(
            "<tr>"
            + f"<th>{ctx.escape(row)}</th>"
            + "".join(f"<td>{p.cells.get((row, col), 0)}</td>" for col in p.columns)
            + "</tr>"
            for row in p.rows
        )
        return (
            f'<table class="dz-pivot-table">'
            f"<caption>{ctx.escape(p.label)}</caption>"
            f"<thead><tr><th></th>{head}</tr></thead>"
            f"<tbody>{body}</tbody>"
            f"</table>"
        )

    def _emit_timeline(self, t: Timeline, ctx: RenderContext) -> str:
        events = "".join(
            f'<li class="dz-timeline__event">'
            f'<time datetime="{ctx.escape_attr(when)}">{ctx.escape(when)}</time>'
            f'<span class="dz-timeline__label">{ctx.escape(label)}</span>'
            f"</li>"
            for label, when in t.events
        )
        return f'<ol class="dz-timeline">{events}</ol>'

    def _emit_kanban_board(self, k: KanbanBoard, ctx: RenderContext) -> str:
        cols = "".join(
            f'<div class="dz-kanban__column" data-key="{ctx.escape_attr(key)}">'
            + "".join(self._emit(item, ctx) for item in items)  # type: ignore[arg-type]
            + "</div>"
            for key, items in k.columns
        )
        return f'<div class="dz-kanban">{cols}</div>'

    def _emit_calendar_grid(self, c: CalendarGrid, ctx: RenderContext) -> str:
        cls = f"dz-calendar dz-calendar--view-{c.view}"
        events = "".join(
            f'<li class="dz-calendar__event">'
            f'<time datetime="{ctx.escape_attr(when)}">{ctx.escape(when)}</time> '
            f"{ctx.escape(label)}"
            f"</li>"
            for label, when in c.events
        )
        return f'<div class="{cls}"><ul>{events}</ul></div>'

    def _emit_diagram(self, d: Diagram, ctx: RenderContext) -> str:
        """Render an entity-relationship diagram as a paired
        nodes-list + edges-list.

        Phase 4A renders nodes as labelled `<li>` boxes and edges as
        `from → to` rows. A future iteration can produce SVG or wire
        a JS layout engine without changing the IR shape.
        """
        nodes_html = "".join(
            f'<li class="dz-diagram__node" data-key="{ctx.escape_attr(name)}">'
            f"{ctx.escape(name)}</li>"
            for name in d.nodes
        )
        edges_html = "".join(
            f'<li class="dz-diagram__edge">'
            f'<span class="dz-diagram__edge-from">{ctx.escape(src)}</span>'
            f'<span class="dz-diagram__edge-arrow">→</span>'
            f'<span class="dz-diagram__edge-to">{ctx.escape(dst)}</span>'
            f"</li>"
            for src, dst in d.edges
        )
        return (
            f'<section class="dz-diagram">'
            f'<ul class="dz-diagram__nodes">{nodes_html}</ul>'
            f'<ul class="dz-diagram__edges">{edges_html}</ul>'
            f"</section>"
        )

    def _emit_time_series(self, t: TimeSeries, ctx: RenderContext) -> str:
        """Render line/area/sparkline as a labelled `<ol>` of points.

        Phase 4A renders points as semantic data — `<li data-x="…"
        data-y="…">x:y</li>`. CSS hooks (`dz-timeseries--view-line`
        etc.) carry the view distinction so styling can produce the
        chart shape later. A future iteration can swap to inline SVG
        or a charting library without changing the IR shape.
        """
        cls = f"dz-timeseries dz-timeseries--view-{t.view}"
        items = "".join(
            f'<li class="dz-timeseries__point" '
            f'data-x="{ctx.escape_attr(label)}" '
            f'data-y="{value}">'
            f'<span class="dz-timeseries__x">{ctx.escape(label)}</span>'
            f": "
            f'<span class="dz-timeseries__y">{value}</span>'
            f"</li>"
            for label, value in t.points
        )
        return (
            f'<section class="{cls}">'
            f'<h4 class="dz-timeseries__label">{ctx.escape(t.label)}</h4>'
            f'<ol class="dz-timeseries__points">{items}</ol>'
            f"</section>"
        )

    def _emit_radar(self, r: Radar, ctx: RenderContext) -> str:
        """Render a polar/radar profile as a labelled `<ul>` of axes.

        Each axis becomes `<li data-axis="…" data-value="…">`. CSS
        hooks (`dz-radar`) carry the shape; an SVG layout can replace
        the renderer body without changing the IR shape.
        """
        items = "".join(
            f'<li class="dz-radar__axis" '
            f'data-axis="{ctx.escape_attr(axis)}" '
            f'data-value="{value}">'
            f'<span class="dz-radar__axis-label">{ctx.escape(axis)}</span>'
            f'<span class="dz-radar__axis-value">{value}</span>'
            f"</li>"
            for axis, value in r.axes
        )
        return (
            f'<section class="dz-radar">'
            f'<h4 class="dz-radar__label">{ctx.escape(r.label)}</h4>'
            f'<ul class="dz-radar__axes">{items}</ul>'
            f"</section>"
        )

    def _emit_box_plot(self, b: BoxPlot, ctx: RenderContext) -> str:
        """Render a box-plot as a `<table>` of group rows with a column
        per quartile statistic.

        Future iteration can render the boxes as SVG; the table is the
        accessible-by-default fallback and carries the data semantically.
        """
        header = (
            "<thead><tr>"
            "<th>Group</th><th>Min</th><th>Q1</th>"
            "<th>Median</th><th>Q3</th><th>Max</th>"
            "</tr></thead>"
        )
        rows = "".join(
            f"<tr>"
            f"<td>{ctx.escape(label)}</td>"
            f"<td>{mn}</td><td>{q1}</td><td>{med}</td><td>{q3}</td><td>{mx}</td>"
            f"</tr>"
            for label, mn, q1, med, q3, mx in b.groups
        )
        return (
            f'<section class="dz-box-plot">'
            f'<h4 class="dz-box-plot__label">{ctx.escape(b.label)}</h4>'
            f'<table class="dz-box-plot__table">{header}<tbody>{rows}</tbody></table>'
            f"</section>"
        )

    def _emit_action_card(self, a: ActionCard, ctx: RenderContext) -> str:
        """Render an ActionCard as the dashboard CTA card shape.

        Mirrors the legacy `workspace/regions/action_grid.html` rendering
        so dual-path validation (Phase 4B.3) compares clean: anchor wrapper
        when `url` is set, plain `<div>` otherwise; tone tint via
        `data-dz-tone`; optional icon (Lucide) and count badge.
        """
        tone = ctx.escape_attr(a.tone)
        label = ctx.escape(a.label)
        icon_html = (
            f'<span class="dz-action-card-icon" data-lucide="{ctx.escape_attr(a.icon)}" '
            f'aria-hidden="true"></span>'
            if a.icon
            else '<span class="dz-action-card-icon-spacer"></span>'
        )
        count_html = (
            f'<span class="dz-action-card-count" data-dz-tone-badge="{tone}">{a.count}</span>'
            if a.count is not None
            else ""
        )
        body = (
            f'<div class="dz-action-card-row">{icon_html}{count_html}</div>'
            f'<span class="dz-action-card-label">{label}</span>'
        )
        if a.url:
            href = ctx.escape_attr(a.url)
            return f'<a href="{href}" class="dz-action-card" data-dz-tone="{tone}">{body}</a>'
        return f'<div class="dz-action-card" data-dz-tone="{tone}">{body}</div>'

    def _emit_profile_card(self, p: ProfileCard, ctx: RenderContext) -> str:
        """Render a ProfileCard matching the legacy
        `workspace/regions/profile_card.html` HTML shape: identity row
        (avatar or initials + name + meta), optional 3-up stats grid,
        optional bulleted facts list.
        """
        # Identity row: avatar wins over initials
        if p.avatar_url:
            avatar_html = (
                f'<img src="{ctx.escape_attr(p.avatar_url)}" '
                f'alt="{ctx.escape_attr(p.primary)}" '
                f'class="dz-profile-avatar" />'
            )
        elif p.initials:
            avatar_html = (
                f'<span class="dz-profile-initials" aria-hidden="true">'
                f"{ctx.escape(p.initials)}</span>"
            )
        else:
            avatar_html = ""

        text_inner = ""
        if p.primary:
            text_inner += f'<h3 class="dz-profile-primary">{ctx.escape(p.primary)}</h3>'
        if p.secondary:
            text_inner += f'<p class="dz-profile-secondary">{ctx.escape(p.secondary)}</p>'
        identity_html = (
            f'<div class="dz-profile-identity">'
            f"{avatar_html}"
            f'<div class="dz-profile-text">{text_inner}</div>'
            f"</div>"
        )

        # Stats grid — em-dash for empty values (matches legacy `stat.value or "—"`)
        stats_html = ""
        if p.stats:
            stat_rows = "".join(
                f'<div class="dz-profile-stat">'
                f'<dt class="dz-profile-stat-label">{ctx.escape(label)}</dt>'
                f'<dd class="dz-profile-stat-value">{ctx.escape(value) if value else "—"}</dd>'
                f"</div>"
                for label, value in p.stats
            )
            stats_html = f'<dl class="dz-profile-stats">{stat_rows}</dl>'

        # Facts list — bullet decoration via CSS, not literal text
        facts_html = ""
        if p.facts:
            fact_items = "".join(
                f'<li class="dz-profile-fact">'
                f'<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
                f'<span class="dz-profile-fact-text">{ctx.escape(fact)}</span>'
                f"</li>"
                for fact in p.facts
            )
            facts_html = f'<ul class="dz-profile-facts">{fact_items}</ul>'

        return f'<div class="dz-profile-card">{identity_html}{stats_html}{facts_html}</div>'

    def _emit_metric_tile(self, m: MetricTile, ctx: RenderContext) -> str:
        """Render a MetricTile matching the legacy
        `workspace/regions/metrics.html` HTML shape: dz-metric-tile
        wrapper with snake-cased data-dz-metric-key, optional data-dz-tone,
        label + already-formatted value, and a delta block when
        delta_direction is set.

        The delta tone is computed from (direction, sentiment):
            - up + positive_up   = good (positive)
            - down + positive_down = good (positive)
            - down + positive_up = bad (destructive)
            - up + positive_down = bad (destructive)
            - flat or anything else = neutral
        """
        key_attr = m.label.lower().replace(" ", "_")
        tone_attr = f' data-dz-tone="{ctx.escape_attr(m.tone)}"' if m.tone else ""

        delta_html = ""
        if m.delta_direction:
            is_good = (m.delta_direction == "up" and m.delta_sentiment == "positive_up") or (
                m.delta_direction == "down" and m.delta_sentiment == "positive_down"
            )
            is_bad = (m.delta_direction == "down" and m.delta_sentiment == "positive_up") or (
                m.delta_direction == "up" and m.delta_sentiment == "positive_down"
            )
            delta_tone = "positive" if is_good else ("destructive" if is_bad else "neutral")
            arrow = (
                "↑" if m.delta_direction == "up" else ("↓" if m.delta_direction == "down" else "→")
            )
            sign = "+" if m.delta_direction == "up" else ""
            pct_html = (
                f'<span class="dz-metric-delta-pct">({m.delta_pct}%)</span>' if m.delta_pct else ""
            )
            period_html = (
                f'<span class="dz-metric-delta-period">vs {ctx.escape(m.delta_period_label)}</span>'
                if m.delta_period_label
                else ""
            )
            delta_html = (
                f'<div class="dz-metric-delta" '
                f'data-dz-delta-tone="{delta_tone}" '
                f'data-dz-delta-direction="{ctx.escape_attr(m.delta_direction)}" '
                f'data-dz-delta-sentiment="{ctx.escape_attr(m.delta_sentiment)}">'
                f'<span aria-hidden="true">{arrow}</span>'
                f'<span class="dz-metric-delta-value">{sign}{ctx.escape(m.delta_value)}</span>'
                f"{pct_html}"
                f"{period_html}"
                f"</div>"
            )

        return (
            f'<div class="dz-metric-tile" '
            f'data-dz-metric-key="{ctx.escape_attr(key_attr)}"{tone_attr}>'
            f'<div class="dz-metric-label">{ctx.escape(m.label)}</div>'
            f'<div class="dz-metric-value">{ctx.escape(m.value)}</div>'
            f"{delta_html}"
            f"</div>"
        )

    def _emit_form_stack(self, fs: FormStack, ctx: RenderContext) -> str:
        action = ctx.escape_attr(str(fs.action))
        fields_html = "".join(self._emit(f, ctx) for f in fs.fields)  # type: ignore[arg-type]
        submit_html = self._emit(fs.submit, ctx) if fs.submit is not None else ""
        return (
            f'<form class="dz-form-stack" action="{action}" method="{fs.method}">'
            f"{fields_html}{submit_html}"
            f"</form>"
        )

    def _emit_field(self, f: Field, ctx: RenderContext) -> str:
        # Field labels are developer-supplied; values may be user-supplied —
        # escape both as a safety net.
        label = ctx.escape(f.label)
        name = ctx.escape_attr(f.name)
        placeholder = ctx.escape_attr(f.placeholder)
        initial = ctx.escape_attr(f.initial_value)
        required_attr = " required" if f.required else ""
        readonly_attr = " readonly" if f.readonly else ""

        if f.kind == "textarea":
            inner = (
                f'<textarea class="dz-field__input" name="{name}" '
                f'placeholder="{placeholder}"{required_attr}{readonly_attr}>'
                f"{ctx.escape(f.initial_value)}</textarea>"
            )
        elif f.kind == "checkbox":
            checked = " checked" if f.initial_value == "true" else ""
            inner = (
                f'<input class="dz-field__input" type="checkbox" name="{name}"'
                f"{checked}{required_attr}{readonly_attr}>"
            )
        else:
            inner = (
                f'<input class="dz-field__input" type="{f.kind}" name="{name}" '
                f'value="{initial}" placeholder="{placeholder}"{required_attr}{readonly_attr}>'
            )
        return (
            f'<label class="dz-field"><span class="dz-field__label">{label}</span>{inner}</label>'
        )

    def _emit_combobox(self, c: Combobox, ctx: RenderContext) -> str:
        options = "".join(
            f'<option value="{ctx.escape_attr(value)}"'
            + (" selected" if value == c.initial_value else "")
            + f">{ctx.escape(label)}</option>"
            for value, label in c.options
        )
        required_attr = " required" if c.required else ""
        label = ctx.escape(c.label)
        name = ctx.escape_attr(c.name)
        return (
            f'<label class="dz-combobox">'
            f'<span class="dz-combobox__label">{label}</span>'
            f'<select class="dz-combobox__select" name="{name}"{required_attr}>{options}</select>'
            f"</label>"
        )

    def _emit_ref_picker(self, r: RefPicker, ctx: RenderContext) -> str:
        name = ctx.escape_attr(r.name)
        label = ctx.escape(r.label)
        ref_api = ctx.escape_attr(r.ref_api.value)
        initial_value = ctx.escape_attr(r.initial_value)
        required_attr = " required" if r.required else ""
        if r.initial_value:
            initial_option = (
                f'<option value="{initial_value}" selected>'
                f"{ctx.escape(r.initial_label or r.initial_value)}</option>"
            )
        else:
            initial_option = ""
        return (
            f'<label class="dz-ref-picker">'
            f'<span class="dz-ref-picker__label">{label}</span>'
            f'<select class="dz-ref-picker__select" name="{name}" '
            f'data-ref-api="{ref_api}" '
            f'data-selected-value="{initial_value}" '
            f'x-init="dz.filterRefSelect($el)"{required_attr}>'
            f"{initial_option}"
            f"</select>"
            f"</label>"
        )

    def _emit_submit(self, s: Submit, ctx: RenderContext) -> str:
        cls = f"dz-submit dz-submit--variant-{s.variant}"
        return f'<button type="submit" class="{cls}">{ctx.escape(s.label)}</button>'
