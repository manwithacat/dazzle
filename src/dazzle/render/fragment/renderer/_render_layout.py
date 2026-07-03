"""Layout-family region builders.

Houses the 17 layout primitives — text/heading containers + structural
boxes + simple flat displays. None of these touch HTMX or external
state; pure structural emission.

  - _emit_text             plain text run
  - _emit_heading          heading level 1-6
  - _emit_stack            vertical stack with gap
  - _emit_row              horizontal row
  - _emit_split            two-pane split
  - _emit_grid             CSS-grid container
  - _emit_card             titled card box
  - _emit_surface          Surface(header, body) wrapper
  - _emit_region           kind-tagged region wrapper
  - _emit_drawer           lateral drawer panel
  - _emit_modal            modal dialog
  - _emit_tabs             tab strip + panels
  - _emit_lazy_tab_panel   HTMX-lazy tab panel
  - _emit_icon             SVG icon
  - _emit_badge            label + tone
  - _emit_empty_state      empty-state placeholder
  - _emit_skeleton         loading-skeleton lines

All methods only call `self._emit(child, ctx)` for child recursion;
dispatch goes back through the match block in `_emit.py`.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.icon_html import lucide_icon_html
from dazzle.render.fragment.primitives import (
    Badge,
    Card,
    Drawer,
    DzTableMount,
    EmptyState,
    Grid,
    Heading,
    Icon,
    LazyTabPanel,
    Modal,
    Region,
    Row,
    Skeleton,
    Split,
    Stack,
    Surface,
    Tabs,
    Text,
)

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


class _RenderLayoutMixin:
    """Mixin adding 17 layout-family `_emit_*` methods to `FragmentRenderer`.

    Same pattern as the family mixins in `region_adapter` (#1065).

    Mixin contract: the host class must provide a `_emit(fragment, ctx)`
    method (the dispatcher's match-block emit) so layout container
    primitives can render their children. Declared here as a TYPE_CHECKING
    stub so mypy can resolve `self._emit(child, ctx)` calls.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

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
        data_attr = f' data-dazzle-table="{ctx.escape_attr(r.data_table)}"' if r.data_table else ""
        # Phase 2: detail regions carry the entity anchor tier2 e2e gestures +
        # dz-analytics.js scope by.
        if r.data_entity:
            ent = ctx.escape_attr(r.data_entity)
            data_attr += f' data-dazzle-entity="{ent}" data-dz-entity="{ent}"'
            if r.data_entity_id:
                data_attr += f' data-dz-entity-id="{ctx.escape_attr(r.data_entity_id)}"'
        # ADR-0049 D3: when the region carries a dzTable mount, the root gets
        # the `x-data="dzTable(id, endpoint, config)"` controller wrapper —
        # the same one the legacy `render_filterable_table` mounted — so the
        # hydrated rows' sort/bulk/inline/column-visibility bindings resolve.
        mount_attr = self._dztable_mount_attrs(r.mount, ctx) if r.mount is not None else ""
        body_html = self._emit(r.body, ctx)  # type: ignore[arg-type]
        # Task 4e: a controlled list region carries the polite ARIA live region
        # the dzTable controller announces sort/loading state into
        # (`getElementById("dz-live-region")`). One per list region.
        live_region = (
            '<div id="dz-live-region" aria-live="polite" aria-atomic="true" '
            'class="visually-hidden"></div>'
            if r.mount is not None
            else ""
        )
        return f'<section class="{cls}"{mount_attr}{data_attr}>{body_html}{live_region}</section>'

    @staticmethod
    def _dztable_mount_attrs(m: DzTableMount, ctx: RenderContext) -> str:
        config = {
            "sortField": m.sort_field,
            "sortDir": m.sort_dir,
            "inlineEditable": list(m.inline_editable),
            "bulkActions": m.bulk_actions,
            "entityName": m.entity_name,
        }
        config_json = json.dumps(config)
        table_id = ctx.escape_attr(m.table_id)
        endpoint = ctx.escape_attr(m.endpoint)
        return (
            f' id="{table_id}"'
            f' x-data=\'dzTable("{table_id}", "{endpoint}", {config_json})\''
            ' :aria-busy="loading"'
            ' data-dz-bulk-count="0"'
        )

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
        return lucide_icon_html(i.name, cls=f"dz-icon dz-icon--size-{i.size}")

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
        # Legacy template emits raw `>` in the onclick attribute, not
        # `&gt;`. Match that. Note this is technically not strictly
        # spec-valid HTML attr escaping, but browsers parse it fine
        # and the dual-path harness compares byte-for-byte.
        click_js = (
            f"document.querySelectorAll('#tabs-{p.region_name} [role=tab]')"
            f".forEach(t => t.classList.remove('is-active')); "
            f"this.classList.add('is-active'); "
            f"document.querySelectorAll('#panels-{p.region_name} .tab-panel')"
            f".forEach(p => p.classList.add('hidden')); "
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
