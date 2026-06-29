"""IR-to-Fragment translator for surface rendering.

Takes a SurfaceSpec + render context (rows, columns, etc. — same shape
as the Jinja path's context dict) and produces a Fragment tree. The
FragmentRenderer then emits HTML from the tree.

Plan 3 ships the minimum-viable adapter for `mode: list` only — enough
to render simple_task's task_list surface. Subsequent plans add detail,
form, and dashboard modes.
"""

import json
from typing import Any

from dazzle.core.ir.protocols import SurfaceLike, SurfaceMode
from dazzle.render.fragment import (
    URL,
    Button,
    ColumnVisibilityMenu,
    Combobox,
    CreateButton,
    DataListScroll,
    DzTableMount,
    EmptyState,
    Field,
    FileUpload,
    FilterBar,
    FilterColumn,
    FormSection,
    FormStack,
    Fragment,
    FragmentRenderer,
    Heading,
    Link,
    ListFilterBar,
    RawHTML,
    RefPicker,
    Region,
    RelatedGroup,
    RelatedTab,
    Row,
    SearchBox,
    SearchSelect,
    SortHeader,
    Stack,
    Submit,
    Surface,
    Table,
    TargetSelector,
    Text,
)
from dazzle.render.fragment.format_cell import ResolvedFormat, format_cell
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.html import esc as _html_esc


def _esc_attr(s: str) -> str:
    """Attribute-escape for the few RawHTML escape-hatch interpolations."""
    return _html_esc(str(s), quote=True)


def render_generic_detail(surface: SurfaceLike, ctx: dict[str, Any]) -> str:
    """ADR-0049 Phase 2 (#1297): render the framework's generic detail body via
    the typed substrate, for a custom `mode: view` renderer that wants to wrap
    the standard detail with bespoke chrome. The substrate-backed replacement
    for the deleted `page.runtime.render_detail_view(ctx["detail_context"])` —
    the custom renderer already has `surface` + the dispatch `ctx`."""
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(surface, ctx))


def _detail_field_value(f: dict[str, Any]) -> Fragment:
    """ADR-0049 Phase 2 (flip review): render one detail field VALUE through the
    same typed-cell core the list rows use (`_render_cell_display`) — so `ref`
    (display name), `money`/`currency`, `badge` (WCAG chrome), `bool` (icon),
    `file` (download link) all render at parity instead of as a raw value."""
    value = f.get("value")
    if value in (None, "", "—"):
        return Text("—")
    col = {
        "type": str(f.get("kind", "text") or "text"),
        "currency_code": str(f.get("currency_code", "") or ""),
        "semantic_map": dict(f.get("semantic_map", {}) or {}),
    }
    return RawHTML(_render_cell_display(col, value))


