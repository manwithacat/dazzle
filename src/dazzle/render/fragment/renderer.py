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
    Badge,
    BarChart,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    Drawer,
    EmptyState,
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
    Modal,
    PivotTable,
    RefPicker,
    Region,
    Row,
    Skeleton,
    Split,
    Stack,
    Submit,
    Surface,
    Table,
    Tabs,
    Text,
    Timeline,
    Toolbar,
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
        return f'<section class="{cls}">{self._emit(r.body, ctx)}</section>'  # type: ignore[arg-type]

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
