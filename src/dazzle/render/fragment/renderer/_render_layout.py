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
        # Layouts L2: the HM stack Hyperpart contract — gap rides the shared
        # data-dz-gap scale, not the retired --gap-* modifier classes.
        body = "".join(self._emit(c, ctx) for c in s.children)  # type: ignore[arg-type]
        return f'<div class="dz-stack" data-dz-gap="{ctx.escape_attr(s.gap)}">{body}</div>'

    def _emit_row(self, r: Row, ctx: RenderContext) -> str:
        # Layouts L2: Row renders the HM cluster Hyperpart (wrapping
        # horizontal group). align=center is the cluster default; other
        # alignments ride data-dz-align.
        align = "" if r.align == "center" else f' data-dz-align="{ctx.escape_attr(r.align)}"'
        body = "".join(self._emit(c, ctx) for c in r.children)  # type: ignore[arg-type]
        return f'<div class="dz-cluster" data-dz-gap="{ctx.escape_attr(r.gap)}"{align}>{body}</div>'

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
        # ADR-0049 D3 → convergence C2.4: when the region carries a grid
        # mount, the root is an HM grid root — dz-grid.js and its extensions
        # (all delegated, state-in-DOM) resolve every behaviour against these
        # attributes. The dzTable Alpine `x-data` wrapper this originally
        # emitted is retired (its last bindings converged in C2.1–C2.3).
        mount_attr = self._dztable_mount_attrs(r.mount, ctx) if r.mount is not None else ""
        body_html = self._emit(r.body, ctx)  # type: ignore[arg-type]
        return f'<section class="{cls}"{mount_attr}{data_attr}>{body_html}</section>'

    @staticmethod
    def _dztable_mount_attrs(m: DzTableMount, ctx: RenderContext) -> str:
        table_id = ctx.escape_attr(m.table_id)
        endpoint = ctx.escape_attr(m.endpoint)
        return (
            f' id="{table_id}"'
            # Convergence C1.1: `data-dz-grid` marks this region as an HM grid
            # root — dz-grid.js (delegated) owns sort / selection / bulk /
            # pagination within it.
            # C1.3: `data-dz-grid-url` opts the grid into URL-synced state —
            # this mount renders ONLY for full-page list surfaces (the one
            # DzTableMount construction site is `_build_list`), which satisfies
            # the one-url-synced-grid-per-page constraint; workspace/dashboard
            # regions stay off until the URL keys are namespaced.
            " data-dz-grid data-dz-grid-url"
            # C2.3: the inline-edit extension's commit base — the entity's
            # API root (commits PUT {base}/{id}, the standard update route).
            f' data-dz-grid-edit-url="{endpoint}"'
            ' data-dz-bulk-count="0"'
        )

    def _emit_drawer(self, d: Drawer, ctx: RenderContext) -> str:
        cls = f"dz-drawer dz-drawer--side-{d.side}"
        return f'<aside class="{cls}">{self._emit(d.body, ctx)}</aside>'  # type: ignore[arg-type]

    def _emit_modal(self, m: Modal, ctx: RenderContext) -> str:
        cls = f"dz-modal dz-modal--size-{m.size}"
        return f'<div class="{cls}" role="dialog">{self._emit(m.body, ctx)}</div>'  # type: ignore[arg-type]

    def _emit_tabs(self, t: Tabs, ctx: RenderContext) -> str:
        """Render an eager (content-inline) tab strip using the HM `tabs`
        Hyperpart contract (`.dz-tabs*`), driven by the ingested
        `dz-tabs.js` controller — the same honest link-strip as
        `_emit_lazy_tab_panel`, but each panel carries its content inline
        (no `hx-get`). Buttons are `<button aria-current>`, panels toggle
        via the native `hidden` attribute; no `role=tablist`, no inline JS.

        Panel ids are `dz-tab-<key>` (the generic Tabs fragment carries no
        region namespace). Switching is safe regardless — `dz-tabs.js`
        scopes every query to the clicked tab's `closest('.dz-tabs')` root
        — but two eager Tabs on one page sharing a tab key would emit
        duplicate DOM ids (HTML-invalid, cosmetic). This fragment is the
        rare latent inline-`tabs` fallback; the live `tabbed_list` path is
        `_emit_lazy_tab_panel`, which is region-namespaced.
        """
        tab_buttons = "".join(
            f'<button type="button" class="dz-tabs__tab"'
            f"{' aria-current="true"' if i == 0 else ''} "
            f'data-dz-tab-target="dz-tab-{ctx.escape_attr(key)}">'
            f"{ctx.escape(key)}</button>"
            for i, (key, _panel) in enumerate(t.tabs)
        )
        panels = "".join(
            f'<div id="dz-tab-{ctx.escape_attr(key)}" class="dz-tabs__panel"'
            f"{'' if i == 0 else ' hidden'}>"
            f"{self._emit(panel, ctx)}</div>"  # type: ignore[arg-type]
            for i, (key, panel) in enumerate(t.tabs)
        )
        return f'<div class="dz-tabs"><div class="dz-tabs__list">{tab_buttons}</div>{panels}</div>'

    def _emit_icon(self, i: Icon, ctx: RenderContext) -> str:
        return lucide_icon_html(i.name, cls=f"dz-icon dz-icon--size-{i.size}")

    def _emit_badge(self, b: Badge, ctx: RenderContext) -> str:
        cls = f"dz-badge dz-badge--variant-{b.variant}"
        return f'<span class="{cls}">{ctx.escape(b.label)}</span>'

    def _emit_empty_state(self, e: EmptyState, ctx: RenderContext) -> str:
        action_html = self._emit(e.action, ctx) if e.action is not None else ""  # type: ignore[arg-type]
        icon_html = lucide_icon_html(e.icon, cls="dz-empty-state__icon") if e.icon else ""
        return (
            f'<div class="dz-empty-state">'
            f"{icon_html}"
            f'<h3 class="dz-empty-state__title">{ctx.escape(e.title)}</h3>'
            f'<p class="dz-empty-state__description">{ctx.escape(e.description)}</p>'
            f'<div class="dz-empty-state__action">{action_html}</div>'
            f"</div>"
        )

    def _emit_skeleton(self, s: Skeleton, ctx: RenderContext) -> str:
        # Adopts the design system's canonical `.dz-skeleton` placeholder (the
        # HM skeleton Hyperpart): each line is a `dz-skeleton` element shaped
        # `text`, stacked by `dz-skeleton-lines`. (The prior `dz-skeleton__line`
        # child class had no CSS rule — the lines rendered invisible.)
        lines = "".join(
            '<div class="dz-skeleton" data-dz-shape="text"></div>' for _ in range(s.lines)
        )
        return f'<div class="dz-skeleton-lines">{lines}</div>'

    def _emit_lazy_tab_panel(self, p: LazyTabPanel, ctx: RenderContext) -> str:
        """Render a LazyTabPanel using the HM `tabs` Hyperpart contract.

        An honest link-strip (Tabs Phase 2 convergence): the tabs are
        `<button class="dz-tabs__tab">`s with `aria-current="true"` on the
        active one — NOT a `role="tablist"` the widget can't back with
        roving-tabindex/arrow-key navigation. Panel switching is driven by
        the ingested `dz-tabs.js` controller (delegated, scoped per
        `.dz-tabs` root), so there is no inline `onclick` JS here.

        Each tab points at its panel via `data-dz-tab-target`; each panel
        (`.dz-tabs__panel`) fetches its own content via `hx-get`. The
        first tab fires `load` (and is visible); subsequent panels carry
        the native `hidden` attribute and fire `hx-trigger="intersect
        once"` — revealing a hidden panel is what triggers its lazy load.

        DOM ids: `tabs-<region>` for the `.dz-tabs` root, `tab-<region>-<key>`
        for each panel.
        """
        rname = ctx.escape_attr(p.region_name)

        tab_buttons = "".join(
            f'<button type="button" '
            f'class="dz-tabs__tab"{' aria-current="true"' if i == 0 else ""} '
            f'data-dz-tab-target="tab-{rname}-{ctx.escape_attr(tab.key)}">'
            f"{ctx.escape(tab.label)}</button>"
            for i, tab in enumerate(p.tabs)
        )

        panels = "".join(
            f'<div id="tab-{rname}-{ctx.escape_attr(tab.key)}" '
            f'class="dz-tabs__panel"{"" if i == 0 else " hidden"} '
            f'hx-get="{ctx.escape_attr(str(tab.endpoint))}" '
            f'hx-trigger="{"load" if (tab.eager or i == 0) else "intersect once"}" '
            f'hx-swap="innerHTML">'
            f'<div class="dz-tabs__loading">'
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
            f'<div class="dz-tabs" id="tabs-{rname}">'
            f'<div class="dz-tabs__list">{tab_buttons}</div>'
            f"{panels}"
            f"</div>"
        )
