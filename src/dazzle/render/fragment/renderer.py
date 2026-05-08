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
    BarTrack,
    BoxPlot,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    ConfirmCheckItem,
    ConfirmGate,
    CsvExportButton,
    DateRangePicker,
    Diagram,
    Drawer,
    EmptyState,
    ErrorPage,
    Field,
    FilterBar,
    FilterColumn,
    FormStack,
    Fragment,
    Grid,
    Heading,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    LazyTabPanel,
    Link,
    MetricTile,
    Modal,
    NavGroup,
    NavItem,
    Page,
    PivotTable,
    ProfileCard,
    Radar,
    ReferenceBand,
    ReferenceLine,
    RefPicker,
    Region,
    Row,
    SearchBox,
    Sidebar,
    Skeleton,
    SkipLink,
    SortHeader,
    Split,
    Stack,
    StageBar,
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
            case BarTrack():
                return self._emit_bar_track(fragment, ctx)
            case StageBar():
                return self._emit_stage_bar(fragment, ctx)
            case LazyTabPanel():
                return self._emit_lazy_tab_panel(fragment, ctx)
            case SearchBox():
                return self._emit_search_box(fragment, ctx)
            case ConfirmGate():
                return self._emit_confirm_gate(fragment, ctx)
            case FilterBar():
                return self._emit_filter_bar(fragment, ctx)
            case SortHeader():
                return self._emit_sort_header(fragment, ctx)
            case CsvExportButton():
                return self._emit_csv_export_button(fragment, ctx)
            case DateRangePicker():
                return self._emit_date_range_picker(fragment, ctx)
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
        hx_put: object | None = None,
        hx_vals: str = "",
        hx_ext: tuple[str, ...] = (),
    ) -> str:
        """Build the htmx attribute string for an interactive primitive.

        All values are escaped for attribute context. Wrapper types (URL,
        TargetSelector, HxTrigger) are validated at construction; this
        escape pass converts characters like `&` in query strings to their
        HTML entity form so the output is valid HTML5.

        Phase 4B.1.d added hx_put + hx_vals + hx_ext (queue transitions,
        JSON payloads, hx-ext extension list).
        """
        parts: list[str] = []
        if hx_get is not None:
            parts.append(f'hx-get="{_escape(str(hx_get), quote=True)}"')
        if hx_post is not None:
            parts.append(f'hx-post="{_escape(str(hx_post), quote=True)}"')
        if hx_put is not None:
            parts.append(f'hx-put="{_escape(str(hx_put), quote=True)}"')
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
        if hx_vals:
            # Use single quotes around the JSON value so internal double
            # quotes (a JSON dict's quoted keys) don't need escaping.
            # Single quotes inside the value are escaped to &#39;.
            escaped_vals = hx_vals.replace("'", "&#39;")
            parts.append(f"hx-vals='{escaped_vals}'")
        if hx_ext:
            parts.append(f'hx-ext="{_escape(",".join(hx_ext), quote=True)}"')
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
            hx_put=b.hx_put,
            hx_target=b.hx_target,
            hx_swap=b.hx_swap,
            hx_trigger=b.hx_trigger,
            hx_indicator=b.hx_indicator,
            hx_confirm=b.hx_confirm,
            hx_vals=b.hx_vals,
            hx_ext=b.hx_ext,
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

    def _render_references(
        self,
        block_class: str,
        reference_lines: tuple[ReferenceLine, ...],
        reference_bands: tuple[ReferenceBand, ...],
        ctx: RenderContext,
    ) -> str:
        """Shared helper — emit a `<dl class="<block>__references">` annotation
        list when a chart primitive carries reference_lines or reference_bands.
        Returns empty string when both tuples are empty.

        Used by TimeSeries, BarChart, BarTrack, BoxPlot. Future SVG-rendering
        ship will overlay references on the visual chart instead.
        """
        if not reference_lines and not reference_bands:
            return ""
        line_items = "".join(
            f'<div class="{block_class}__ref-line" '
            f'data-style="{ctx.escape_attr(line.style)}" '
            f'data-value="{line.value}">'
            f'<dt class="{block_class}__ref-label">{ctx.escape(line.label) or "ref"}</dt>'
            f'<dd class="{block_class}__ref-value">{line.value}</dd>'
            f"</div>"
            for line in reference_lines
        )
        band_items = "".join(
            f'<div class="{block_class}__ref-band" '
            f'data-color="{ctx.escape_attr(band.color)}" '
            f'data-from="{band.from_value}" '
            f'data-to="{band.to_value}">'
            f'<dt class="{block_class}__ref-label">{ctx.escape(band.label) or "band"}</dt>'
            f'<dd class="{block_class}__ref-range">'
            f"{band.from_value}–{band.to_value}</dd>"
            f"</div>"
            for band in reference_bands
        )
        return f'<dl class="{block_class}__references">{line_items}{band_items}</dl>'

    def _emit_bar_chart(self, b: BarChart, ctx: RenderContext) -> str:
        """Render a bar chart as label/track/fill/value rows — byte-equivalent
        to the legacy `workspace/regions/bar_chart.html` template.

        Phase 4B.1.c (SVG arc, bar variant): replaces the prior BEM
        emit with the legacy single-dash CSS-bar structure (track div +
        fill div with `width: N%`). The `dz-bar-chart-references`
        annotation block is the v0.66.81 programmatic-data layer and
        keeps its BEM `__references` form (net-new from Phase 4B —
        no legacy template equivalent to match).
        """
        if not b.buckets:
            return (
                f'<div class="dz-bar-chart-region" aria-label="{ctx.escape_attr(b.label)}"></div>'
            )

        max_val = max((c for _, c in b.buckets), default=1) or 1
        total = sum(c for _, c in b.buckets)
        rows = "".join(
            f'<div class="dz-bar-chart-row">'
            f'<span class="dz-bar-chart-label">{ctx.escape(label)}</span>'
            f'<div class="dz-bar-chart-track">'
            f'<div class="dz-bar-chart-fill" '
            f'style="width: {int(count / max_val * 100)}%"></div>'
            f"</div>"
            f'<span class="dz-bar-chart-value">{count}</span>'
            f"</div>"
            for label, count in b.buckets
        )
        refs = self._render_references("dz-bar-chart", b.reference_lines, b.reference_bands, ctx)
        return (
            f'<div class="dz-bar-chart-region" '
            f'aria-label="{ctx.escape_attr(b.label)}">'
            f'<div class="dz-bar-chart-bars">{rows}</div>'
            f'<p class="dz-bar-chart-summary">{total} total</p>'
            f"{refs}"
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
        """Render line/area/sparkline as inline SVG plus optional `<dl>`
        annotation lists for reference lines and reference bands.

        Phase 4B.1.c replaced the semantic `<ol>` of points with an
        inline SVG produced by `dazzle.render.svg.time_series_svg` —
        byte-equivalent to the legacy `line_chart.html` template. The
        `<dl class="dz-timeseries__references">` block remains as the
        programmatic-data layer for screen-readers and tests; the SVG
        already carries the same data via `<title>` tooltips and is
        the visual layer.
        """
        from dazzle.render.svg import time_series_svg

        cls = f"dz-timeseries dz-timeseries--view-{t.view}"
        svg = time_series_svg(
            t.label,
            t.points,
            view=t.view,
            reference_lines=t.reference_lines,
            reference_bands=t.reference_bands,
        )
        references_html = self._render_references(
            "dz-timeseries", t.reference_lines, t.reference_bands, ctx
        )

        return (
            f'<section class="{cls}">'
            f'<h4 class="dz-timeseries__label">{ctx.escape(t.label)}</h4>'
            f"{svg}"
            f"{references_html}"
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
        refs = self._render_references("dz-box-plot", b.reference_lines, b.reference_bands, ctx)
        return (
            f'<section class="dz-box-plot">'
            f'<h4 class="dz-box-plot__label">{ctx.escape(b.label)}</h4>'
            f'<table class="dz-box-plot__table">{header}<tbody>{rows}</tbody></table>'
            f"{refs}"
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

    def _emit_bar_track(self, b: BarTrack, ctx: RenderContext) -> str:
        """Render a BarTrack matching legacy `workspace/regions/bar_track.html`:
        per-row track with ARIA progressbar semantics + a summary line.
        """
        rows_html = "".join(
            f'<div class="dz-bar-track-row">'
            f'<span class="dz-bar-track-label" title="{ctx.escape_attr(label)}">'
            f"{ctx.escape(label)}</span>"
            f'<div class="dz-bar-track" role="progressbar" '
            f'aria-valuemin="0" '
            f'aria-valuemax="{b.max_value}" '
            f'aria-valuenow="{value}" '
            f'aria-label="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}">'
            f'<span class="dz-bar-track-fill" '
            f'style="width: {round(fill_pct, 2)}%;" '
            f'title="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}"></span>'
            f"</div>"
            f'<span class="dz-bar-track-value">{ctx.escape(formatted)}</span>'
            f"</div>"
            for label, value, formatted, fill_pct in b.rows
        )
        refs = self._render_references("dz-bar-track", b.reference_lines, b.reference_bands, ctx)
        return (
            f'<div class="dz-bar-track-rows">{rows_html}</div>'
            f'<p class="dz-bar-track-summary">'
            f"{len(b.rows)} rows · scale 0–{round(b.max_value, 2)}"
            f"</p>"
            f"{refs}"
        )

    def _emit_stage_bar(self, s: StageBar, ctx: RenderContext) -> str:
        """Render a StageBar matching legacy
        `workspace/regions/progress.html`: header `<progress>` + percent
        readout + chip list of stages with per-chip tone (complete /
        active / empty), and an optional "N of M complete" summary.
        """
        chips_html = "".join(
            f'<span class="dz-progress-chip" '
            f'data-dz-stage-tone="{("complete" if complete else ("active" if count > 0 else "empty"))}">'
            f"{ctx.escape(name)} ({count})"
            f"</span>"
            for name, count, complete in s.stages
        )
        summary_html = (
            f'<p class="dz-progress-summary">{s.complete_count} of {s.total} complete</p>'
            if s.total > 0
            else ""
        )
        return (
            f'<div class="dz-progress-header">'
            f'<progress data-dz-progress value="{s.complete_pct}" max="100"></progress>'
            f"<span>{s.complete_pct}%</span>"
            f"</div>"
            f'<div class="dz-progress-stages">{chips_html}</div>'
            f"{summary_html}"
        )

    def _emit_lazy_tab_panel(self, p: LazyTabPanel, ctx: RenderContext) -> str:
        """Render a LazyTabPanel matching legacy
        `workspace/regions/tabbed_list.html` byte-for-byte.

        Each tab becomes:
          - a `<a role="tab">` button with an inline `onclick` JS
            handler that toggles `is-active` and shows/hides panels
          - a `<div class="tab-panel">` shell that fetches its own
            content via `hx-get` on first activation

        The first tab fires `load`; subsequent tabs fire on
        `intersect once`. The first panel is visible by default
        (no `hidden` class); other panels start hidden.

        DOM ids: `tabs-<region>` for the tablist, `tab-<region>-<key>`
        for each panel.
        """
        rname = ctx.escape_attr(p.region_name)
        # Inline-JS click handler: vanilla JS toggles is-active +
        # shows/hides panels. Mirrors the legacy template verbatim
        # so dual-path validation stays byte-equivalent.
        click_js = (
            f"document.querySelectorAll('#tabs-{p.region_name} [role=tab]')"
            f".forEach(t =&gt; t.classList.remove('is-active')); "
            f"this.classList.add('is-active'); "
            f"document.querySelectorAll('#panels-{p.region_name} .tab-panel')"
            f".forEach(p =&gt; p.classList.add('hidden')); "
            f"document.getElementById(this.dataset.tabTarget).classList.remove('hidden');"
        )

        tab_buttons = "".join(
            f'<a role="tab" '
            f'class="dz-tabbed-list-tab{" is-active" if i == 0 else ""}" '
            f'data-tab-target="tab-{rname}-{ctx.escape_attr(tab.key)}" '
            f'onclick="{click_js}">'
            f"{ctx.escape(tab.label)}</a>"
            for i, tab in enumerate(p.tabs)
        )

        panels = "".join(
            f'<div id="tab-{rname}-{ctx.escape_attr(tab.key)}" '
            f'class="tab-panel{"" if i == 0 else " hidden"}" '
            f'hx-get="{ctx.escape_attr(str(tab.endpoint))}" '
            f'hx-trigger="{"load" if (tab.eager or i == 0) else "intersect once"}" '
            f'hx-swap="innerHTML">'
            f'<div class="dz-tabbed-list-panel-loading">'
            f'<svg fill="none" viewBox="0 0 24 24" aria-hidden="true">'
            f'<circle class="opacity-25" cx="12" cy="12" r="10" '
            f'stroke="currentColor" stroke-width="4"></circle>'
            f'<path class="opacity-75" fill="currentColor" '
            f'd="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>'
            f"</svg>"
            f"</div>"
            f"</div>"
            for i, tab in enumerate(p.tabs)
        )

        return (
            f'<div role="tablist" class="dz-tabbed-list-tabs" id="tabs-{rname}">'
            f"{tab_buttons}"
            f"</div>"
            f'<div id="panels-{rname}">{panels}</div>'
        )

    def _emit_search_box(self, s: SearchBox, ctx: RenderContext) -> str:
        """Render a SearchBox matching legacy
        `workspace/regions/search_box.html` byte-for-byte: an Alpine
        `x-data="{ q: '' }"` outer div, accessible label + search
        input wired to HTMX with 250ms debounce, results panel with
        `aria-live="polite"`, coaching message hidden via `x-show`
        once the user types.
        """
        results_id = f"dz-search-results-{ctx.escape_attr(s.name)}"
        endpoint = ctx.escape_attr(str(s.fts_endpoint))
        placeholder = ctx.escape_attr(s.placeholder)
        coaching = ctx.escape(s.coaching_message)
        # Label uses placeholder as fallback when no explicit label is
        # supplied — matches the legacy template's `title or _placeholder`.
        label_text = ctx.escape(s.label or s.placeholder)
        return (
            f'<div class="dz-search-box-region" x-data="{{ q: \'\' }}">'
            f'<div class="dz-search-box-input-row">'
            f'<label for="{results_id}-input" class="visually-hidden">{label_text}</label>'
            f'<input id="{results_id}-input" type="search" name="q" '
            f'class="dz-search-box-input" placeholder="{placeholder}" '
            f'autocomplete="off" '
            f'hx-get="{endpoint}" '
            f'hx-trigger="input changed delay:250ms, search" '
            f'hx-target="#{results_id}" '
            f'hx-swap="innerHTML" '
            f'x-model="q">'
            f"</div>"
            f'<div id="{results_id}" class="dz-search-box-results" '
            f'role="region" aria-live="polite">'
            f'<div class="dz-search-box-empty" x-show="!q">'
            f"{coaching}"
            f"</div>"
            f"</div>"
            f"</div>"
        )

    def _emit_confirm_gate(self, c: ConfirmGate, ctx: RenderContext) -> str:
        """Render a ConfirmGate matching legacy
        `workspace/regions/confirm_action_panel.html` byte-for-byte.

        Three state branches:
          - live / active / on / enabled → "Currently live" summary
          - revoked / disabled / off-revoked → audit summary
          - everything else → checklist (when supplied) + dual button

        Audit footer renders in all branches when `audit_enabled`.
        """
        state_lower = (c.state or "off").lower()
        is_live = state_lower in ("live", "active", "on", "enabled")
        is_revoked = state_lower in ("revoked", "disabled", "off-revoked")
        state_attr = ctx.escape_attr(c.state or "off")

        # ── State branches ──────────────────────────────────────
        if is_live:
            inner = (
                f'<div class="dz-confirm-summary" data-dz-confirm-tone="success">'
                f'<div class="dz-confirm-summary-title">{ctx.escape(c.live_title)}</div>'
                f'<div class="dz-confirm-summary-body">{ctx.escape(c.live_body)}</div>'
                f"</div>"
            )
            if c.revoke_url:
                inner += (
                    f'<div class="dz-confirm-actions">'
                    f'<a href="{ctx.escape_attr(c.revoke_url)}" class="dz-confirm-revoke">'
                    f"{ctx.escape(c.revoke_label)}</a>"
                    f"</div>"
                )
        elif is_revoked:
            inner = (
                f'<div class="dz-confirm-summary" data-dz-confirm-tone="muted">'
                f'<div class="dz-confirm-summary-title">{ctx.escape(c.revoked_title)}</div>'
                f'<div class="dz-confirm-summary-body">{ctx.escape(c.revoked_body)}</div>'
                f"</div>"
            )
            if c.primary_action_url:
                inner += (
                    f'<div class="dz-confirm-actions">'
                    f'<a href="{ctx.escape_attr(c.primary_action_url)}" '
                    f'class="dz-confirm-primary">{ctx.escape(c.re_enable_label)}</a>'
                    f"</div>"
                )
        elif c.confirmations:
            # Off/pending/draft with checklist
            required_count = sum(1 for item in c.confirmations if item.required)

            def _render_check_item(i: int, item: ConfirmCheckItem) -> str:
                required_str = "true" if item.required else "false"
                # Required items get @change Alpine binding + data attribute.
                # Note: emit literal `"` quotes — these are HTML attributes,
                # not nested inside an outer-quoted attribute.
                required_attrs = (
                    '@change="onToggle($event)" data-dz-required="true" ' if item.required else ""
                )
                caption_html = (
                    f'<div class="dz-confirm-caption">{ctx.escape(item.caption)}</div>'
                    if item.caption
                    else ""
                )
                return (
                    f'<li class="dz-confirm-row" data-dz-required="{required_str}">'
                    f'<input type="checkbox" class="dz-confirm-checkbox" '
                    f"{required_attrs}"
                    f'id="dz-confirm-{i}">'
                    f'<label for="dz-confirm-{i}" class="dz-confirm-row-label">'
                    f'<div class="dz-confirm-title">{ctx.escape(item.title)}</div>'
                    f"{caption_html}"
                    f"</label>"
                    f"</li>"
                )

            checklist_items = "".join(
                _render_check_item(i, item) for i, item in enumerate(c.confirmations, start=1)
            )
            # Dual-button row (still inside the <ul> per legacy template)
            actions_inner = ""
            if c.secondary_action_url:
                actions_inner += (
                    f'<a href="{ctx.escape_attr(c.secondary_action_url)}" '
                    f'class="dz-confirm-secondary">{ctx.escape(c.secondary_label)}</a>'
                )
            if c.primary_action_url:
                # Alpine bindings: enabled is provided by dzConfirmGate(count)
                actions_inner += (
                    f"<a :href=\"enabled ? '{ctx.escape_attr(c.primary_action_url)}' : null\" "
                    f':aria-disabled="!enabled" '
                    f":class=\"{{ 'is-disabled': !enabled }}\" "
                    f'class="dz-confirm-primary">'
                    f"{ctx.escape(c.primary_label)}</a>"
                )
            inner = (
                f'<ul x-data="dzConfirmGate({len(c.confirmations)})" '
                f'class="dz-confirm-checklist" '
                f'data-dz-required-count="{required_count}">'
                f"{checklist_items}"
                f'<li class="dz-confirm-actions">{actions_inner}</li>'
                f"</ul>"
            )
        else:
            # Off/pending/draft, no checklist — dual button alone
            actions_inner = ""
            if c.secondary_action_url:
                actions_inner += (
                    f'<a href="{ctx.escape_attr(c.secondary_action_url)}" '
                    f'class="dz-confirm-secondary">{ctx.escape(c.secondary_label)}</a>'
                )
            if c.primary_action_url:
                actions_inner += (
                    f'<a href="{ctx.escape_attr(c.primary_action_url)}" '
                    f'class="dz-confirm-primary">'
                    f"{ctx.escape('Confirm')}</a>"
                )
            inner = f'<div class="dz-confirm-actions">{actions_inner}</div>'

        # ── Audit footer ────────────────────────────────────────
        audit_html = (
            '<p class="dz-confirm-audit">'
            "This action is recorded in the audit log with your account, "
            "IP address, and timestamp."
            "</p>"
            if c.audit_enabled
            else ""
        )

        return (
            f'<div class="dz-confirm-panel" data-dz-state-value="{state_attr}">'
            f"{inner}"
            f"{audit_html}"
            f"</div>"
        )

    def _emit_filter_bar(self, f: FilterBar, ctx: RenderContext) -> str:
        """Render a FilterBar matching legacy `queue.html` / `list.html`
        filter-row markup byte-for-byte: a `.filter-bar` flex row of
        `<select>` elements wired to the region endpoint via HTMX with
        `hx-include="closest .filter-bar"` so all active filter values
        ride along on each change.
        """
        target = f"#region-{ctx.escape_attr(f.region_name)}"
        endpoint = ctx.escape_attr(str(f.endpoint))

        def _render_column(col: FilterColumn) -> str:
            options_html = f'<option value="">All {ctx.escape(col.label)}</option>'
            for value, display in col.options:
                selected_attr = " selected" if value == col.selected else ""
                options_html += (
                    f'<option value="{ctx.escape_attr(value)}"{selected_attr}>'
                    f"{ctx.escape(display)}</option>"
                )
            return (
                f'<select class="dz-queue-filter-select" '
                f'hx-get="{endpoint}" '
                f'hx-target="{target}" '
                f'hx-swap="innerHTML" '
                f'hx-include="closest .filter-bar" '
                f'name="filter_{ctx.escape_attr(col.key)}">'
                f"{options_html}"
                f"</select>"
            )

        selects_html = "".join(_render_column(col) for col in f.columns)
        return f'<div class="dz-queue-filters filter-bar">{selects_html}</div>'

    def _emit_sort_header(self, s: SortHeader, ctx: RenderContext) -> str:
        """Render a SortHeader as an HTMX-driven column-header link.

        Matches the legacy `list.html` sort-link markup byte-for-byte:
        when this column is currently the active sort, append a
        ▲ (asc) or ▼ (desc) indicator and emit a link that flips the
        direction. Other columns always sort ascending on first click.
        Uses `&amp;` for the URL parameter separator (matches the
        legacy template's `hx-get` value with HTML-encoded ampersand).
        """
        is_active = s.current_sort == s.column_key
        # Next direction: flip if active, otherwise asc
        if is_active:
            next_dir = "desc" if s.current_direction == "asc" else "asc"
        else:
            next_dir = "asc"
        endpoint = ctx.escape_attr(str(s.endpoint))
        target = f"#region-{ctx.escape_attr(s.region_name)}"
        column_key = ctx.escape_attr(s.column_key)
        # Use &amp; for the URL param separator inside the attribute value
        href = f"{endpoint}?sort={column_key}&amp;dir={next_dir}"
        indicator = ""
        if is_active:
            indicator = f"<span>{'▼' if s.current_direction == 'desc' else '▲'}</span>"
        return (
            f'<a hx-get="{href}" '
            f'hx-target="{target}" '
            f'hx-swap="innerHTML" '
            f'class="dz-list-sort-link">'
            f"{ctx.escape(s.label)}"
            f"{indicator}"
            f"</a>"
        )

    def _emit_csv_export_button(self, c: CsvExportButton, ctx: RenderContext) -> str:
        """Render a CsvExportButton matching the legacy `list.html`
        export-button markup. The inline `onclick` defers to the
        global `dz.downloadCsv` helper so Safari's same-origin
        text/csv quirk is bypassed (#862)."""
        endpoint = ctx.escape_attr(str(c.endpoint))
        filename = ctx.escape_attr(c.filename)
        label = ctx.escape_attr(c.label)
        return (
            f'<button type="button" '
            f'data-dz-csv-endpoint="{endpoint}" '
            f'data-dz-csv-filename="{filename}" '
            f'onclick="window.dz.downloadCsv('
            f"this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename"
            f')" '
            f'class="dz-list-csv-button" '
            f'title="{label}" aria-label="{label}">'
            f'<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            f'd="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 '
            f'01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>'
            f"</svg>"
            f"</button>"
        )

    def _emit_date_range_picker(self, d: DateRangePicker, ctx: RenderContext) -> str:
        """Render a DateRangePicker matching the legacy
        `fragments/date_range_picker.html` byte-for-byte: paired
        From/To `<input type="date">` elements with HTMX
        `hx-include="closest .date-range-bar"` so both values ride
        along on every change.
        """
        rname = ctx.escape_attr(d.region_name)
        endpoint = ctx.escape_attr(str(d.endpoint))
        target = f"#region-{rname}"
        date_from = ctx.escape_attr(d.date_from)
        date_to = ctx.escape_attr(d.date_to)
        return (
            f'<div class="dz-date-range-picker date-range-bar">'
            f'<label class="dz-date-range-label" for="date-from-{rname}">From</label>'
            f'<input type="date" id="date-from-{rname}" name="date_from" '
            f'value="{date_from}" class="dz-date-range-input" '
            f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
            f'hx-include="closest .date-range-bar">'
            f'<label class="dz-date-range-label" for="date-to-{rname}">To</label>'
            f'<input type="date" id="date-to-{rname}" name="date_to" '
            f'value="{date_to}" class="dz-date-range-input" '
            f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
            f'hx-include="closest .date-range-bar">'
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
