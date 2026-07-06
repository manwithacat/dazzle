"""Interactive-family render mixin.

Houses the 13 interactive primitives — anything that emits HTMX
attributes (buttons, links, hyperlinks, pagination), inline editing
controls, or chrome around list regions (filter bar, sort headers,
date range, CSV export, search box, confirm gate):

  - _emit_button
  - _emit_link
  - _emit_interactive
  - _emit_inline_edit
  - _emit_toolbar
  - _emit_create_button
  - _emit_pagination
  - _emit_search_box
  - _emit_confirm_gate
  - _emit_filter_bar
  - _emit_sort_header
  - _emit_csv_export_button
  - _emit_date_range_picker

Also houses `_emit_bulk_action_toolbar` (convergence C1.1: the bulk
toolbar on the HM grid controller's seams — Delete posts to the C0b
`/bulk` route, Clear + Select-all-matching ride the delegated markers).

All methods only call `self._emit(child, ctx)` for recursion, plus
the module-level helpers `_hx_attrs` and `_pagination_pages` from
`._helpers`.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    BulkActionToolbar,
    Button,
    ConfirmCheckItem,
    ConfirmGate,
    CreateButton,
    CsvExportButton,
    DateRangePicker,
    FilterBar,
    FilterColumn,
    InlineEdit,
    Interactive,
    Link,
    ListFilterBar,
    Pagination,
    SearchBox,
    SortHeader,
    Toolbar,
)
from dazzle.render.fragment.renderer._helpers import _hx_attrs, _pagination_pages

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


# Bulk-action toolbar (convergence C1.1): rides the HM grid controller's
# seams. Delete = `[data-dz-grid-bulk-action="delete"]` posting form-encoded
# to `{endpoint}/bulk` (the C0b route) behind an hx-confirm dialog, with
# `data-dz-grid-bulk-refresh` re-fetching rows + footer after the POST
# settles (two-request pattern — the response is JSON, nothing swaps).
# "Select all N matching" escalates a page selection to the whole matched
# query (total mirrored from the footer's data-dz-grid-total). Visibility
# stays CSS-driven via `[data-dz-bulk-count]` on the grid root (#978 /
# ADR-0022; written by dz-grid.js's sync()).
_BULK_DELETE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<polyline points="3 6 5 6 21 6"></polyline>'
    '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>'
    '<path d="M10 11v6"></path>'
    '<path d="M14 11v6"></path>'
    '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>'
    "</svg>"
)


class _RenderInteractiveMixin:
    """Mixin adding the 13 interactive-family `_emit_*` methods to
    `FragmentRenderer`. Same pattern as the other render mixins.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    # Button IR uses a semantic variant vocabulary; button.css skins on the
    # canonical data-dz-variant set (ghost/outline/destructive/primary). Map
    # the two here — the render layer is where authoring vocab meets CSS.
    _VARIANT_MAP = {
        "primary": "primary",
        "secondary": "outline",
        "danger": "destructive",
        "ghost": "ghost",
    }

    def _emit_button(self, b: Button, ctx: RenderContext) -> str:
        tokens = b.tokens if b.tokens is not None else ctx.tokens.button
        # Canonical button: one base class + data-dz-variant / data-dz-size
        # attributes (matches button.css; the old dz-button--* BEM classes
        # matched no CSS, so substrate buttons rendered unskinned).
        variant_attrs = f' data-dz-variant="{self._VARIANT_MAP[b.variant]}"'
        if tokens.size == "sm":
            variant_attrs += ' data-dz-size="sm"'
        attrs = _hx_attrs(
            hx_get=b.hx_get,
            hx_post=b.hx_post,
            hx_put=b.hx_put,
            hx_delete=b.hx_delete,
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
        # visibility="hidden" → the native `hidden` attribute (actually hides
        # it); the old dz-button--visibility-hidden class matched no CSS.
        hidden = " hidden" if b.visibility == "hidden" else ""
        action_attr = self._action_attrs(b.data_action, ctx)
        label = ctx.escape(b.label)
        return (
            f'<button type="button" class="dz-button"{variant_attrs}'
            f"{action_attr}{attr_str}{disabled}{hidden}>{label}</button>"
        )

    @staticmethod
    def _action_attrs(data_action: str, ctx: RenderContext) -> str:
        """Build the action anchors from `data_action` (`"{entity}.{verb}"`):
        `data-dazzle-action` + the `data-dz-action` (verb) / `data-dz-entity`
        pair that `dz-analytics.js` delegates on (ADR-0049 Phase 2)."""
        if not data_action:
            return ""
        entity, sep, verb = data_action.partition(".")
        out = f' data-dazzle-action="{ctx.escape_attr(data_action)}"'
        if sep:
            out += (
                f' data-dz-action="{ctx.escape_attr(verb)}"'
                f' data-dz-entity="{ctx.escape_attr(entity)}"'
            )
        return out

    def _emit_link(self, link: Link, ctx: RenderContext) -> str:
        href = ctx.escape_attr(str(link.href))
        action_attr = self._action_attrs(link.data_action, ctx)
        tab_attr = ' target="_blank" rel="noopener noreferrer"' if link.new_tab else ""
        return (
            f'<a class="dz-link" href="{href}"{action_attr}{tab_attr}>{ctx.escape(link.label)}</a>'
        )

    def _emit_interactive(self, iw: Interactive, ctx: RenderContext) -> str:
        attrs = _hx_attrs(
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

    def _emit_create_button(self, b: CreateButton, ctx: RenderContext) -> str:
        """Render a CreateButton matching legacy `filterable_table.html`
        create-button shape (Phase 3 of #1029).

        Carries `data-dazzle-action="{entity_name}.create"` — the RBAC
        contract checker's anchor — plus the 12×12 `+` icon SVG and a
        "New {entity_name}" label (or caller's custom label)."""
        href_attr = ctx.escape_attr(str(b.href))
        action_attr = ctx.escape_attr(f"{b.entity_name}.create")
        # #1487: prefer the declared display title; fall back to humanising the
        # raw entity identifier only when no title is declared.
        label = b.label or f"New {b.entity_title or b.entity_name.replace('_', ' ')}"
        return (
            f'<a href="{href_attr}" '
            f'data-dazzle-action="{action_attr}" '
            f'class="dz-button" data-dz-variant="primary" data-dz-size="sm">'
            f'<svg width="12" height="12" viewBox="0 0 12 12" fill="none" '
            f'aria-hidden="true" xmlns="http://www.w3.org/2000/svg">'
            f'<path d="M6 1v10M1 6h10" stroke="currentColor" '
            f'stroke-width="1.5" stroke-linecap="round"/>'
            f"</svg>"
            f"{ctx.escape(label)}"
            f"</a>"
        )

    def _emit_bulk_action_toolbar(self, b: BulkActionToolbar, ctx: RenderContext) -> str:
        """Render the bulk toolbar on the HM grid controller's seams
        (convergence C1.1) — see the primitive's docstring for the contract."""
        endpoint = ctx.escape_attr(b.endpoint)
        return (
            '<div class="dz-bulk-actions">'
            '<button type="button" class="dz-bulk-matching" data-dz-grid-select-all-matching>'
            "Select all <span data-dz-grid-matching-total>…</span> matching</button>"
            '<button type="button" class="dz-bulk-delete" '
            'data-dz-grid-bulk-action="delete" data-dz-grid-bulk-refresh '
            # hx-swap=none: the two-request pattern swaps NOTHING on the POST
            # (without it htmx-4 swaps the JSON response into the button).
            'hx-swap="none" '
            f'hx-post="{endpoint}/bulk" '
            'hx-confirm="Delete the selected items? This cannot be undone.">'
            f"{_BULK_DELETE_SVG}"
            "<span>Delete <span data-dz-bulk-count-target>0</span> "
            'item<span class="dz-bulk-plural">s</span></span>'
            "</button>"
            '<button type="button" class="dz-bulk-clear" data-dz-grid-clear>'
            "Clear selection"
            "</button>"
            "</div>"
        )

    def _emit_pagination(self, p: Pagination, ctx: RenderContext) -> str:
        """Render a Pagination matching legacy `table_pagination.html`
        byte-equivalent shape (Phase 2 of #1029).

        Wraps the LIST adapter's table when total > page_size; emits
        the row-summary on the left and bounded page-button row on
        the right. Each button is htmx-driven; sort/filter/search
        state preserved via the opaque `extra_query` carried on the
        primitive."""
        if p.total <= p.page_size:
            return ""
        total_pages = (p.total + p.page_size - 1) // p.page_size
        endpoint_str = ctx.escape_attr(str(p.endpoint))
        target = ctx.escape_attr(f"#{p.region_name}-body")
        extra = ctx.escape_attr(p.extra_query) if p.extra_query else ""
        pages = _pagination_pages(p.page, total_pages)
        page_html_parts: list[str] = []
        for entry in pages:
            if entry is None:
                page_html_parts.append(
                    '<span class="dz-pagination-ellipsis" aria-hidden="true">…</span>'
                )
                continue
            is_current = entry == p.page
            cls = "dz-pagination-page is-current" if is_current else "dz-pagination-page"
            current_attr = ' aria-current="page"' if is_current else ""
            page_html_parts.append(
                f'<button class="{cls}"{current_attr} '
                f'hx-get="{endpoint_str}?page={entry}&page_size={p.page_size}{extra}" '
                f'hx-target="{target}" hx-swap="innerMorph" '
                f'hx-headers=\'{{"Accept": "text/html"}}\' '
                f'hx-indicator="#{ctx.escape_attr(p.region_name)}-loading">'
                f"{entry}"
                f"</button>"
            )
        rows_label = "row" if p.total == 1 else "rows"
        return (
            # data-dz-grid-total: the server-authoritative matched total the HM
            # grid primitive reads (all-matching selection) — convergence C0a.
            # C1 GATE: `data-dz-grid-pagination` must land on THIS element
            # (matchedTotal() reads the total off the marker's carrier).
            f'<div class="dz-pagination" data-dz-grid-total="{p.total}">'
            f'<span class="dz-pagination-summary">'
            f'<span class="dz-bulk-summary-selected">'
            f"<span data-dz-bulk-count-target>0</span> of {p.total} selected"
            f"</span>"
            f'<span class="dz-bulk-summary-rows">{p.total} {rows_label}</span>'
            f"</span>"
            f'<div class="dz-pagination-pages">{"".join(page_html_parts)}</div>'
            f"</div>"
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
                # Required items get the data attribute the delegated
                # dz-confirm-gate controller recounts on every change.
                required_attrs = 'data-dz-required="true" ' if item.required else ""
                # spans, not divs — a <label> only admits phrasing content
                # (the HM gallery's vnu gate caught the div-in-label the
                # legacy template shipped); display:block lives in the CSS.
                caption_html = (
                    f'<span class="dz-confirm-caption">{ctx.escape(item.caption)}</span>'
                    if item.caption
                    else ""
                )
                return (
                    f'<li class="dz-confirm-row" data-dz-required="{required_str}">'
                    f'<input type="checkbox" class="dz-confirm-checkbox" '
                    f"{required_attrs}"
                    f'id="dz-confirm-{i}">'
                    f'<label for="dz-confirm-{i}" class="dz-confirm-row-label">'
                    f'<span class="dz-confirm-title">{ctx.escape(item.title)}</span>'
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
                # State-in-DOM gate (dz-confirm-gate.js): the anchor ships
                # disarmed with its destination parked in
                # data-dz-confirm-href; the controller promotes the href
                # and drops aria-disabled once every required box is
                # ticked. Zero required boxes = armed at SSR (the
                # controller then never needs to fire).
                if required_count == 0:
                    gate_state = f'href="{ctx.escape_attr(c.primary_action_url)}" '
                else:
                    gate_state = 'aria-disabled="true" '
                actions_inner += (
                    f'<a data-dz-confirm-href="{ctx.escape_attr(c.primary_action_url)}" '
                    f"{gate_state}"
                    f'class="dz-confirm-primary">'
                    f"{ctx.escape(c.primary_label)}</a>"
                )
            inner = (
                f"<ul data-dz-confirm-gate "
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
                # htmx 4: the select sits inside its own swap target, so the
                # default `change` trigger re-fires on every reprocess after a
                # swap → infinite refetch loop (htmx 2 didn't re-fire change on
                # reprocess). The `changed` modifier gates on an actual value
                # change, so the reprocessed same-value select stays quiet.
                f'hx-trigger="change changed" '
                f'hx-include="closest .filter-bar" '
                f'name="filter_{ctx.escape_attr(col.key)}">'
                f"{options_html}"
                f"</select>"
            )

        selects_html = "".join(_render_column(col) for col in f.columns)
        return f'<div class="dz-queue-filters filter-bar">{selects_html}</div>'

    def _emit_list_filter_bar(self, f: ListFilterBar, ctx: RenderContext) -> str:
        """Task 4d: list filter row that actually filters the list tbody.

        Targets `#{tbody_id}` with `filter[{key}]` param names (what the
        /api list handler parses), `innerMorph` swap, and
        `hx-include="closest [data-dazzle-table]"` so all active filters ride
        along — mirroring the legacy `render_filterable_table` filter bar."""

        # Convergence C1.1: filters are the HM grid controller's seam —
        # `data-dz-grid-filter="filter[key]"` (the bracketed wire key the /api
        # list route parses). On change the controller composes ONE query from
        # ALL current DOM state (sort + every filter + page-size, back at page
        # 1), so a filter change can no longer lose the active sort (the old
        # per-control hx-get + hx-include never carried sort state). Text
        # filters apply on change (blur/Enter) for now — a debounced-input
        # filter seam is a tracked HM follow-up.
        def _control(col: FilterColumn) -> str:
            name = f"filter[{ctx.escape_attr(col.key)}]"
            sel = ctx.escape_attr(col.selected)
            if col.filter_type == "text":
                placeholder = ctx.escape_attr(f"Filter {col.label.lower()}…")
                return (
                    f'<input type="text" name="{name}" class="dz-filter-input" '
                    f'data-dz-grid-filter="{name}" '
                    f'placeholder="{placeholder}" value="{sel}">'
                )
            if col.filter_type == "ref":
                return (
                    f'<select name="{name}" class="dz-filter-select" '
                    f'data-dz-grid-filter="{name}" '
                    f'data-ref-api="{ctx.escape_attr(col.ref_api)}" '
                    f'data-selected-value="{sel}" '
                    'x-init="dzFilterRefSelect($el)">'
                    '<option value="">All</option></select>'
                )
            options_html = '<option value="">All</option>'
            for value, display in col.options:
                selected_attr = " selected" if value == col.selected else ""
                options_html += (
                    f'<option value="{ctx.escape_attr(value)}"{selected_attr}>'
                    f"{ctx.escape(display)}</option>"
                )
            return (
                f'<select name="{name}" class="dz-filter-select" '
                f'data-dz-grid-filter="{name}">'
                f"{options_html}</select>"
            )

        cells = "".join(
            f'<div class="dz-filter-cell">'
            f'<label class="dz-filter-label">{ctx.escape(col.label)}</label>'
            f"{_control(col)}</div>"
            for col in f.columns
        )
        return (
            f'<div class="dz-table-toolbar-filters"><div class="dz-filter-bar">{cells}</div></div>'
        )

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
