"""Dashboard-family render mixin.

Houses the 6 dashboard primitives — workspace-shaped composite regions
that mostly forward to typed children carrying pre-resolved data:

  - _emit_dashboard_grid
  - _emit_dashboard_card
  - _emit_cohort_strip_region
  - _emit_day_timeline_region
  - _emit_entity_card_region
  - _emit_task_inbox_region

All methods only call `self._emit(child, ctx)` for child recursion;
dispatch goes back through the match block in `_emit.py`.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.icon_html import lucide_icon_html
from dazzle.render.fragment.ingest import CohortStrip as CohortStripSeam
from dazzle.render.fragment.ingest import DashboardCard as DashboardCardSeam
from dazzle.render.fragment.ingest import TaskInbox as TaskInboxSeam
from dazzle.render.fragment.ingest import (
    render_cohort_strip,
    render_dashboard_card,
    render_task_inbox,
)
from dazzle.render.fragment.primitives import (
    CohortStripRegion,
    DashboardCard,
    DashboardGrid,
    DayTimelineRegion,
    EntityCardRegion,
    TaskInboxRegion,
)

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


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
        keys off it), `role="application"` + `aria-label` for a11y, and
        optional `hx-ext="sse" sse-connect="..."` when the workspace
        declared an `sse_url`. Cards inside are rendered as
        DashboardCard primitives."""
        from dazzle.perf.tracer import dazzle_span

        with dazzle_span("region.render", region_kind=type(g).__name__):
            return self._emit_dashboard_grid_impl(g, ctx)

    def _emit_dashboard_grid_impl(self, g: DashboardGrid, ctx: RenderContext) -> str:
        sse_attrs = ""
        if g.sse_url:
            sse_attrs = f' hx-ext="sse" sse-connect="{ctx.escape_attr(g.sse_url)}"'
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
            f"{editable_attr}"
            f"{sse_attrs}>"
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
             (skeleton + lazy/eager HTMX trigger).
          3. `<div class="dz-card-resize">` aria-hidden trailing handle.

        Trigger is `'load'` when `eager=True` (above-the-fold; #864) and
        `'intersect once'` when lazy. SSE adds three entity events to
        the trigger when the workspace's grid carries `sse_url`."""
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

        # ── HTMX trigger: 'load' (eager) or 'intersect once' (lazy),
        #    plus three SSE entity events when sse_enabled.
        trigger = "load" if c.eager else "intersect once"
        if c.sse_enabled:
            trigger += ", sse:entity.created, sse:entity.updated, sse:entity.deleted"
        # #1391: declarative live-refresh — append a polling clause so HTMX
        # re-fetches the region body every N seconds. Parser floors this at 5s.
        if c.refresh_interval:
            trigger += f", every {c.refresh_interval}s"

        body_html = (
            f'<div class="dz-card-body" '
            f'id="region-{ctx.escape_attr(c.name)}-{ctx.escape_attr(c.card_id)}" '
            f'data-display="{ctx.escape_attr(c.display.lower())}" '
            f'hx-get="{ctx.escape_attr(c.hx_endpoint)}" '
            f'hx-trigger="{ctx.escape_attr(trigger)}" '
            f'hx-swap="innerHTML">'
            f'<div class="dz-card-skeleton">'
            f'<div class="dz-card-skeleton-line w-3-4"></div>'
            f'<div class="dz-card-skeleton-line is-thin"></div>'
            f'<div class="dz-card-skeleton-line is-thin w-5-6"></div>'
            f"</div>"
            f"</div>"
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

        Outer wrapper carries `data-dz-region-name` so the lens-toggle
        HTMX swap can target it. Lens toggle is a `<div role="tablist">`
        of buttons; each button fires an `hx-get` to the same region
        endpoint with `?lens=<id>` and swaps the body. Cells row is a
        horizontal-scroll flex strip on wide widths, wraps on narrow.

        Cells with non-empty `drill_url` wrap in an `<a>` for keyboard-
        navigable drill-down to the entity_card surface (#1017)."""
        endpoint_str = ctx.escape_attr(str(c.endpoint))
        region_name_attr = ctx.escape_attr(c.region_name)
        lens_buttons: list[str] = []
        for lens in c.lenses:
            cls = "dz-cohort-strip-lens"
            if lens.is_active:
                cls += " is-active"
            active_attr = ' aria-pressed="true"' if lens.is_active else ' aria-pressed="false"'
            lens_buttons.append(
                f'<button type="button" role="tab" class="{cls}"{active_attr} '
                f'data-lens-id="{ctx.escape_attr(lens.id)}" '
                f'hx-get="{endpoint_str}?lens={ctx.escape_attr(lens.id)}" '
                f'hx-target="#region-{region_name_attr}-body" '
                f'hx-swap="innerHTML">'
                f"{ctx.escape(lens.label)}"
                f"</button>"
            )
        lens_bar = (
            f'<div class="dz-cohort-strip-lenses" role="tablist" '
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
                    cell_parts.append(
                        f'<a class="dz-cohort-strip-cell" '
                        f'href="{ctx.escape_attr(cell.drill_url)}" '
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

        body = (
            f"{lens_bar}"
            f'<div class="dz-cohort-strip-body" id="region-{region_name_attr}-body">'
            f"{cells_html}"
            f"</div>"
        )
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
        region_name_attr = ctx.escape_attr(t.region_name)
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
                    slot_parts.append(
                        f'<a class="{cls}" '
                        f'data-dz-position="{ctx.escape_attr(pos)}" '
                        f'data-slot-id="{ctx.escape_attr(slot.slot_id)}" '
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

        return (
            f'<div class="dz-day-timeline-region" '
            f'data-dz-region-name="{region_name_attr}">'
            f"{body}"
            f"</div>"
        )

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
        region_name_attr = ctx.escape_attr(p.region_name)
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

        return (
            f'<div class="dz-entity-card-region" '
            f'data-dz-region-name="{region_name_attr}">'
            f"{heading_html}"
            f"{body}"
            f"</div>"
        )

    def _emit_task_inbox_region(self, t: TaskInboxRegion, ctx: RenderContext) -> str:
        """Render a TaskInboxRegion (#1015).

        The summary-chip row sits above the items list when any
        `count_as` source resolves a non-zero count. Each chip
        renders as a single pill with the count + label, optionally
        wrapped in an `<a>` for drill-down to the source surface.

        Items render as a `<ul>` of typed task rows: icon + title +
        meta + urgency-tone tint via `data-dz-urgency`. When there
        are zero items AND zero summary chips, the empty-state path
        emits a single paragraph in place of both."""
        chip_parts: list[str] = []
        for chip in t.summary_chips:
            inner = (
                f'<span class="dz-task-inbox-chip-count">{chip.count}</span>'
                f'<span class="dz-task-inbox-chip-label">{ctx.escape(chip.label)}</span>'
            )
            if chip.drill_url:
                chip_parts.append(
                    f'<a class="dz-task-inbox-chip" '
                    f'href="{ctx.escape_attr(chip.drill_url)}" '
                    f'data-dz-chip-id="{ctx.escape_attr(chip.chip_id)}">'
                    f"{inner}"
                    f"</a>"
                )
            else:
                chip_parts.append(
                    f'<div class="dz-task-inbox-chip" '
                    f'data-dz-chip-id="{ctx.escape_attr(chip.chip_id)}">'
                    f"{inner}"
                    f"</div>"
                )
        chips_html = (
            f'<div class="dz-task-inbox-chips">{"".join(chip_parts)}</div>' if chip_parts else ""
        )

        item_parts: list[str] = []
        for item in t.items:
            urgency = (
                item.urgency if item.urgency in ("overdue", "due", "soon", "later") else "later"
            )
            meta_html = (
                f'<div class="dz-task-inbox-item-meta">{ctx.escape(item.meta)}</div>'
                if item.meta
                else ""
            )
            icon_html = lucide_icon_html(item.icon, cls="dz-task-inbox-item-icon")
            inner = (
                f"{icon_html}"
                f'<div class="dz-task-inbox-item-body">'
                f'<div class="dz-task-inbox-item-title">{ctx.escape(item.title)}</div>'
                f"{meta_html}"
                f"</div>"
            )
            if item.drill_url:
                item_parts.append(
                    f'<li class="dz-task-inbox-item" '
                    f'data-dz-urgency="{ctx.escape_attr(urgency)}" '
                    f'data-dz-item-id="{ctx.escape_attr(item.item_id)}">'
                    f'<a class="dz-task-inbox-item-link" '
                    f'href="{ctx.escape_attr(item.drill_url)}">'
                    f"{inner}"
                    f"</a></li>"
                )
            else:
                item_parts.append(
                    f'<li class="dz-task-inbox-item" '
                    f'data-dz-urgency="{ctx.escape_attr(urgency)}" '
                    f'data-dz-item-id="{ctx.escape_attr(item.item_id)}">'
                    f"{inner}"
                    f"</li>"
                )

        if not t.items and not t.summary_chips:
            body = f'<p class="dz-task-inbox-empty">{ctx.escape(t.empty_message)}</p>'
        elif not t.items:
            body = chips_html  # chips only — no items list
        else:
            body = f'{chips_html}<ul class="dz-task-inbox-items">{"".join(item_parts)}</ul>'

        return render_task_inbox(
            TaskInboxSeam(
                region_name=t.region_name,
                body_html=body,
            )
        )
