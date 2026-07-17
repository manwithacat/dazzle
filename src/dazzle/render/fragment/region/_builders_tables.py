"""Tables-family region builders.

Houses the 4 tabular builders — the largest family by line count:

  - _build_list         ListRegion with optional FilterBar/DatePicker/CSV chrome
  - _build_queue        QueueRegion with inline state-transition action buttons
  - _build_pivot_table  PivotTableRegion (or legacy 2-dim PivotTable fallback)
  - _build_tabbed_list  LazyTabPanel (HTMX) or eager Tabs fallback

No family-local helpers — `_render_typed_value` / `_region_title` /
`_wrap_surface` come from `_shared`; `_metric_number_filter` /
`_timeago_filter` stay as inline lazy imports.

See issue #1065 for the full decomposition plan. This is the LAST
family extraction — after this lands, `_dispatcher.py` is the
class shell + dispatch tables + `build()`.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    URL,
    CsvExportButton,
    DateRangePicker,
    EmptyState,
    FilterBar,
    FilterColumn,
    Fragment,
    LazyTab,
    LazyTabPanel,
    ListColumn,
    ListRegion,
    PivotDimSpec,
    PivotTable,
    PivotTableRegion,
    QueueBadgeColumn,
    QueueDateColumn,
    QueueMetric,
    QueueRegion,
    QueueRow,
    QueueTransition,
    RawHTML,
    Row,
    Stack,
    Surface,
    Tabs,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._row_links import _resolve_row_links
from dazzle.render.fragment.region._shared import (
    _region_title,
    _render_typed_value,
    _wrap_surface,
)
from dazzle.render.fragment.region.workspace_card_bodies import (
    _eval_row_condition,
    _render_row_action_button,
)


def _outlier_badge(flag: str) -> RawHTML:
    """WCAG-safe outlier badge: tone colour + ⚠ icon + direction text (#1470).

    Uniform `warning` tone (an outlier is *notable*, not good/bad); the
    direction is carried by the ⚠ icon + `high`/`low` text + aria-label.
    """
    from html import escape as _esc

    direction = flag if flag in ("low", "high") else "outlier"
    return RawHTML(
        f'<span class="dz-badge dz-badge-sm" data-dz-tone="warning" '
        f'aria-label="Outlier: {_esc(direction)}">⚠ {_esc(direction)}</span>'
    )


_RAG_LABELS = {"positive": "good", "warning": "watch", "destructive": "critical"}


def _rag_badge(tone: str) -> RawHTML:
    """WCAG-safe RAG badge: band tone colour + ● icon + derived label (#1470)."""
    from html import escape as _esc

    label = _RAG_LABELS.get(tone, tone)
    return RawHTML(
        f'<span class="dz-badge dz-badge-sm" data-dz-tone="{_esc(tone, quote=True)}" '
        f'aria-label="Status: {_esc(label)}">● {_esc(label)}</span>'
    )


class _BuildersTablesMixin:
    """Mixin adding the 4 tables-family `_build_*` methods to
    `WorkspaceRegionAdapter`. Same pattern as other family mixins.
    """

    def _build_list(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: list` regions render as a Region(kind=list).

        Phase 4A core: items + columns → Table primitive (basic list).
        Phase 4B.1.e: opt-in chrome — when ctx supplies `endpoint` +
        `region_name`, the adapter composes a Stack of:
          1. FilterBar (when `filter_columns` is present)
          2. DateRangePicker (when `date_range` is True)
          3. CsvExportButton (when `csv_export` is True)
          4. Table with sortable column headers (when `sort_field` is
             tracked in ctx and columns supply `sortable: True`)
          5. CsvExportButton — actually appears in the action row, not
             below; placement is renderer's concern via Stack ordering

        Without chrome ctx, the original simple Table-only behaviour
        is preserved for backward compat with existing tests.

        ctx shape (Phase 4B.1.e additions):
            endpoint: str URL for HTMX-driven chrome (filter bar, sort,
                date range, csv export)
            region_name: str — DOM-id namespace for hx-target
            filter_columns: list of dicts {key, label, options[(value, display)],
                selected} → produces FilterBar
            active_filters: dict[key → value] — currently-selected filters
                (alternative to per-column `selected`)
            date_range: bool — when True, render DateRangePicker
            date_from / date_to: iso-date strings for picker initial values
            csv_export: bool — when True, render CsvExportButton
            sort_field: str — currently-active sort column key
            sort_dir: "asc" | "desc"
            columns[i].sortable: bool — column-level opt-in for sort header
        """
        title = _region_title(region)
        items = ctx.get("items", []) or []
        columns: list[Any] = ctx.get("columns", []) or []
        # #1470 outlier_on — decorated column key + per-row flags (index-aligned
        # to `items`). Empty/unset → ordinary list render.
        outlier_on = str(ctx.get("outlier_on") or "")
        outlier_flags = ctx.get("outlier_flags") or []
        # #1470 rag_on — fixed-band RAG decorator (parallel to outlier_on).
        rag_on = str(ctx.get("rag_on") or "")
        rag_tones = ctx.get("rag_tones") or []

        endpoint = ctx.get("endpoint")
        region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "list")

        # Build chrome elements in declared order.
        chrome_parts: list[Fragment] = []

        # FilterBar — when filter_columns is supplied
        filter_columns_raw = ctx.get("filter_columns") or []
        active_filters = ctx.get("active_filters") or {}
        if endpoint and isinstance(filter_columns_raw, list) and filter_columns_raw:
            cols: list[FilterColumn] = []
            seen: set[str] = set()
            for fc in filter_columns_raw:
                if not isinstance(fc, dict):
                    continue
                key = str(fc.get("key") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                # Options arrive as either list[str] (legacy) or
                # list[(value, display)] tuples / list[dict].
                raw_options = fc.get("options") or []
                opts: list[tuple[str, str]] = []
                for opt in raw_options:
                    if isinstance(opt, tuple) and len(opt) == 2:
                        opts.append((str(opt[0]), str(opt[1])))
                    elif isinstance(opt, dict):
                        opts.append((str(opt.get("value") or ""), str(opt.get("label") or "")))
                    else:
                        opts.append((str(opt), str(opt)))
                selected = str(
                    fc.get("selected")
                    or (active_filters.get(key) if isinstance(active_filters, dict) else "")
                    or ""
                )
                cols.append(
                    FilterColumn(
                        key=key,
                        label=str(fc.get("label") or key),
                        options=tuple(opts),
                        selected=selected,
                    )
                )
            if cols:
                chrome_parts.append(
                    FilterBar(
                        endpoint=URL(str(endpoint)),
                        region_name=region_name,
                        columns=tuple(cols),
                    )
                )

        # DateRangePicker — when date_range flag is set
        if endpoint and ctx.get("date_range"):
            chrome_parts.append(
                DateRangePicker(
                    endpoint=URL(str(endpoint)),
                    region_name=region_name,
                    date_from=str(ctx.get("date_from") or ""),
                    date_to=str(ctx.get("date_to") or ""),
                )
            )

        # CsvExportButton — when csv_export flag is set
        if endpoint and ctx.get("csv_export"):
            chrome_parts.append(
                CsvExportButton(
                    endpoint=URL(str(endpoint)),
                    filename=str(ctx.get("csv_filename") or f"{region_name}.csv"),
                )
            )

        # Body — ListRegion primitive matching legacy
        # `workspace/regions/list.html` byte-for-byte (Phase 4B.4 wave 2).
        list_columns: list[ListColumn] = []
        list_rows: list[tuple[object, ...]] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            list_columns.append(
                ListColumn(
                    key=str(col.get("key") or ""),
                    label=str(col.get("label") or col.get("key") or ""),
                )
            )

        # #1148: when the region declares ``row_action:``, build the
        # per-row action button HTML alongside the cell rows so the
        # ListRegion can emit a trailing action column. Tracked
        # separately from cells to keep arity-validation simple.
        row_action_spec = getattr(region, "row_action", None)
        row_action_label = ""
        row_actions_list: list[str] = []
        if row_action_spec is not None:
            row_action_label = row_action_spec.label

        # #1303: per-row drill-to-detail. `detail_url_template` (e.g.
        # "/app/assessment-event/{id}") is threaded in by the workspace
        # route builder when the source entity has a VIEW surface and the
        # region didn't `drill: none`. Track the dict items that actually
        # produce rows so the resolved links stay index-aligned with
        # `list_rows` (non-dict items are skipped below).
        detail_url_template = str(ctx.get("detail_url_template") or "")
        row_items: list[dict[str, Any]] = []

        for item_idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            # #1470: this row's flag for the decorated column (index-aligned
            # to `items`; non-dict items skipped here are still slotted None
            # by build_outlier_flags so indices stay aligned).
            row_flag = (
                outlier_flags[item_idx] if outlier_on and item_idx < len(outlier_flags) else None
            )
            row_rag = rag_tones[item_idx] if rag_on and item_idx < len(rag_tones) else None
            row_cells: list[object] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                # Per-cell type-aware rendering via the same helper used
                # by DETAIL/TIMELINE/GRID. LIST passes default badge args
                # (size="md", bordered=False).
                value_cell = _render_typed_value(item, col)
                col_key = str(col.get("key") or "")
                if row_flag in ("low", "high") and col_key == outlier_on:
                    row_cells.append(
                        Row(
                            children=(value_cell, _outlier_badge(row_flag)),
                            gap="sm",
                            align="center",
                        )
                    )
                elif row_rag and col_key == rag_on:
                    row_cells.append(
                        Row(
                            children=(value_cell, _rag_badge(str(row_rag))),
                            gap="sm",
                            align="center",
                        )
                    )
                else:
                    row_cells.append(value_cell)
            list_rows.append(tuple(row_cells))
            row_items.append(item)
            if row_action_spec is not None:
                visible = (
                    True
                    if row_action_spec.visible_when is None
                    else _eval_row_condition(row_action_spec.visible_when, item)
                )
                if visible:
                    _row_action_routes = ctx.get("row_action_routes") or {}
                    row_actions_list.append(
                        _render_row_action_button(
                            action_id=row_action_spec.action_id,
                            label=row_action_spec.label,
                            item=item,
                            bind=row_action_spec.bind,
                            action_url=_row_action_routes.get(row_action_spec.action_id, ""),
                        )
                    )
                else:
                    row_actions_list.append("")

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        try:
            total = int(ctx.get("total") or len(list_rows))
        except (TypeError, ValueError):
            total = len(list_rows)

        # #1303: resolve per-row drill links (index-aligned with list_rows).
        # Reuses the standalone list's helper so workspace + standalone
        # share one substitution contract.
        row_links: tuple[str | None, ...] = ()
        if detail_url_template or ctx.get("detail_url_candidates"):
            # #1614: optional same-entity fallback when open-via FK is null
            # #1600 P2: multi-hop open-via candidates (first non-null)
            _fb = str(ctx.get("detail_url_fallback_template") or "")
            _raw_cands = ctx.get("detail_url_candidates")
            _cands: tuple[str, ...]
            if isinstance(_raw_cands, str):
                _cands = (_raw_cands,) if _raw_cands else ()
            elif isinstance(_raw_cands, (list, tuple)):
                _cands = tuple(str(c) for c in _raw_cands if c)
            else:
                _cands = ()
            row_links = _resolve_row_links(
                row_items,
                detail_url_template or "",
                fallback_template=_fb,
                candidate_templates=_cands,
            )

        body: Fragment = ListRegion(
            columns=tuple(list_columns),
            rows=tuple(list_rows),
            csv_endpoint=str(endpoint or ""),
            csv_filename=f"{region_name}.csv",
            total=total,
            empty_message=str(empty_msg),
            row_action_label=row_action_label,
            row_actions=tuple(row_actions_list) if row_action_spec is not None else (),
            row_links=row_links,
            master_detail_pane=bool(ctx.get("master_detail_pane")),
            master_detail_target=str(ctx.get("master_detail_target") or ""),
        )

        # If we have chrome, wrap the body in a Stack that also contains
        # the chrome row(s). The legacy template injects chrome INSIDE
        # the dz-list-region wrapper, so once chrome flows through the
        # ListRegion primitive (follow-up), this Stack wrap can drop.
        if chrome_parts:
            body = Stack(children=(*chrome_parts, body), gap="md")

        return _wrap_surface(title, "list", body)

    def _build_queue(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: queue` regions render as a review queue with inline
        state-transition action buttons.

        Phase 4B.1.d/e — replaces the prior alias to `_build_list`.
        Composes a Stack of:
          1. Total count badge (when total > 0)
          2. Metrics summary tiles (when `metrics` ctx is supplied)
          3. FilterBar / DateRangePicker / CsvExportButton chrome (same
             contract as `_build_list`)
          4. Per-item rows: each item is a Card with main content + a
             Row of transition Buttons (using the extended Button shape
             from v0.66.83 — hx_put + hx_vals + hx_ext)
          5. Overflow text (when `total > len(items)`)

        Note: this is structurally equivalent to the legacy
        `queue.html` but not byte-for-byte (the legacy template uses
        a custom `dz-queue-row` flex layout that the typed-Fragment
        substrate doesn't replicate today). The Phase 4B.3 dual-path
        validation gate will surface this as an accepted divergence
        — the chrome is byte-equivalent, the row interior is not.

        ctx shape (Phase 4B preferred):
            items, columns: same as list
            total: int — full row count for the count badge + overflow
            metrics: list of metric dicts (label, value, etc.)
            endpoint, region_name: HTMX wiring (chrome + transitions)
            filter_columns, active_filters, date_range, csv_export: chrome
            queue_transitions: list of {label, to_state}
            queue_status_field: str — field name carrying current state
            queue_api_endpoint: str URL — base URL for transitions
                (transitions PUT to f"{queue_api_endpoint}/{item.id}")
        """
        from dazzle.render.filters import (
            _metric_number_filter,
            _timeago_filter,
        )

        title = _region_title(region)
        items = ctx.get("items", []) or []
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "queue")
        queue_status_field = str(ctx.get("queue_status_field") or "")
        queue_api_endpoint = str(ctx.get("queue_api_endpoint") or "")
        display_key = str(ctx.get("display_key") or "")
        columns = ctx.get("columns") or []
        detail_url_template = str(ctx.get("detail_url_template") or "")

        # Metrics row.
        metrics: list[QueueMetric] = []
        for m in ctx.get("metrics") or []:
            if not isinstance(m, dict):
                continue
            label = str(m.get("label") or m.get("name") or "")
            if not label:
                continue
            metrics.append(
                QueueMetric(
                    label=label,
                    value=str(_metric_number_filter(m.get("value"))),
                )
            )

        # Transition definitions (per-region).
        transitions: list[QueueTransition] = []
        for tr in ctx.get("queue_transitions") or []:
            if not isinstance(tr, dict):
                continue
            to_state = str(tr.get("to_state") or "")
            if not to_state:
                continue
            transitions.append(
                QueueTransition(
                    label=str(tr.get("label") or to_state),
                    to_state=to_state,
                )
            )

        # #1303: resolve hub drills once for all dict rows.
        dict_items = [i for i in items if isinstance(i, dict)]
        row_links: tuple[str | None, ...] = (
            _resolve_row_links(dict_items, detail_url_template) if detail_url_template else ()
        )

        # Per-row construction.
        rows: list[QueueRow] = []
        link_idx = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or "")
            # Title chain: FK-resolved `<key>_display` when present and
            # non-empty → raw display_key value → id. Missing `_display`
            # (normal for non-FK display_field like Ticket.subject) must
            # fall through to the primary field — never empty title or
            # bare UUID when subject/title is on the row.
            row_title = row_id
            if display_key:
                display_attr = f"{display_key}_display"
                resolved = item.get(display_attr) if display_attr in item else None
                primary = item.get(display_key)
                if resolved is not None and str(resolved).strip():
                    row_title = str(resolved)
                elif primary is not None and str(primary).strip():
                    row_title = str(primary)

            # Badges = columns with type=="badge" and key != display_key.
            badges: list[QueueBadgeColumn] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key:
                    continue
                if col.get("type") == "badge":
                    badges.append(QueueBadgeColumn(key=key, value=item.get(key)))

            # Date secondaries = columns with type=="date" and a non-empty value.
            date_columns: list[QueueDateColumn] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                if col.get("type") != "date":
                    continue
                key = str(col.get("key") or "")
                val = item.get(key)
                if not val:
                    continue
                date_columns.append(
                    QueueDateColumn(
                        label=str(col.get("label") or key),
                        timeago_str=_timeago_filter(val),
                    )
                )

            # Attention.
            attn_raw = item.get("_attention") if hasattr(item, "get") else None
            attn_level = ""
            attn_message = ""
            if isinstance(attn_raw, dict):
                attn_level = str(attn_raw.get("level") or "")
                attn_message = str(attn_raw.get("message") or "")

            current_status = str(item.get(queue_status_field) or "") if queue_status_field else ""

            drill_url = ""
            if link_idx < len(row_links) and row_links[link_idx]:
                drill_url = str(row_links[link_idx])
            link_idx += 1

            rows.append(
                QueueRow(
                    row_id=row_id,
                    title=row_title,
                    current_status=current_status,
                    badges=tuple(badges),
                    date_columns=tuple(date_columns),
                    attention_level=attn_level,
                    attention_message=attn_message,
                    drill_url=drill_url,
                )
            )

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "Queue is empty."
        )
        body: Fragment = QueueRegion(
            rows=tuple(rows),
            total=total,
            metrics=tuple(metrics),
            transitions=tuple(transitions),
            queue_status_field=queue_status_field,
            queue_api_endpoint=queue_api_endpoint,
            region_name=region_name,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "list", body)

    def _build_pivot_table(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: pivot_table` regions render as a `PivotTableRegion`
        primitive matching `workspace/regions/pivot_table.html`
        byte-for-byte. Phase 4B.4 wave 4: replaced the simpler
        2-dim PivotTable primitive with the workspace-shape that
        consumes `pivot_buckets` + `pivot_dim_specs` directly.

        ctx shape (production runtime):
            pivot_buckets: list[dict] — one row per dim combination
            pivot_dim_specs: list[{name, label, is_fk}] — dimension columns
            empty_message: optional empty-state fallback
            (legacy alt) rows + columns + cells: 2-dim matrix shape;
              not the production runtime ctx, but kept on a fallback
              path until callers migrate.
        """
        title = _region_title(region)
        raw_buckets = ctx.get("pivot_buckets") or []
        raw_specs = ctx.get("pivot_dim_specs") or []

        # Phase 4A 2-dim fallback: rows + columns + cells.
        if not raw_buckets and (ctx.get("rows") or ctx.get("columns")):
            rows_2d = tuple(str(r) for r in (ctx.get("rows") or []))
            cols_2d = tuple(str(c) for c in (ctx.get("columns") or []))
            raw_cells = ctx.get("cells") or {}
            cells: dict[tuple[str, str], int] = {}
            if isinstance(raw_cells, dict):
                for key, val in raw_cells.items():
                    if isinstance(key, (list, tuple)) and len(key) == 2:
                        r, c = str(key[0]), str(key[1])
                        if r in rows_2d and c in cols_2d:
                            try:
                                cells[(r, c)] = int(val)
                            except (TypeError, ValueError):
                                continue
            chart_label = str(ctx.get("chart_label") or title or "Pivot")
            if rows_2d and cols_2d:
                body: Fragment = PivotTable(
                    label=chart_label,
                    rows=rows_2d,
                    columns=cols_2d,
                    cells=cells,
                )
            else:
                body = EmptyState(
                    title="No data",
                    description=getattr(region, "empty_message", None)
                    or "No row or column dimensions to pivot.",
                )
            return _wrap_surface(title, "report", body)

        # Production path: pivot_buckets + pivot_dim_specs.
        dim_specs: list[PivotDimSpec] = []
        dim_field_names: set[str] = set()
        for spec in raw_specs:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "")
            if not name:
                continue
            dim_specs.append(
                PivotDimSpec(
                    name=name,
                    label=str(spec.get("label") or name),
                    is_fk=bool(spec.get("is_fk")),
                )
            )
            dim_field_names.add(name)
            dim_field_names.add(f"{name}_label")

        # Measure keys = ALL first-row keys, NOT filtered. The legacy
        # template intends to filter out dimension fields via an inner
        # `{% set is_dim_field = true %}` mutation inside a nested
        # `{% for spec in pivot_dim_specs %}` loop, but Jinja's set
        # scoping doesn't propagate the mutation out of the inner block,
        # so the filter never applies and EVERY row key (including
        # dim fields like `status`/`severity` and FK label fields like
        # `status_label`) ends up as a measure column. Phase 4B.4 wave
        # 4 (v0.66.116) replicates this scoping bug exactly for
        # byte-equivalence — Jinja-scope quirks of the kind we
        # accumulated in v0.66.106 (pipeline_steps progress) and
        # v0.66.111 (radar tooltip).
        measure_keys: list[str] = []
        if raw_buckets and isinstance(raw_buckets[0], dict):
            measure_keys = [str(k) for k in raw_buckets[0].keys()]

        rows_norm = tuple(b for b in raw_buckets if isinstance(b, dict))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data to pivot."
        )
        body = PivotTableRegion(
            dim_specs=tuple(dim_specs),
            measure_keys=tuple(measure_keys),
            rows=rows_norm,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_tabbed_list(self, region: Any, ctx: RegionContext) -> Surface:
        """`display: tabbed_list` regions render as a tabbed container.

        Phase 4B.1.d preferred path — the runtime supplies `source_tabs`
        with HTMX endpoints, producing a `LazyTabPanel` that lazy-loads
        each tab's content (matches the legacy `workspace/regions/
        tabbed_list.html` HTMX-driven shape byte-for-byte).

        Phase 4A fallback path — the test/migration ctx supplies `tabs`
        with pre-loaded `items` + `columns`, producing the simpler
        eager `Tabs` primitive. This is retained so existing call sites
        and tests don't regress; the runtime should migrate to
        `source_tabs` ahead of the Phase 4B.2 translator.

        ctx shape (Phase 4B preferred):
            region_name: str — DOM-id namespace; required for LazyTabPanel
            source_tabs: list[dict] each with:
              - key: str (slug for tab id)
              - label: str
              - endpoint: str (URL; HTMX hx-get target)
              - eager: bool (optional; first tab is always eager)

        ctx shape (Phase 4A fallback):
            tabs / slices: list[dict] each with:
              - key, label, items, columns (pre-loaded shape)
        """
        from dazzle.render.fragment import Table

        title = _region_title(region)

        # Phase 4B preferred: lazy-loaded tabs via HTMX endpoints
        source_tabs = ctx.get("source_tabs") or []
        if source_tabs:
            region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "tabbed")
            built_lazy: list[LazyTab] = []
            seen_keys: set[str] = set()
            for st in source_tabs:
                if not isinstance(st, dict):
                    continue
                # Legacy template uses `entity_name | lower` for the
                # tab id slug; accept both `key` (Phase 4B preferred)
                # and `entity_name` (production runtime ctx).
                entity_name = str(st.get("entity_name") or "")
                key = str(st.get("key") or entity_name.lower())
                label = str(st.get("label") or key)
                endpoint = str(st.get("endpoint") or "")
                if not key or not endpoint:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                built_lazy.append(
                    LazyTab(
                        key=key,
                        label=label,
                        endpoint=URL(endpoint),
                        eager=bool(st.get("eager")),
                    )
                )
            body: Fragment
            if not built_lazy:
                body = EmptyState(
                    title="No tabs",
                    description=getattr(region, "empty_message", None)
                    or "No data slices declared.",
                )
            else:
                body = LazyTabPanel(
                    region_name=region_name,
                    tabs=tuple(built_lazy),
                    empty_message=getattr(region, "empty_message", None) or "No data available.",
                )
            return _wrap_surface(title, "list", body)

        # Phase 4A fallback: pre-loaded tabs via eager Tabs primitive
        raw_tabs = ctx.get("tabs") or ctx.get("slices") or []
        if not raw_tabs:
            body = EmptyState(
                title="No tabs",
                description=getattr(region, "empty_message", None) or "No data slices declared.",
            )
            return _wrap_surface(title, "list", body)

        built: list[tuple[str, object]] = []
        seen_keys = set()
        for tab in raw_tabs:
            if not isinstance(tab, dict):
                continue
            key = str(tab.get("key") or tab.get("label") or f"tab_{len(built)}")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            items = tab.get("items") or []
            cols = tab.get("columns") or []
            tab_body: Fragment
            if not items:
                tab_body = EmptyState(title="No items", description="")
            elif not cols:
                tab_body = EmptyState(title="No columns", description="")
            else:
                column_labels = tuple(c.get("label", c.get("key", "")) for c in cols)
                rows_data = tuple(
                    tuple(str(item.get(c["key"], "")) for c in cols) for item in items
                )
                tab_body = Table(columns=column_labels, rows=rows_data)
            built.append((key, tab_body))

        if not built:
            body = EmptyState(title="No tabs", description="")
        else:
            body = Tabs(tabs=tuple(built))

        return _wrap_surface(title, "list", body)