class FragmentSurfaceAdapter:
    """Translate a SurfaceSpec + context into a Fragment tree."""

    def build(self, surface: SurfaceLike, ctx: dict[str, Any]) -> Fragment:
        if surface.mode == SurfaceMode.LIST:
            return self._build_list(surface, ctx)
        if surface.mode == SurfaceMode.VIEW:
            return self._build_view(surface, ctx)
        if surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
            return self._build_form(surface, ctx, mode=surface.mode)
        raise NotImplementedError(
            f"FragmentSurfaceAdapter does not yet support mode {surface.mode.name!r}; "
            f"Plans 3+8+9 cover LIST/VIEW/CREATE/EDIT. CUSTOM lands later."
        )

    def _build_list(self, surface: SurfaceLike, ctx: dict[str, Any]) -> Surface:
        """Substrate-canonical list surface (ADR-0049 Phase 1, Task 4e).

        First-paints the chrome + an empty skeleton `<tbody hx-trigger="load">`;
        rows hydrate from `/api` via `render_data_row` (D2). The dzTable
        controller mounts on the Region (D3) and drives sort/bulk/inline/
        column-visibility; the `/api` handler derives its `table_id` from the
        `HX-Target` header (the tbody id), so the OOB pagination + row swaps
        land automatically. The free-text search is the FTS dropdown
        (substrate-canonical divergence from the legacy inline filter); the
        filter selects narrow the list in place via `ListFilterBar`.
        """
        title = surface.title or surface.name.replace("_", " ").title()
        columns: list[dict[str, Any]] = ctx.get("columns", [])
        entity_name = (getattr(surface, "entity_ref", "") or "").strip()
        entity_title = str(ctx.get("entity_title", "") or "")
        create_url = str(ctx.get("create_url", "") or "").strip()
        page_size = int(ctx.get("page_size", 20) or 20)
        endpoint = str(ctx.get("endpoint", "") or "").strip()
        region_name = str(ctx.get("region_name", "") or "").strip()
        search_enabled = bool(ctx.get("search_enabled", False))
        search_fields = list(ctx.get("search_fields", []) or [])
        filter_values = dict(ctx.get("filter_values", {}) or {})
        bulk_actions = bool(ctx.get("bulk_actions", False))
        inline_editable = tuple(ctx.get("inline_editable", []) or ())
        sort_field = str(ctx.get("sort_field", "") or "")
        sort_dir = "desc" if str(ctx.get("sort_dir", "asc") or "asc").lower() == "desc" else "asc"
        refresh_interval = ctx.get("refresh_interval")
        search_first = bool(ctx.get("search_first", False))
        paginated = str(ctx.get("pagination_mode", "pages") or "pages") != "infinite"

        # The dzTable id; the tbody hydrate target is `#{table_id}-body`, and
        # the /api handler strips `-body` off HX-Target to recover it.
        table_id = region_name or entity_name
        tbody_id = f"{table_id}-body"
        loading_sr = f"#{table_id}-loading-sr"

        visible = [c for c in columns if not c.get("hidden")]
        col_labels = tuple(str(c.get("label", c.get("key", ""))) for c in visible)
        col_keys = tuple(str(c.get("key", "")) for c in visible)
        sortable_keys = tuple(str(c.get("key", "")) for c in visible if c.get("sortable"))

        # Skeleton hydrate endpoint carries the default sort (matches legacy).
        hx_endpoint = endpoint
        if sort_field and endpoint:
            sep = "&" if "?" in endpoint else "?"
            hx_endpoint = f"{endpoint}{sep}sort={sort_field}&dir={sort_dir}"
        # search_first lists omit the load trigger (the search drives the fetch).
        hx_trigger = "" if search_first else "load"

        table = Table(
            columns=col_labels,
            rows=(),
            skeleton=True,
            bulk_select=bulk_actions,
            tbody_id=tbody_id,
            hx_endpoint=hx_endpoint,
            hx_trigger=hx_trigger,
            refresh_interval=int(refresh_interval) if refresh_interval else None,
            loading_indicator=loading_sr,
            caption=title,
            has_actions=True,
            column_keys=col_keys,
            sortable_keys=sortable_keys,
        )

        empty_title, empty_description = _pick_empty_state(ctx)
        create_label = f"New {entity_title or entity_name.replace('_', ' ')}" if create_url else ""
        shell = DataListScroll(
            table=table,
            table_id=table_id,
            page_size=page_size,
            aria_label=title,
            empty_title=empty_title,
            empty_description=empty_description,
            empty_action_href=create_url,
            empty_action_label=create_label,
            paginated=paginated,
        )

        # Toolbar: FTS search box (canonical) + working list filters.
        toolbar: list[Fragment] = []
        if search_enabled and search_fields and entity_name:
            placeholder = f"Search {entity_title.lower()}…" if entity_title else "Search…"
            toolbar.append(
                SearchBox(
                    name=f"{region_name or entity_name}_search",
                    fts_endpoint=URL(f"/_dazzle/fts/{entity_name}?html=1"),
                    placeholder=placeholder,
                )
            )
        filter_cols = tuple(
            FilterColumn(
                key=str(c.get("key", "")),
                label=str(c.get("label", "") or c.get("key", "")),
                options=tuple(_filter_option(o) for o in (c.get("filter_options") or [])),
                selected=str(filter_values.get(c.get("key", ""), "")),
                filter_type=(
                    "ref" if c.get("filter_ref_entity") else c.get("filter_type", "select")
                ),
                ref_api=str(c.get("filter_ref_api", "")),
            )
            # a key-less column can't be filtered (no param name) — skip it
            # rather than 500 the page (D4 removes the legacy fallback).
            for c in visible
            if c.get("filterable") and c.get("key")
        )
        if filter_cols and endpoint:
            toolbar.append(
                ListFilterBar(
                    tbody_id=tbody_id,
                    endpoint=URL(endpoint),
                    columns=filter_cols,
                    loading_indicator=loading_sr,
                )
            )

        # Body: [BulkActionToolbar?] + toolbar + the list-table shell.
        body_children: list[Fragment] = []
        if bulk_actions:
            from dazzle.render.fragment import BulkActionToolbar

            body_children.append(BulkActionToolbar())
        body_children.extend(toolbar)
        body_children.append(shell)
        body: Fragment = (
            Stack(children=tuple(body_children), gap="sm") if len(body_children) > 1 else shell
        )

        # Header: title + column-visibility menu (>3 visible cols) + create.
        header_children: list[Fragment] = [Heading(title, level=1)]
        if len(visible) > 3:
            header_children.append(
                ColumnVisibilityMenu(
                    columns=tuple(
                        (str(c.get("key", "")), str(c.get("label", c.get("key", ""))))
                        for c in visible
                    )
                )
            )
        if create_url and entity_name:
            header_children.append(
                CreateButton(
                    href=URL(create_url),
                    entity_name=entity_name,
                    entity_title=entity_title,
                )
            )
        header: Fragment = (
            Row(children=tuple(header_children), align="center", gap="md")
            if len(header_children) > 1
            else Heading(title, level=1)
        )

        mount = DzTableMount(
            table_id=table_id,
            endpoint=endpoint,
            sort_field=sort_field,
            sort_dir=sort_dir,
            inline_editable=inline_editable,
            bulk_actions=bulk_actions,
            entity_name=entity_name,
        )
        return Surface(
            header=header,
            # Region carries `data-dazzle-table` so the UX contract checker +
            # htmx `closest [data-dazzle-table]` selectors find the container.
            body=Region(kind="list", body=body, data_table=entity_name, mount=mount),
        )

    def _build_view(self, surface: SurfaceLike, ctx: dict[str, Any]) -> Fragment:
        """Detail surface — fields + action toolbar + related groups.

        Plan 8: each field renders as a Row of (Heading-level-4 label,
        Text value). Stack groups them inside Region(kind="detail").
        Plan 10: when ctx carries `related_groups`, additional
        Region(kind="related") entries are appended after the detail
        body — each emits a Heading (group title) + Skeleton placeholder.

        Issue #1030: the action toolbar (Edit Link, Delete Button,
        state-machine transition Buttons, integration-action Buttons,
        external-link Links) renders as a Row prepended to the detail
        body. The legacy template emits these in the surface header;
        Region(kind="detail") body keeps them adjacent to the fields
        they act on.
        """
        title = surface.title or surface.name.replace("_", " ").title()
        fields: list[dict[str, Any]] = ctx.get("fields", [])

        detail_body: Fragment
        if not fields:
            detail_body = EmptyState(
                title="No data",
                description="This record has no displayable fields.",
            )
        else:
            field_rows = tuple(
                Row(
                    children=(
                        Heading(str(f.get("label", f.get("key", ""))), level=4),
                        _detail_field_value(f),
                    ),
                    align="start",
                )
                for f in fields
            )
            detail_body = Stack(children=field_rows, gap="sm")

        entity_name = (getattr(surface, "entity_ref", "") or ctx.get("entity_name") or "").strip()
        item_id = str(ctx.get("item_id", "") or "")

        # Task 3b: audit-history slot (#956) — an htmx-loaded region. Appended
        # to the detail body when `show_history` is opted in and we have an id.
        if ctx.get("show_history") and item_id and entity_name:
            ent = _esc_attr(entity_name)
            iid = _esc_attr(item_id)
            audit = RawHTML(
                f'<div class="dz-detail-audit-history" '
                f'hx-get="/_dazzle/audit-history/{ent}/{iid}" '
                'hx-trigger="load" hx-swap="innerHTML">'
                '<p class="dz-audit-history__loading" aria-live="polite">'
                "Loading history…</p></div>"
            )
            detail_body = Stack(children=(detail_body, audit), gap="md")

        # ADR-0049 Phase 2 (flip review): peek mode (`?peek=1`) injects this body
        # into a list-row `<td>` panel. Omit the page-level Surface header (no
        # second `<h1>` on the page) + the Back link (you don't navigate back
        # from an inline peek) — content-only, like the legacy peek body.
        peek = bool(ctx.get("peek"))

        # Issue #1030: action toolbar — Back / Edit / Delete / transitions /
        # integration / external-link actions.
        back_url = str(ctx.get("back_url", "") or "").strip()
        back = (Link(label="← Back", href=URL(back_url)),) if (back_url and not peek) else ()
        actions = back + self._build_detail_actions(ctx)
        if actions:
            detail_body = Stack(
                children=(Row(children=actions, align="start"), detail_body),
                gap="md",
            )

        def _detail_region(body: Fragment) -> Region:
            return Region(kind="detail", body=body, data_entity=entity_name, data_entity_id=item_id)

        def _wrap(region: Region) -> Fragment:
            # Peek = content-only (the Region itself, no Surface chrome / h1).
            return region if peek else Surface(header=Heading(title, level=1), body=region)

        related_groups: list[dict[str, Any]] = ctx.get("related_groups", []) or []
        if not related_groups:
            return _wrap(_detail_region(detail_body))

        # ADR-0049 Phase 2 Task 3a: render the FETCHED related-group content
        # (table / status_cards / file_list) instead of a Skeleton placeholder.
        related_regions: list[Fragment] = []
        for group in related_groups:
            group_title = str(group.get("label") or group.get("title") or "Related")
            related_regions.append(
                Region(
                    kind="related",
                    body=Stack(
                        children=(
                            Heading(group_title, level=2),
                            self._build_related_group(group, item_id),
                        ),
                        gap="sm",
                    ),
                )
            )

        wrapper = Stack(
            children=(Region(kind="detail", body=detail_body), *related_regions),
            gap="md",
        )

        # Outer Region uses kind="detail" since the surface IS a detail
        # surface; the inner sub-regions carry kind="related" for CSS.
        return _wrap(_detail_region(wrapper))

    def _build_list_toolbar(
        self,
        *,
        search_enabled: bool,
        search_fields: list[str],
        filter_values: dict[str, str],
        columns: list[dict[str, Any]],
        entity_name: str,
        entity_title: str,
        endpoint: str,
        region_name: str,
    ) -> tuple[Fragment, ...]:
        """Issue #1029 phase 5: compose the search box + filter bar
        for the list region toolbar.

        SearchBox emitted when `search_enabled` AND `search_fields`
        non-empty AND we have an entity_name to derive the FTS
        endpoint. FilterBar emitted when at least one column carries
        `filterable=True`. Returns the ordered tuple of toolbar
        primitives — empty when neither is configured."""
        toolbar: list[Fragment] = []

        if search_enabled and search_fields and entity_name:
            # #1487 follow-on: name the entity by its declared title in the
            # search placeholder ("Search curriculum plan…"), not the raw id.
            placeholder = f"Search {entity_title.lower()}…" if entity_title else "Search…"
            toolbar.append(
                SearchBox(
                    name=f"{region_name or entity_name}_search",
                    fts_endpoint=URL(f"/_dazzle/fts/{entity_name}?html=1"),
                    placeholder=placeholder,
                )
            )

        filter_columns = tuple(
            FilterColumn(
                key=col["key"],
                label=str(col.get("label", col["key"])),
                options=tuple(col.get("filter_options", []) or ()),
                selected=str(filter_values.get(col["key"], "")),
            )
            for col in columns
            if col.get("filterable")
        )
        if filter_columns and endpoint and region_name:
            toolbar.append(
                FilterBar(
                    endpoint=URL(endpoint),
                    region_name=region_name,
                    columns=filter_columns,
                )
            )

        return tuple(toolbar)

    def _build_related_group(self, group: dict[str, Any], item_id: str) -> Fragment:
        """ADR-0049 Phase 2 Task 3a: build a `RelatedGroup` primitive from the
        fetched related-group ctx. Cells are formatted via `_format_cell`
        (typed); drill + create hrefs are pre-built here (page-free renderer)."""
        tabs: list[RelatedTab] = []
        for tab in group.get("tabs", []) or []:
            cols = tab.get("columns", []) or []
            headers = tuple(str(c.get("label", c.get("key", ""))) for c in cols)
            rows: list[tuple[str, ...]] = []
            drills: list[str] = []
            tmpl = str(tab.get("detail_url_template", "") or "")
            for record in tab.get("rows", []) or []:
                rec = record if isinstance(record, dict) else {}
                cells = tuple(
                    _format_cell(
                        rec.get(c.get("key", "")),
                        str(c.get("type", "text") or "text"),
                        str(c.get("currency_code", "") or ""),
                        "",
                        "",
                    )
                    for c in cols
                )
                rows.append(cells)
                rid = str(rec.get("id", "") or "")
                drills.append(tmpl.replace("{id}", rid) if (tmpl and rid) else "")
            create_url = str(tab.get("create_url", "") or "")
            create_href = create_action = create_label = ""
            if create_url:
                sep = "&" if "?" in create_url else "?"
                filter_field = str(tab.get("filter_field", "") or "")
                create_href = f"{create_url}{sep}{filter_field}={item_id}"
                ftf = str(tab.get("filter_type_field", "") or "")
                if ftf:
                    create_href += f"&{ftf}={tab.get('filter_type_value', '') or ''}"
                create_action = f"{tab.get('entity_name', '') or ''}.create"
                create_label = str(tab.get("label", "") or "")
            tabs.append(
                RelatedTab(
                    tab_id=str(tab.get("tab_id", "") or ""),
                    label=str(tab.get("label", "") or ""),
                    headers=headers,
                    rows=tuple(rows),
                    row_drill=tuple(drills),
                    create_href=create_href,
                    create_action=create_action,
                    create_label=create_label,
                )
            )
        return RelatedGroup(
            group_id=str(group.get("group_id", "") or ""),
            label=str(group.get("label", "") or ""),
            display=str(group.get("display", "table") or "table"),
            tabs=tuple(tabs),
            is_auto=bool(group.get("is_auto", False)),
        )

    def _build_detail_actions(self, ctx: dict[str, Any]) -> tuple[Fragment, ...]:
        """Issue #1030: build the per-record action row from ctx.

        Order: Edit Link (primary) → state-machine transitions →
        integration actions → external links → Delete Button (danger,
        confirm-gated). Empty tuple when no actions are configured."""
        actions: list[Fragment] = []
        edit_url = ctx.get("edit_url") or ""
        delete_url = ctx.get("delete_url") or ""
        entity_name = ctx.get("entity_name") or "record"
        status_field = str(ctx.get("status_field") or "status")
        transitions = ctx.get("transitions") or []
        integration_actions = ctx.get("integration_actions") or []
        external_links = ctx.get("external_link_actions") or []

        if edit_url:
            actions.append(
                Link(
                    label="Edit",
                    href=URL(str(edit_url)),
                    data_action=f"{entity_name}.edit",
                )
            )

        for t in transitions:
            api_url = t.get("api_url") or ""
            label = t.get("label") or ""
            to_state = str(t.get("to_state") or "")
            if not api_url or not label:
                continue
            # ADR-0049 Phase 2: transitions are hx-PUT with the status field →
            # target state in hx-vals (the legacy semantics); the prior hx-post
            # without vals never told the endpoint which state to move to.
            actions.append(
                Button(
                    label=str(label),
                    variant="secondary",
                    hx_put=URL(str(api_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                    hx_vals=json.dumps({status_field: to_state}),
                    data_action=f"{entity_name}.transition.{to_state}",
                )
            )

        for a in integration_actions:
            api_url = a.get("api_url") or ""
            label = a.get("label") or ""
            if not api_url or not label:
                continue
            iname = str(a.get("integration_name") or "")
            mname = str(a.get("mapping_name") or "")
            actions.append(
                Button(
                    label=str(label),
                    variant="secondary",
                    hx_post=URL(str(api_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                    data_action=f"{entity_name}.integration.{iname}.{mname}",
                )
            )

        for link in external_links:
            label = link.get("label") or ""
            url = link.get("url") or ""
            if not label or not url:
                continue
            # External links use Link primitive (no htmx — full nav).
            actions.append(
                Link(
                    label=str(label),
                    href=URL(str(url)),
                    new_tab=bool(link.get("new_tab")),
                    data_action=f"{entity_name}.external.{link.get('name') or ''}",
                )
            )

        if delete_url:
            actions.append(
                Button(
                    label="Delete",
                    variant="danger",
                    hx_delete=URL(str(delete_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                    hx_confirm=f"Delete this {str(entity_name).lower()}?",
                    data_action=f"{entity_name}.delete",
                )
            )

        return tuple(actions)

    def _build_form(
        self,
        surface: SurfaceLike,
        ctx: dict[str, Any],
        *,
        mode: SurfaceMode,
    ) -> Surface:
        """CREATE/EDIT form surface — FormStack with type-aware widgets.

        Both modes share infrastructure; the only differences are:
        - initial_value (empty in CREATE, from row in EDIT — both flow
          through ctx["fields"][i]["value"], so the adapter is uniform)
        - Submit label and action URL (carried via ctx["submit_label"]
          and ctx["action"])
        """
        title = surface.title or surface.name.replace("_", " ").title()
        fields_in: list[dict[str, Any]] = ctx.get("fields", [])
        action = ctx.get("action", "") or "/"
        method = ctx.get("method", "POST")
        submit_label = ctx.get(
            "submit_label",
            "Save" if mode == SurfaceMode.EDIT else "Create",
        )

        body: Fragment
        # v0.67.0: map dispatch ctx method (lowercase per FormContext) to
        # the FormStack typed method. PUT support added so EDIT-mode
        # forms emit hx-put per the legacy form contract.
        method_upper = str(method).upper() if method else "POST"
        method_lit = method_upper if method_upper in ("GET", "POST", "PUT") else "POST"
        # RBAC contract attrs threaded onto the <form>.
        form_entity_name = (getattr(surface, "entity_ref", "") or "").strip()
        form_mode = "edit" if mode == SurfaceMode.EDIT else "create"
        sections_in: list[dict[str, Any]] = ctx.get("sections", []) or []
        if not fields_in:
            body = EmptyState(
                title="No fields",
                description="This form has no inputs.",
            )
        elif sections_in:
            # Issue #1031: multi-section forms wrap each section's
            # fields in a FormSection inside the outer FormStack —
            # one `<form>` element with `<section>` groupings, single
            # Submit at the bottom commits all fields together. Falls
            # back to the flat FormStack path for single-section forms.
            section_primitives: list[FormSection] = []
            for s in sections_in:
                section_fields = s.get("fields", []) or []
                if not section_fields:
                    continue
                section_primitives.append(
                    FormSection(
                        title=str(s.get("title") or s.get("name", "")),
                        fields=tuple(_field_to_primitive(f) for f in section_fields),
                        note=str(s.get("note") or ""),
                    )
                )
            body = FormStack(
                action=URL(action),
                fields=tuple(section_primitives),
                method=method_lit,  # type: ignore[arg-type]
                submit=Submit(label=submit_label),
                entity_name=form_entity_name,
                mode=form_mode,  # type: ignore[arg-type]
            )
        else:
            primitives = tuple(_field_to_primitive(f) for f in fields_in)
            body = FormStack(
                action=URL(action),
                fields=primitives,
                method=method_lit,  # type: ignore[arg-type]
                submit=Submit(label=submit_label),
                entity_name=form_entity_name,
                mode=form_mode,  # type: ignore[arg-type]
            )

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="form", body=body),
        )


def _field_to_primitive(
    field_dict: dict[str, Any],
) -> "Field | Combobox | RefPicker | SearchSelect | FileUpload":
    """Map a field-shape dict to the right Fragment form primitive.

    The `kind` carried in field_dict is the *widget* kind — matching
    `FieldContext.type` from `dazzle.page.runtime.template_context` (text,
    textarea, select, checkbox, number, date, datetime, email, url,
    money, file, etc.) — NOT the DSL FieldType.kind. The page route's
    `_build_dispatch_ctx` reads `field.type` directly off the FieldContext
    and passes it through as `kind`.

    Disambiguation between enum-vs-ref (both arrive as widget kind
    `"select"`) uses the data already on the field_dict: presence of
    `ref_api` ⇒ RefPicker, presence of `options` ⇒ Combobox.

    Until v0.66.44 this function expected DSL kinds and silently swapped
    widgets (str→textarea, text→input, enum/bool→input) for any DSL-driven
    call — surfaced by the cyfuture pilot in #1026.
    """
    name = str(field_dict.get("name", ""))
    label = str(field_dict.get("label", name))
    required = bool(field_dict.get("required", False))
    placeholder = str(field_dict.get("placeholder", ""))
    initial_value = str(field_dict.get("value", "") or "")
    kind = str(field_dict.get("kind", "text")).lower()

    # FILE: issue #1033 — distinguished by widget kind "file". Returns
    # a FileUpload primitive carrying the multipart upload endpoint
    # (defaults to /uploads when the dispatch ctx didn't supply one).
    if kind == "file":
        return FileUpload(
            name=name,
            label=label,
            upload_url=URL(str(field_dict.get("upload_url", "") or "/uploads")),
            required=required,
            accept=str(field_dict.get("accept", "") or ""),
            max_size_bytes=int(field_dict.get("max_size_bytes", 0) or 0),
            initial_value=initial_value,
            initial_label=str(field_dict.get("initial_label", "") or ""),
        )

    # SEARCH_SELECT: a `source:` typeahead field. Distinguished by a
    # non-empty `source` dict (endpoint/debounce/min_chars), threaded by
    # `_build_dispatch_ctx`. Checked before ref_api/options — a source
    # field is a remote-search combobox, not a static enum or full-list ref.
    source = field_dict.get("source") or {}
    source_endpoint = str(source.get("endpoint", "") or "").strip() if source else ""
    if source_endpoint:
        return SearchSelect(
            name=name,
            label=label,
            endpoint=URL(source_endpoint),
            required=required,
            placeholder=placeholder,
            debounce_ms=int(source.get("debounce_ms", 300) or 300),
            min_chars=int(source.get("min_chars", 0) or 0),
            initial_value=initial_value,
            initial_label=str(field_dict.get("initial_label", "") or ""),
        )

    # REF: distinguished by presence of a non-empty ref_api in field_dict.
    ref_api = str(field_dict.get("ref_api", "") or "").strip()
    if ref_api:
        return RefPicker(
            name=name,
            label=label,
            ref_api=URL(ref_api),
            required=required,
            initial_value=initial_value,
            initial_label=str(field_dict.get("initial_label", "") or ""),
        )

    # Enum / select: distinguished by presence of options OR widget kind
    # explicitly being "select"/"combobox". Both forms reach the same
    # Combobox primitive; the options tuple is whatever the page route
    # populated from FieldContext.options.
    raw_options = field_dict.get("options")
    if raw_options or kind in ("select", "combobox"):
        opts = tuple((str(v), str(label_)) for v, label_ in (raw_options or []))
        if not opts:
            opts = (("", ""),)  # Combobox requires at least one option
        return Combobox(
            name=name,
            label=label,
            options=opts,
            required=required,
            initial_value=initial_value,
        )

    # Map widget kind to Field.kind. Field._FIELD_KINDS validates the
    # result; an unknown widget kind falls back to plain text.
    widget_to_field_kind: dict[str, str] = {
        "text": "text",
        "textarea": "textarea",
        "email": "email",
        "password": "password",
        "number": "number",
        "money": "number",
        "checkbox": "checkbox",
        "radio": "radio",
        "date": "date",
        "datetime": "datetime-local",
        "datetime-local": "datetime-local",
        "time": "time",
        "url": "url",
        "tel": "tel",
    }
    field_kind = widget_to_field_kind.get(kind, "text")
    return Field(
        name=name,
        label=label,
        kind=field_kind,  # type: ignore[arg-type]
        required=required,
        placeholder=placeholder,
        initial_value=initial_value,
    )


def _filter_option(o: Any) -> tuple[str, str]:
    """Normalise a filter option into a `(value, label)` pair. Dispatch ctx
    supplies either dicts (`{"value":..,"label":..}`) or `(value, label)`
    tuples depending on the column source — accept both (Task 4d)."""
    if isinstance(o, dict):
        return (str(o.get("value", "")), str(o.get("label", "")))
    if isinstance(o, (tuple, list)) and len(o) >= 2:
        return (str(o[0]), str(o[1]))
    return (str(o), str(o))


def _build_column_header(
    *,
    col: dict[str, Any],
    endpoint: str,
    region_name: str,
    current_sort: str,
    current_direction: str,
) -> object:
    """Issue #1029 phase 6: per-column header builder.

    Returns a `SortHeader` primitive when the column is `sortable=True`
    AND endpoint + region_name are configured; falls back to the plain
    string label otherwise. The Table primitive's column tuple is
    `tuple[str | SortHeader, ...]` and the renderer dispatches per cell."""
    label = str(col.get("label", col.get("key", "")))
    if not col.get("sortable") or not endpoint or not region_name:
        return label
    column_key = str(col.get("key", "") or "")
    if not column_key:
        return label
    direction: str = "desc" if current_direction == "desc" else "asc"
    return SortHeader(
        label=label,
        column_key=column_key,
        endpoint=URL(endpoint),
        region_name=region_name,
        current_sort=current_sort,
        current_direction=direction,  # type: ignore[arg-type]
    )


def _pick_empty_state(ctx: dict[str, Any]) -> tuple[str, str]:
    """Issue #1029 phase 4: choose the empty-state title + description
    based on `empty_kind` and the typed empty variants (#807).

    Priority within each kind:
      1. The kind-specific message (`empty_collection` / `empty_filtered`
         / `empty_forbidden`) when set.
      2. The generic `empty_message` field.
      3. A framework default.

    Returns `(title, description)`. The legacy template puts the
    message in the description slot and synthesises a short title
    from the kind (e.g. "No matches" for filtered); we mirror that
    contract here."""
    kind = str(ctx.get("empty_kind", "") or "collection").lower()
    # ADR-0049 Task 5: entity-specific collection title ("No tasks found"),
    # matching the legacy renderer, when the entity label is known.
    entity_label = (
        str(ctx.get("entity_title", "") or ctx.get("entity_name", "") or "")
        .replace("_", " ")
        .strip()
        .lower()
    )
    collection_title = f"No {entity_label}s found" if entity_label else "No items yet"
    typed_keys = {
        "collection": ("empty_collection", collection_title),
        "filtered": ("empty_filtered", "No matches"),
        "forbidden": ("empty_forbidden", "Not available"),
    }
    typed_key, default_title = typed_keys.get(kind, ("empty_collection", "No items yet"))
    typed_value = str(ctx.get(typed_key, "") or "").strip()
    generic_message = str(ctx.get("empty_message", "") or "").strip()
    description = typed_value or generic_message or "Items will appear here when they are added."
    return default_title, description


def _cell_value(item: dict[str, Any], col: dict[str, Any]) -> Any:
    """Pick a column's cell value, preferring a resolved ``{key}_display`` for
    ``ref`` columns (#1471).

    The fetch injects ``{fk}_display`` via ``_inject_display_names`` (FK display
    fast-path), so a ref column should render the referenced row's display field,
    not the raw UUID — mirroring the legacy ``htmx_render`` table path. Falls back
    to the raw key when no display name is present (e.g. the ref wasn't included).
    """
    key = col["key"]
    if col.get("type") == "ref":
        display = item.get(f"{key}_display")
        if display not in (None, ""):
            return display
    return item.get(key)


def _format_cell(
    value: Any,
    kind: str,
    currency_code: str = "",
    format_kind: str = "",
    format_arg: str = "",
) -> str:
    """Stringify a cell value for the typed Table via the pure formatter (#1470).

    Delegates to ``render.fragment.format_cell``, which renders by column kind +
    Python value type (bool→Yes/No, enum→Title Case, money(minor units)→currency,
    float→2dp, datetime→friendly, FK→name) and returns RAW (the renderer escapes).
    An explicit ``format:`` override (``format_kind``/``format_arg`` from the column
    spec, #1470 Phase 2) wins over inference. Replaces the old str()-coerce stub.
    """
    override = ResolvedFormat(format_kind, format_arg or None) if format_kind else None
    return format_cell(value, kind, currency_code=currency_code, override=override)
