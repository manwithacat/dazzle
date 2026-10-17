"""Dashboard-family render mixin.

Houses the 5 dashboard primitives — workspace-shaped composite regions
that mostly forward to typed children carrying pre-resolved data:

  - _emit_dashboard_grid
  - _emit_dashboard_card
  - _emit_cohort_strip_region
  - _emit_day_timeline_region
  - _emit_entity_card_region

All methods only call `self._emit(child, ctx)` for child recursion;
dispatch goes back through the match block in `_emit.py`.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.ingest import CohortStrip as CohortStripSeam
from dazzle.render.fragment.ingest import DashboardCard as DashboardCardSeam
from dazzle.render.fragment.ingest import DayTimeline as DayTimelineSeam
from dazzle.render.fragment.ingest import EntityCard as EntityCardSeam
from dazzle.render.fragment.ingest import (
    render_cohort_strip,
    render_dashboard_card,
    render_day_timeline,
    render_entity_card,
)
from dazzle.render.fragment.ingest.emit import drill_anchor_open_attrs
from dazzle.render.fragment.primitives import (
    CohortStripRegion,
    DashboardCard,
    DashboardGrid,
    DayTimelineRegion,
    EntityCardRegion,
)
from dazzle.render.fragment.primitives.data import region_poll_id
from dazzle.render.fragment.renderer._render_interactive import (
    _with_leftover_honest_temporal,
)

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


def _dashboard_card_first_fetch_trigger(c: DashboardCard) -> str:
    """The one-shot first fetch of a skeleton card body (#864): ``load`` when
    eager (above the fold), ``intersect once`` when lazy."""
    return "load" if c.eager else "intersect once"


class _RenderDashboardMixin:
    """Mixin adding the 6 dashboard-family `_emit_*` methods to
    `FragmentRenderer`. Same pattern as `_RenderLayoutMixin`.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    def _emit_dashboard_grid(self, g: DashboardGrid, ctx: RenderContext) -> str:
        """Render a DashboardGrid matching legacy `_content.html` card-grid
        block byte-for-byte (Phase 4B.5.b.2.ii).

        Outer wrapper carries `data-grid-container` (the JS grid handler
        keys off it) and `role="application"` + `aria-label` for a11y.
        Cards inside are rendered as DashboardCard primitives."""
        from dazzle.perf.tracer import dazzle_span

        with dazzle_span("region.render", region_kind=type(g).__name__):
            return self._emit_dashboard_grid_impl(g, ctx)

    def _emit_dashboard_grid_impl(self, g: DashboardGrid, ctx: RenderContext) -> str:
        # #1204: data-grid-editable is the contract between Python (server-
        # rendered cards) and JS (dashboard-builder.js dynamic card injection)
        # for whether the Remove-card chrome should appear at all. The JS
        # reads this on the grid container to decide whether to add the X
        # button when the user adds a new card via the picker.
        editable_attr = (
            ' data-grid-editable="true"' if g.edit_enabled else ' data-grid-editable="false"'
        )
        cards_html = "".join(self._emit(c, ctx) for c in g.cards)
        # Trust contract: leading_html is built by render_master_detail_shell
        # (escaped region names/titles); not author-supplied raw markup.
        leading = getattr(g, "leading_html", "") or ""
        return (
            f'<div class="dz-dashboard-grid" '
            f"data-grid-container "
            f'role="application" '
            f'aria-label="Dashboard card grid"'
            f"{editable_attr}>"
            f"{leading}"
            f"{cards_html}"
            f"</div>"
        )

    def _emit_dashboard_card(self, c: DashboardCard, ctx: RenderContext) -> str:
        """Render a DashboardCard matching legacy `_content.html` per-card
        block byte-for-byte (Phase 4B.5.b.2.ii).

        Three layers of chrome:
          1. Outer `<div class="dz-card-wrapper">` carrying drag/resize
             contract attrs (`data-card-id`, `data-card-region`,
             `data-card-col-span`, `data-card-row-order`,
             `style="grid-column: span N / span N"`, `tabindex="0"`,
             optional `is-animating` + caller-supplied `css_class`).
          2. `<article class="dz-card">` with header (drag handle +
             titles + remove button), optional notice band, and body
             (a self-replacing skeleton loader) and, when polling, a hidden
             poller sibling of the body.
          3. `<div class="dz-card-resize">` aria-hidden trailing handle.

        The skeleton's trigger is `'load'` when `eager=True` (above-the-fold;
        #864) and `'intersect once'` when lazy; `refresh_interval` adds the
        poller (`every Ns`). Neither is an ancestor of the region (#1802)."""
        wrapper_class = (
            f"dz-card-wrapper {c.css_class} is-animating"
            if c.css_class
            else "dz-card-wrapper is-animating"
        )

        # ── Header: drag handle, titles (eyebrow + h3), remove button
        eyebrow_html = (
            f'<span class="dz-card-eyebrow">{ctx.escape(c.eyebrow)}</span>' if c.eyebrow else ""
        )
        # #1204: actions block (Remove-card × button) is permission-gated.
        # When `edit_enabled` is False (safe default), the entire
        # `dz-card-actions` div is omitted — no hover-flash, no a11y tab
        # target, no surprise screen-reader click target. Page-route call
        # site flips this from the existing `is_superuser` check.
        actions_html = (
            (
                '<div class="dz-card-actions">'
                '<button data-test-id="dz-card-remove" '
                'class="dz-card-action-button" aria-label="Remove card">'
                '<svg width="14" height="14" fill="none" stroke="currentColor" '
                'viewBox="0 0 24 24" aria-hidden="true">'
                '<path stroke-linecap="round" stroke-linejoin="round" '
                'stroke-width="2" d="M6 18L18 6M6 6l12 12"/>'
                "</svg>"
                '<span class="visually-hidden">Remove card</span>'
                "</button>"
                "</div>"
            )
            if c.edit_enabled
            else ""
        )
        header_html = (
            f'<div class="dz-card-header" data-test-id="dz-card-drag-handle">'
            f'<div class="dz-card-titles">'
            f"{eyebrow_html}"
            f'<h3 id="card-title-{ctx.escape_attr(c.card_id)}" '
            f'class="dz-card-title">{ctx.escape(c.title)}</h3>'
            f"</div>"
            f"{actions_html}"
            f"</div>"
        )

        # ── Optional notice band (#906)
        notice_html = ""
        if c.notice and c.notice.title:
            tone = c.notice.tone or "neutral"
            body_html = (
                f'<div class="dz-card-notice-body">{ctx.escape(c.notice.body)}</div>'
                if c.notice.body
                else ""
            )
            notice_html = (
                f'<div class="dz-notice-band dz-card-notice" '
                f'data-dz-notice-tone="{ctx.escape_attr(tone)}" role="note">'
                f'<div class="dz-card-notice-title">{ctx.escape(c.notice.title)}</div>'
                f"{body_html}"
                f"</div>"
            )

        ssr_html = getattr(c, "ssr_html", "") or ""

        # Leftover-honest temporal (cycle 2183). Bare
        # hx-get="{c.hx_endpoint}" used to drop include_closed /
        # as_of and invent open-only / current after SSE / poll /
        # lazy-load refresh. Leftover junk must not invent. Valid
        # true / YYYY-MM-DD ride; leftover junk (zzz / 2abc /
        # maybe / not-a-date) omits.
        hx_get = _with_leftover_honest_temporal(
            ctx.escape_attr(c.hx_endpoint),
            getattr(c, "include_closed", ""),
            getattr(c, "as_of", ""),
            escape_attr=ctx.escape_attr,
        )

        # data-dz-region on the body slot: HTMX region fetches return typed
        # body only (no nested chrome), so this is the stable JS / closest
        # filter handle. Unique id remains region-{name}-{card_id}.
        #
        # #1802: the body is a pure swap target — it carries no hx-*. Under
        # htmx 4 `implicitInheritance` (dz-csrf.js) every hx-* on an ancestor
        # is inherited by each control in the swapped region, so a body with
        # `hx-trigger="load"` fired every triggerless verb button (queue
        # transitions, row deletes) on swap-in, and its `hx-get` beat their
        # own verb. The first fetch rides the SKELETON, which targets the body
        # and is replaced by the response (a self-replacing loader, never an
        # ancestor of what it loads; it is visible, so `intersect once`
        # works); the `every Ns` poll rides a hidden SIBLING.
        body_id = f"region-{c.name}-{c.card_id}"
        body_id_attr = ctx.escape_attr(body_id)
        fetch_attrs = f'hx-get="{hx_get}" hx-target="#{body_id_attr}" hx-swap="innerHTML"'
        inner = (
            ssr_html
            if ssr_html
            else (
                f'<div class="dz-card-skeleton" {fetch_attrs} '
                f'hx-trigger="{_dashboard_card_first_fetch_trigger(c)}">'
                '<div class="dz-card-skeleton-line w-3-4"></div>'
                '<div class="dz-card-skeleton-line is-thin"></div>'
                '<div class="dz-card-skeleton-line is-thin w-5-6"></div>'
                "</div>"
            )
        )
        body_html = (
            f'<div class="dz-card-body" '
            f'id="{body_id_attr}" '
            f'data-dz-region data-dz-region-name="{ctx.escape_attr(c.name)}" '
            f'data-display="{ctx.escape_attr(c.display.lower())}">'
            f"{inner}"
            f"</div>"
        )
        if c.refresh_interval:
            body_html += (
                f'<div hidden id="{ctx.escape_attr(region_poll_id(body_id))}" '
                f"data-dz-region-poll {fetch_attrs} "
                f'hx-trigger="every {int(c.refresh_interval)}s"></div>'
            )

        # #1494: addressable wrapper id (`card-{name}-{card_id}`, derivable
        # from the body's `region-{name}-{card_id}` hx-target) so an empty
        # `when_empty: suppress` region can self-remove via htmx OOB-delete.
        # Dual-lock sole-emitter roots data-dz-dashboard-card on the wrapper.
        attrs = (
            f'id="card-{ctx.escape_attr(c.name)}-{ctx.escape_attr(c.card_id)}" '
            f'data-card-id="{ctx.escape_attr(c.card_id)}" '
            f'data-card-region="{ctx.escape_attr(c.name)}" '
            f'data-card-col-span="{c.col_span}" '
            f'data-card-row-order="{c.row_order}" '
            f'class="{ctx.escape_attr(wrapper_class)}" '
            f'style="grid-column: span {c.col_span} / span {c.col_span};" '
            f'tabindex="0"'
        )
        article = (
            f'<article class="dz-card" role="article" '
            f'aria-labelledby="card-title-{ctx.escape_attr(c.card_id)}">'
            f"{header_html}"
            f"{notice_html}"
            f"{body_html}"
            f"</article>"
            f'<div class="dz-card-resize" aria-hidden="true"></div>'
        )
        return render_dashboard_card(DashboardCardSeam(attrs=attrs, body_html=article))

    def _emit_cohort_strip_region(self, c: CohortStripRegion, ctx: RenderContext) -> str:
        """Render a CohortStripRegion (#1018).

        Lens toggle is an honest selection strip (HM stem
        selection-strip-honest): a labelled group of `<button>`s, the
        active one carrying `aria-current="true"` — no fake
        `role="tablist"` / `role="tab"`. Each button fires an `hx-get`
        to the same region endpoint with `?lens=<id>` and swaps
        `innerHTML` of `closest [data-dz-region]` — the host slot (the
        dashboard card body, or the non-HTMX region wrapper). The HTMX
        region response is the whole strip root (lens bar included), so
        targeting the slot replaces the strip rather than nesting a
        second one inside it (#1795 U9, ADR-0054 rule 2). The endpoint
        honours `?lens=` server-side, so the re-rendered lens bar
        carries the active state — no OOB update is needed. Cells row
        is a horizontal-scroll flex strip on wide widths, wraps on
        narrow.

        Cells with non-empty `drill_url` wrap in an `<a>` for keyboard-
        navigable drill-down to the entity_card surface (#1017)."""
        endpoint_str = ctx.escape_attr(str(c.endpoint))
        lens_buttons: list[str] = []
        for lens in c.lenses:
            cls = "dz-cohort-strip-lens"
            if lens.is_active:
                cls += " is-active"
            active_attr = ' aria-current="true"' if lens.is_active else ""
            # Leftover-honest temporal (cycle 2182). Bare
            # hx-get="{endpoint}?lens=" used to drop include_closed /
            # as_of and invent open-only / current after a lens change.
            # Leftover junk must not invent. Valid true / YYYY-MM-DD
            # ride; leftover junk (zzz / 2abc / maybe / not-a-date)
            # omits.
            lens_href = _with_leftover_honest_temporal(
                f"{endpoint_str}?lens={ctx.escape_attr(lens.id)}",
                getattr(c, "include_closed", ""),
                getattr(c, "as_of", ""),
                escape_attr=ctx.escape_attr,
            )
            lens_buttons.append(
                f'<button type="button" class="{cls}"{active_attr} '
                f'data-lens-id="{ctx.escape_attr(lens.id)}" '
                f'hx-get="{lens_href}" '
                f'hx-target="closest [data-dz-region]" '
                f'hx-swap="innerHTML">'
                f"{ctx.escape(lens.label)}"
                f"</button>"
            )
        lens_bar = (
            f'<div class="dz-cohort-strip-lenses" role="group" '
            f'aria-label="Lens toggle">'
            f"{''.join(lens_buttons)}"
            f"</div>"
        )

        if not c.cells:
            cells_html = f'<p class="dz-cohort-strip-empty">{ctx.escape(c.empty_message)}</p>'
        else:
            cell_parts: list[str] = []
            for cell in c.cells:
                tone = cell.tone if cell.tone in ("good", "warn", "bad") else "neutral"
                initials = (
                    ctx.escape(cell.avatar_initials)
                    if cell.avatar_initials
                    else ctx.escape(cell.member_name[:2].upper())
                )
                year_html = (
                    f'<div class="dz-cohort-strip-cell-subtitle">{ctx.escape(cell.subtitle)}</div>'
                    if cell.subtitle
                    else ""
                )
                # #1148: pre-rendered row_action button HTML, when
                # present, appears after the primary value. Adapter
                # pre-escapes attributes; renderer passes through.
                action_block = (
                    f'<div class="dz-cohort-strip-cell-action">{cell.action_html}</div>'
                    if cell.action_html
                    else ""
                )
                inner = (
                    f'<div class="dz-cohort-strip-cell-halo">{initials}</div>'
                    f'<div class="dz-cohort-strip-cell-name">{ctx.escape(cell.member_name)}</div>'
                    f"{year_html}"
                    f'<div class="dz-cohort-strip-cell-primary" '
                    f'data-dz-tone="{ctx.escape_attr(tone)}">'
                    f"{ctx.escape(cell.primary_value)}"
                    f"</div>"
                    f"{action_block}"
                )
                if cell.drill_url:
                    open_attrs = drill_anchor_open_attrs(str(cell.drill_url), kind="cohort")
                    cell_parts.append(
                        f'<a class="dz-cohort-strip-cell" '
                        f'href="{ctx.escape_attr(cell.drill_url)}" '
                        f"{open_attrs} "
                        f'data-member-id="{ctx.escape_attr(cell.member_id)}">'
                        f"{inner}"
                        f"</a>"
                    )
                else:
                    cell_parts.append(
                        f'<div class="dz-cohort-strip-cell" '
                        f'data-member-id="{ctx.escape_attr(cell.member_id)}">'
                        f"{inner}"
                        f"</div>"
                    )
            cells_html = f'<div class="dz-cohort-strip-cells">{"".join(cell_parts)}</div>'

        body = f'{lens_bar}<div class="dz-cohort-strip-body">{cells_html}</div>'
        return render_cohort_strip(CohortStripSeam(region_name=c.region_name, body_html=body))

    def _emit_day_timeline_region(self, t: DayTimelineRegion, ctx: RenderContext) -> str:
        """Render a DayTimelineRegion (#1016).

        Vertical chronological scroll of slot cards. The active slot
        (at most one) carries `data-dz-position="active"` so project
        CSS can highlight it without DOM-walking. Slots before the
        active one render in `position="before"` (collapsed-summary);
        slots after render in `position="after"` (previewable).

        Each slot's body is treated as a pre-rendered HTML fragment
        produced by the runtime adapter — this primitive does not
        re-escape it. Empty timelines emit a single empty-state
        paragraph."""
        if not t.slots:
            body = f'<p class="dz-day-timeline-empty">{ctx.escape(t.empty_message)}</p>'
        else:
            slot_parts: list[str] = []
            for slot in t.slots:
                pos = slot.position if slot.position in ("before", "active", "after") else "after"
                cls = f"dz-day-timeline-slot is-{pos}"
                inner = (
                    f'<div class="dz-day-timeline-slot-label">{ctx.escape(slot.label)}</div>'
                    f'<div class="dz-day-timeline-slot-body">{slot.body}</div>'
                )
                # #1148: pre-rendered row_action button HTML, when
                # present, is emitted after the body. Adapter pre-
                # escaped attributes; renderer just passes through.
                if slot.action_html:
                    inner += f'<div class="dz-day-timeline-slot-action">{slot.action_html}</div>'
                if slot.drill_url:
                    open_attrs = drill_anchor_open_attrs(str(slot.drill_url), kind="day_timeline")
                    slot_parts.append(
                        f'<a class="{cls}" '
                        f'data-dz-position="{ctx.escape_attr(pos)}" '
                        f'data-slot-id="{ctx.escape_attr(slot.slot_id)}" '
                        f"{open_attrs} "
                        f'href="{ctx.escape_attr(slot.drill_url)}">'
                        f"{inner}"
                        f"</a>"
                    )
                else:
                    slot_parts.append(
                        f'<div class="{cls}" '
                        f'data-dz-position="{ctx.escape_attr(pos)}" '
                        f'data-slot-id="{ctx.escape_attr(slot.slot_id)}">'
                        f"{inner}"
                        f"</div>"
                    )
            body = f'<ol class="dz-day-timeline-slots">{"".join(slot_parts)}</ol>'

        return render_day_timeline(DayTimelineSeam(region_name=t.region_name, body_html=body))

    def _emit_entity_card_region(self, p: EntityCardRegion, ctx: RenderContext) -> str:
        """Render an EntityCardRegion (#1017).

        Domain-agnostic 360° single-entity composite — two-column
        responsive layout. Sections marked `is_omitted=True` are
        skipped entirely (used for optional sections that resolved
        zero rows). Each section's body is pre-rendered HTML produced
        by the runtime adapter — the primitive does not double-escape
        it.

        Sections carry `data-dz-mode` and `data-dz-column` so
        project CSS owns the breakpoint layout and per-mode density
        styling. The wrapper carries `data-dz-region-name` and an
        optional heading derived from `record_label`."""
        heading_html = (
            f'<h3 class="dz-entity-card-heading">{ctx.escape(p.record_label)}</h3>'
            if p.record_label
            else ""
        )

        valid_modes = {"halo", "flags", "mini_bars", "stamps", "thread_summary", "quick_actions"}
        section_parts: list[str] = []
        for section in p.sections:
            if section.is_omitted:
                continue
            mode = section.mode if section.mode in valid_modes else "halo"
            column = section.column if section.column in ("main", "sidebar") else "main"
            section_parts.append(
                f'<section class="dz-entity-card-section" '
                f'data-section-id="{ctx.escape_attr(section.section_id)}" '
                f'data-dz-mode="{ctx.escape_attr(mode)}" '
                f'data-dz-column="{ctx.escape_attr(column)}">'
                f'<header class="dz-entity-card-section-label">'
                f"{ctx.escape(section.label)}"
                f"</header>"
                f'<div class="dz-entity-card-section-body">{section.body}</div>'
                f"</section>"
            )

        body = (
            f'<div class="dz-entity-card-sections">{"".join(section_parts)}</div>'
            if section_parts
            else '<p class="dz-entity-card-empty">No record context available.</p>'
        )

        return render_entity_card(
            EntityCardSeam(
                region_name=p.region_name,
                body_html=f"{heading_html}{body}",
            )
        )
