"""Tables-family render mixin.

Houses the 17 tabular + data-display primitives — anything that
emits a Table/Grid/List structure or a metric/card tile:

  - _emit_table, _emit_kpi
  - _emit_pivot_table, _emit_pivot_table_region
  - _emit_list_region, _emit_grid_region
  - _emit_detail_grid, _emit_status_list, _emit_activity_feed
  - _emit_profile_card, _emit_action_card, _emit_action_grid
  - _emit_metrics_grid, _emit_metric_tile
  - _emit_bar_track, _emit_stage_bar
  - _emit_queue_region

All methods only call `self._emit(child, ctx)` for recursion, plus
the module-level helper `_render_references` from `._helpers`.

This is the LAST family extraction (#1064 PR 9). After this lands,
`_emit.py` is a pure dispatch shell.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    KPI,
    ActionCard,
    ActionGrid,
    ActivityFeed,
    BarTrack,
    DetailGrid,
    GridRegion,
    ListRegion,
    MetricsGrid,
    MetricTile,
    PivotTable,
    PivotTableRegion,
    ProfileCard,
    QueueRegion,
    SortHeader,
    StageBar,
    StatusList,
    Table,
)
from dazzle.render.fragment.renderer._helpers import _render_references

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


class _RenderTablesMixin:
    """Mixin adding the 17 tables-family `_emit_*` methods to
    `FragmentRenderer`. Same pattern as the other render mixins.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    def _emit_table(self, t: Table, ctx: RenderContext) -> str:
        # Issue #1029 phase 6: columns can be plain strings (legacy
        # static labels) or SortHeader primitives (clickable column
        # headers with aria-sort + hx-get). Per-cell dispatch keeps
        # the legacy string-column shape backwards-compatible.
        head_cells_parts: list[str] = []
        # Issue #1029 phase 7: bulk_select prepends a select-all
        # checkbox header cell. Alpine `dzTable` controller owns
        # bulkCount + toggleSelectAll.
        if t.bulk_select:
            head_cells_parts.append(
                '<th scope="col" class="dz-table-th-select">'
                '<input type="checkbox" class="dz-table-col-menu-checkbox" '
                '@change="toggleSelectAll($event.target.checked)" '
                'aria-label="Select all rows" />'
                "</th>"
            )
        for c in t.columns:
            if isinstance(c, SortHeader):
                head_cells_parts.append(f"<th>{self._emit(c, ctx)}</th>")
            else:
                head_cells_parts.append(f"<th>{ctx.escape(str(c))}</th>")
        head_cells = "".join(head_cells_parts)
        # Issue #1029 phase 1: row_links — when set, each row carries
        # an hx-get on the <tr> so clicking navigates to the detail
        # URL via htmx (full-page swap into <body>). Wrapping each
        # cell in an <a> would break <td> nesting; wrapping the <tr>
        # is the htmx-idiomatic shape for clickable rows.
        body_parts: list[str] = []
        for i, row in enumerate(t.rows):
            row_cells: list[str] = []
            # Phase 7: per-row checkbox cell when bulk_select is on.
            if t.bulk_select:
                row_id = ctx.escape_attr(t.row_ids[i]) if t.row_ids else ""
                row_cells.append(
                    f'<td class="dz-tr-checkbox-cell" '
                    f'onclick="event.stopPropagation()">'
                    f'<input type="checkbox" class="dz-tr-checkbox" '
                    f"@change=\"toggleRow('{row_id}')\" "
                    f":checked=\"selected.has('{row_id}')\" "
                    f'aria-label="Select row" />'
                    f"</td>"
                )
            row_cells.extend(f"<td>{ctx.escape(cell)}</td>" for cell in row)
            cells_html = "".join(row_cells)
            url = t.row_links[i] if t.row_links else None
            row_id_attr = (
                f' data-dz-row-id="{ctx.escape_attr(t.row_ids[i])}"'
                if t.bulk_select and t.row_ids
                else ""
            )
            if url:
                url_attr = ctx.escape_attr(url)
                body_parts.append(
                    f'<tr class="dz-table__row dz-table__row--linked" '
                    f'hx-get="{url_attr}" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
                    f'hx-push-url="true" tabindex="0"{row_id_attr}>'
                    f"{cells_html}</tr>"
                )
            else:
                body_parts.append(f"<tr{row_id_attr}>{cells_html}</tr>")
        body_rows = "".join(body_parts)
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

        # Phase 4B.4 wave 4: outer dz-profile-card-region wrapper
        # for byte-equivalence with the legacy template.
        return (
            f'<div class="dz-profile-card-region">'
            f'<div class="dz-profile-card">{identity_html}{stats_html}{facts_html}</div>'
            f"</div>"
        )

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
            # Legacy always emits the period span when delta_direction
            # is set, even with an empty label (rendered as "vs ").
            period_html = (
                f'<span class="dz-metric-delta-period">vs {ctx.escape(m.delta_period_label)}</span>'
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

    def _emit_metrics_grid(self, g: MetricsGrid, ctx: RenderContext) -> str:
        """Render a MetricsGrid matching legacy
        `workspace/regions/metrics.html`: outer `dz-metrics-grid`
        wrapper with `data-dz-tile-count="N"` driving the responsive
        1/2/4 column layout via CSS, then the tile children inline.
        """
        tiles_html = "".join(self._emit(t, ctx) for t in g.tiles)  # type: ignore[arg-type]
        return (
            f'<div class="dz-metrics-grid" data-dz-tile-count="{len(g.tiles)}">{tiles_html}</div>'
        )

    def _emit_activity_feed(self, a: ActivityFeed, ctx: RenderContext) -> str:
        """Render an ActivityFeed matching legacy
        `workspace/regions/activity_feed.html` byte-for-byte: outer
        `<ul class="dz-activity-feed">`, per-row dot SVG + time + bubble.

        The dot SVG is identical across rows (constant). The bubble
        renders an optional `<span class="dz-activity-actor">` when an
        actor is present, then the description as raw text. Click-to-
        drawer wiring (legacy `action_url` → hx-get on the bubble) is
        not yet plumbed through — initial port covers the read-only
        feed shape only; clickable rows are a follow-up.
        """
        if not a.items:
            return f'<div class="dz-activity-empty">{ctx.escape(a.empty_message)}</div>'
        rows: list[str] = []
        for time_str, actor, description in a.items:
            actor_html = (
                f'<span class="dz-activity-actor">{ctx.escape(actor)}</span>' if actor else ""
            )
            rows.append(
                f'<li class="dz-activity-row">'
                f'<span class="dz-activity-dot">'
                f'<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
                f'<circle cx="10" cy="10" r="6"/>'
                f"</svg>"
                f"</span>"
                f'<div class="dz-activity-row-inner">'
                f'<div class="dz-activity-time">{ctx.escape(time_str)}</div>'
                f'<div class="dz-activity-bubble" >'
                f"{actor_html}{ctx.escape(description)}"
                f"</div>"
                f"</div>"
                f"</li>"
            )
        return f'<ul class="dz-activity-feed">{"".join(rows)}</ul>'

    def _emit_action_grid(self, g: ActionGrid, ctx: RenderContext) -> str:
        """Render an ActionGrid matching legacy
        `workspace/regions/action_grid.html` byte-for-byte: outer
        `dz-action-grid-region` + `dz-action-grid` wrapper. Empty
        path renders the `dz-empty-dense` fallback inside the region
        wrapper.
        """
        if not g.cards:
            return (
                f'<div class="dz-action-grid-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(g.empty_message)}</p>"
                f"</div>"
            )
        cards_html = "".join(self._emit(c, ctx) for c in g.cards)  # type: ignore[arg-type]
        return (
            f'<div class="dz-action-grid-region">'
            f'<div class="dz-action-grid">{cards_html}</div>'
            f"</div>"
        )

    def _emit_queue_region(self, q: QueueRegion, ctx: RenderContext) -> str:
        """Render a QueueRegion matching legacy
        `workspace/regions/queue.html` byte-for-byte: outer
        `dz-queue-region`, optional count row + metrics row, then
        the queue items list with per-row attention accent +
        headline (title + badges) + optional attn message + date
        secondaries + transition action buttons.

        Empty path renders `<p class="dz-empty-dense dz-queue-empty">`
        — note the legacy template uses BOTH classes.
        """
        from dazzle.render.fragment.region import (
            _render_status_badge_html,
        )

        if not q.rows:
            return (
                f'<div class="dz-queue-region">'
                f'<p class="dz-empty-dense dz-queue-empty" role="status">'
                f"{ctx.escape(q.empty_message)}</p>"
                f"</div>"
            )

        count_row = ""
        if q.total > 0:
            count_row = (
                f'<div class="dz-queue-count-row">'
                f'<span class="dz-queue-count">{q.total}</span>'
                f"</div>"
            )

        metrics_row = ""
        if q.metrics:
            metric_items = "".join(
                f'<div class="dz-queue-metric">'
                f'<div class="dz-queue-metric-value">{ctx.escape(m.value)}</div>'
                f'<div class="dz-queue-metric-label">{ctx.escape(m.label)}</div>'
                f"</div>"
                for m in q.metrics
            )
            metrics_row = f'<div class="dz-queue-metrics">{metric_items}</div>'

        rows_html: list[str] = []
        for row in q.rows:
            attn_class = ""
            attn_data_attr = ""
            attn_message_html = ""
            if row.attention_level:
                attn_class = f"dz-attn-both dz-attn-tone-{row.attention_level}"
                attn_data_attr = f' data-dz-attn="{ctx.escape_attr(row.attention_level)}"'
                attn_message_html = (
                    f'<p class="dz-queue-row-attn">{ctx.escape(row.attention_message)}</p>'
                )

            badges_html = "".join(_render_status_badge_html(b.value) for b in row.badges)
            headline_html = (
                f'<div class="dz-queue-row-headline">'
                f'<span class="dz-queue-row-title">{ctx.escape(row.title)}</span>'
                f"{badges_html}"
                f"</div>"
            )

            date_html = "".join(
                f'<span class="dz-queue-row-date">'
                f"{ctx.escape(d.label)}: {ctx.escape(d.timeago_str)}"
                f"</span>"
                for d in row.date_columns
            )

            actions_html = ""
            applicable = [t for t in q.transitions if t.to_state != row.current_status]
            if applicable and q.queue_status_field and q.queue_api_endpoint:
                buttons = "".join(
                    f'<button type="button" '
                    f'class="dz-queue-action" '
                    f'hx-put="{ctx.escape_attr(q.queue_api_endpoint)}/'
                    f'{ctx.escape_attr(row.row_id)}" '
                    f'hx-vals=\'{{"{q.queue_status_field}": '
                    f'"{t.to_state}"}}\' '
                    f'hx-target="#region-{ctx.escape_attr(q.region_name)}" '
                    f'hx-swap="innerHTML">'
                    f"{ctx.escape(t.label)}"
                    f"</button>"
                    for t in applicable
                )
                actions_html = (
                    f'<div class="dz-queue-row-actions" '
                    f'onclick="event.stopPropagation()">'
                    f"{buttons}"
                    f"</div>"
                )

            # Trailing space inside `class="dz-queue-row "` mirrors
            # legacy Jinja interpolation when no attn is present.
            row_open_class = f"dz-queue-row {attn_class}" if attn_class else "dz-queue-row "
            # Same artifact for `class="dz-queue-row-main "`.
            rows_html.append(
                f'<div class="{row_open_class}"{attn_data_attr}>'
                f'<div class="dz-queue-row-main ">'
                f"{headline_html}"
                f"{attn_message_html}"
                f"{date_html}"
                f"</div>"
                f"{actions_html}"
                f"</div>"
            )

        rows_block = f'<div class="dz-queue-rows">{"".join(rows_html)}</div>'

        overflow_html = ""
        if q.total > len(q.rows):
            overflow_html = f'<p class="dz-queue-overflow">Showing {len(q.rows)} of {q.total}</p>'

        return (
            f'<div class="dz-queue-region">'
            f"{count_row}"
            f"{metrics_row}"
            f"{rows_block}"
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_pivot_table_region(self, p: PivotTableRegion, ctx: RenderContext) -> str:
        """Render a PivotTableRegion matching legacy
        `workspace/regions/pivot_table.html` byte-for-byte: outer
        `dz-pivot-region`, `dz-pivot-scroll` + `<table class="dz-pivot-grid">`.
        Header has N dimension `<th>` cells + M measure `<th class="is-measure">`
        cells (humanized from measure_keys). Per-row dimension cells
        use FK label fallback for `is_fk=True` specs and status_badge
        rendering for non-FK specs (em-dash placeholder for None).
        Measure cells render raw values with `.is-measure` class.
        Summary line "{N} row(s)".
        """
        from dazzle.render.fragment.region import (
            _render_status_badge_html,
        )

        if not p.rows:
            return (
                f'<div class="dz-pivot-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(p.empty_message)}</p>"
                f"</div>"
            )

        # Header — dim columns then measure columns.
        head_dim = "".join(f"<th>{ctx.escape(s.label)}</th>" for s in p.dim_specs)
        head_measure = "".join(
            f'<th class="is-measure">{ctx.escape(k.replace("_", " ").title())}</th>'
            for k in p.measure_keys
        )
        thead = f"<thead><tr>{head_dim}{head_measure}</tr></thead>"

        body_rows: list[str] = []
        for row in p.rows:
            cells_html = ""
            for spec in p.dim_specs:
                if spec.is_fk:
                    fk_label = row.get(f"{spec.name}_label")
                    if fk_label is None:
                        # Fallback: raw spec.name value, em-dash if also None.
                        sval = row.get(spec.name)
                        cells_html += f"<td>{ctx.escape(str(sval)) if sval else '—'}</td>"
                    else:
                        cells_html += f"<td>{ctx.escape(str(fk_label))}</td>"
                else:
                    sval = row.get(spec.name)
                    if sval is None:
                        cells_html += '<td><span class="dz-pivot-null">—</span></td>'
                    else:
                        cells_html += f"<td>{_render_status_badge_html(sval, size='sm')}</td>"
            for k in p.measure_keys:
                v = row.get(k)
                cells_html += f'<td class="is-measure">{ctx.escape(str(v))}</td>'
            body_rows.append(f"<tr>{cells_html}</tr>")
        tbody = f"<tbody>{''.join(body_rows)}</tbody>"

        n = len(p.rows)
        suffix = "" if n == 1 else "s"
        summary = f'<p class="dz-pivot-summary">{n} row{suffix}</p>'

        return (
            f'<div class="dz-pivot-region">'
            f'<div class="dz-pivot-scroll">'
            f'<table class="dz-pivot-grid">{thead}{tbody}</table>'
            f"</div>"
            f"{summary}"
            f"</div>"
        )

    def _emit_list_region(self, lst: ListRegion, ctx: RenderContext) -> str:
        """Render a ListRegion matching legacy
        `workspace/regions/list.html` byte-for-byte: outer
        `dz-list-region`, action row with always-emitted CSV button,
        `<div class="dz-list-scroll">` of `<table class="dz-list-table">`,
        optional overflow line. Filter chrome / sortable headers /
        click-through wiring deferred to follow-up — read-only basic
        case here.
        """
        # Action row — CSV button always rendered (legacy behaviour).
        csv_button = (
            f'<button type="button" '
            f'data-dz-csv-endpoint="{ctx.escape_attr(lst.csv_endpoint)}" '
            f'data-dz-csv-filename="{ctx.escape_attr(lst.csv_filename)}" '
            f'onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" '
            f'class="dz-list-csv-button" title="Export CSV" aria-label="Export CSV">'
            f'<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            f'd="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>'
            f"</svg>"
            f"</button>"
        )
        actions_row = (
            f'<div class="dz-list-actions">'
            f'<div class="dz-list-action-group">{csv_button}</div>'
            f"</div>"
        )

        if not lst.rows:
            # Legacy empty state via fragments/empty_state.html — match
            # the read-only shape with the fixed icon + message.
            label = lst.empty_message or "No items found."
            empty_html = (
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f'<svg class="dz-empty-state-icon" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" '
                f'd="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>'
                f"</svg>"
                f'<p class="dz-empty-state-message">{ctx.escape(label)}</p>'
                f"</div>"
            )
            return f'<div class="dz-list-region">{actions_row}{empty_html}</div>'

        has_actions = bool(lst.row_actions)
        thead_cells = [f"<th>{ctx.escape(c.label)}</th>" for c in lst.columns]
        if has_actions:
            # #1148: trailing action column header. ``row_action_label``
            # is the visible label authored in DSL — usually short
            # (e.g. "Approve", "Resolve") so the table doesn't grow
            # excessively wide.
            thead_cells.append(
                f'<th class="dz-list-row-action-col">{ctx.escape(lst.row_action_label)}</th>'
            )
        thead = "<thead><tr>" + "".join(thead_cells) + "</tr></thead>"

        tbody_rows: list[str] = []
        for i, row in enumerate(lst.rows):
            cells_html = ""
            for cell in row:
                if isinstance(cell, str):
                    cells_html += f"<td>{ctx.escape(cell)}</td>"
                else:
                    cells_html += f"<td>{self._emit(cell, ctx)}</td>"  # type: ignore[arg-type]
            if has_actions:
                # #1148: per-row action button HTML is pre-rendered by
                # the data builder (already-escaped attributes, hx-post
                # URL, JSON-encoded bound args). Trust contract: builder
                # owns escape for the values it pulls off row dicts.
                cells_html += f'<td class="dz-list-row-action">{lst.row_actions[i]}</td>'
            # #1303: per-row drill-to-detail. When a row link is set, the
            # <tr> carries an hx-get to the entity detail (full-page swap),
            # the htmx-idiomatic clickable-row shape the standalone list uses
            # (#1029) — not a cell <a>, which would break <td> nesting.
            url = lst.row_links[i] if lst.row_links else None
            if url:
                url_attr = ctx.escape_attr(url)
                tbody_rows.append(
                    f'<tr class="dz-list-row is-clickable" '
                    f'hx-get="{url_attr}" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
                    f'hx-push-url="true" tabindex="0">{cells_html}</tr>'
                )
            else:
                # Trailing space on `class="dz-list-row "` mirrors legacy
                # `class="dz-list-row {{ attention_classes(...) }}{% if action_url %} is-clickable{% endif %}"`
                # for the no-attention, no-action_url case.
                tbody_rows.append(f'<tr class="dz-list-row ">{cells_html}</tr>')
        tbody = f"<tbody>{''.join(tbody_rows)}</tbody>"

        table = (
            f'<div class="dz-list-scroll"><table class="dz-list-table">{thead}{tbody}</table></div>'
        )

        overflow_html = ""
        if lst.total > len(lst.rows):
            overflow_html = (
                f'<p class="dz-list-overflow">Showing {len(lst.rows)} of {lst.total}</p>'
            )

        return f'<div class="dz-list-region">{actions_row}{table}{overflow_html}</div>'

    def _emit_grid_region(self, g: GridRegion, ctx: RenderContext) -> str:
        """Render a GridRegion matching legacy
        `workspace/regions/grid.html` byte-for-byte: outer
        `dz-grid-region`, `<div class="dz-grid-list">` with per-cell
        `<div class="dz-grid-cell">` containing `<h4>` title +
        per-field `<p class="dz-grid-cell-field">` lines. Empty path
        renders the legacy empty-state fragment shape.
        """
        if not g.cells:
            # Empty state matches `fragments/empty_state.html` —
            # SVG icon + message + optional CTA. The CTA needs an
            # entity_name + create_url which the primitive doesn't
            # carry yet; for now emit the read-only empty state with
            # the message only. CTA support is a follow-up when the
            # primitive gains the appropriate fields.
            label = g.empty_message or "No items found."
            return (
                f'<div class="dz-grid-region">'
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f'<svg class="dz-empty-state-icon" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" '
                f'stroke-width="1.5" '
                f'd="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>'
                f"</svg>"
                f'<p class="dz-empty-state-message">{ctx.escape(label)}</p>'
                f"</div>"
                f"</div>"
            )

        cells_html: list[str] = []
        for cell in g.cells:
            fields_html = ""
            for label, value in cell.fields:
                if isinstance(value, str):
                    value_html = ctx.escape(value)
                else:
                    value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                fields_html += (
                    f'<p class="dz-grid-cell-field">'
                    f'<span class="dz-grid-cell-field-label">{ctx.escape(label)}:</span> '
                    f"{value_html}"
                    f"</p>"
                )
            # Trailing space inside `class="dz-grid-cell "` matches the
            # legacy `class="dz-grid-cell {{ attention_classes(...) }}"`
            # rendering when attention is empty — Jinja interpolates ""
            # leaving the space. Preserve it for byte-equivalence.
            cells_html.append(
                f'<div class="dz-grid-cell ">'
                f'<h4 class="dz-grid-cell-title">{ctx.escape(cell.title)}</h4>'
                f"{fields_html}"
                f"</div>"
            )

        return (
            f'<div class="dz-grid-region">'
            f'<div class="dz-grid-list">{"".join(cells_html)}</div>'
            f"</div>"
        )

    def _emit_status_list(self, s: StatusList, ctx: RenderContext) -> str:
        """Render a StatusList matching legacy
        `workspace/regions/status_list.html` byte-for-byte: outer
        `dz-status-list-region` wrapper, `<ul class="dz-status-list"
        data-dz-entry-count="N">` with per-row `data-dz-state` attr,
        icon column (or spacer), title + optional caption, pill for
        non-neutral states.

        Empty state renders the `dz-empty-dense` paragraph inside the
        region wrapper, matching the legacy template's else branch.
        """
        if not s.entries:
            return (
                f'<div class="dz-status-list-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(s.empty_message)}</p>"
                f"</div>"
            )

        rows: list[str] = []
        for entry in s.entries:
            if entry.icon:
                icon_html = (
                    f'<span class="dz-status-list-icon" '
                    f'data-lucide="{ctx.escape_attr(entry.icon)}" '
                    f'aria-hidden="true"></span>'
                )
            else:
                icon_html = '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'

            caption_html = (
                f'<div class="dz-status-list-caption">{ctx.escape(entry.caption)}</div>'
                if entry.caption
                else ""
            )

            pill_html = (
                f'<span class="dz-status-list-pill">{ctx.escape(entry.state)}</span>'
                if entry.state != "neutral"
                else ""
            )

            rows.append(
                f'<li class="dz-status-list-entry" '
                f'data-dz-state="{ctx.escape_attr(entry.state)}">'
                f"{icon_html}"
                f'<div class="dz-status-list-text">'
                f'<div class="dz-status-list-title">{ctx.escape(entry.title)}</div>'
                f"{caption_html}"
                f"</div>"
                f"{pill_html}"
                f"</li>"
            )

        return (
            f'<div class="dz-status-list-region">'
            f'<ul class="dz-status-list" data-dz-entry-count="{len(s.entries)}">'
            f"{''.join(rows)}"
            f"</ul>"
            f"</div>"
        )

    def _emit_detail_grid(self, g: DetailGrid, ctx: RenderContext) -> str:
        """Render a DetailGrid matching legacy
        `workspace/regions/detail.html`: outer `dz-detail-region`
        wrapper, `dz-detail-region-grid` definition list, and per-row
        `<dt class="dz-detail-label">` / `<dd class="dz-detail-value">`
        pairs.

        The value fragment renders inline inside the `<dd>` — Badge,
        Text, Link, etc. Per-type rendering (badge / bool / date /
        currency / ref) is the adapter's responsibility — this
        primitive just lays out the dt/dd grid structure.
        """
        rows_html = "".join(
            f'<dt class="dz-detail-label">{ctx.escape(label)}</dt>'
            f'<dd class="dz-detail-value">{self._emit(value, ctx)}</dd>'  # type: ignore[arg-type]
            for label, value in g.rows
        )
        return (
            f'<div class="dz-detail-region">'
            f'<dl class="dz-detail-region-grid">{rows_html}</dl>'
            f"</div>"
        )

    def _emit_bar_track(self, b: BarTrack, ctx: RenderContext) -> str:
        """Render a BarTrack matching legacy `workspace/regions/bar_track.html`
        byte-for-byte: outer `dz-bar-track-region` wrapper, per-row track
        with ARIA progressbar semantics, summary line, and optional
        reference annotations.

        Phase 4B.1.c (bar-track variant): added the outer
        `<div class="dz-bar-track-region">` wrapper so the emit matches
        the legacy template structurally — completes the chart family
        port. The references block (BEM `__references`) rides along
        outside the region wrapper, consistent with TimeSeries / BoxPlot
        / BarChart — references are a Phase 4B-only programmatic-data
        layer with no legacy template equivalent.
        """

        # Match Jinja's `{{ value }}` rendering — int repr for whole values.
        def _num(v: float) -> str:
            return str(int(v)) if v == int(v) else str(v)

        max_str = _num(b.max_value)
        rows_html = "".join(
            f'<div class="dz-bar-track-row">'
            f'<span class="dz-bar-track-label" title="{ctx.escape_attr(label)}">'
            f"{ctx.escape(label)}</span>"
            f'<div class="dz-bar-track" role="progressbar" '
            f'aria-valuemin="0" '
            f'aria-valuemax="{max_str}" '
            f'aria-valuenow="{_num(value)}" '
            f'aria-label="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}">'
            f'<span class="dz-bar-track-fill" '
            f'style="width: {_num(round(fill_pct, 2))}%;" '
            f'title="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}"></span>'
            f"</div>"
            f'<span class="dz-bar-track-value">{ctx.escape(formatted)}</span>'
            f"</div>"
            for label, value, formatted, fill_pct in b.rows
        )
        refs = _render_references("dz-bar-track", b.reference_lines, b.reference_bands, ctx)
        max_rounded = round(b.max_value, 2)
        max_summary = str(int(max_rounded)) if max_rounded == int(max_rounded) else str(max_rounded)
        return (
            f'<div class="dz-bar-track-region">'
            f'<div class="dz-bar-track-rows">{rows_html}</div>'
            f'<p class="dz-bar-track-summary">'
            f"{len(b.rows)} rows · scale 0–{max_summary}"
            f"</p>"
            f"</div>"
            f"{refs}"
        )

    def _emit_stage_bar(self, s: StageBar, ctx: RenderContext) -> str:
        """Render a StageBar matching legacy
        `workspace/regions/progress.html` byte-for-byte: outer
        `dz-progress-region` wrapper, header `<progress>` + percent
        readout, chip list of stages with per-chip tone (complete /
        active / empty), and an optional "N of M complete" summary.
        """
        # Match Jinja's `{{ complete_pct }}` rendering: int values
        # render without trailing `.0`, floats render as-is. The
        # adapter coerces to float for type safety; the renderer
        # narrows back to int when the value is whole so byte-
        # equivalence holds for the common round-percentage case.
        pct = s.complete_pct
        pct_str = str(int(pct)) if pct == int(pct) else str(pct)

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
            f'<div class="dz-progress-region">'
            f'<div class="dz-progress-header">'
            f'<progress data-dz-progress value="{pct_str}" max="100"></progress>'
            f"<span>{pct_str}%</span>"
            f"</div>"
            f'<div class="dz-progress-stages">{chips_html}</div>'
            f"{summary_html}"
            f"</div>"
        )
