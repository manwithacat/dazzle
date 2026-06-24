"""IR-to-Fragment translator for surface rendering.

Takes a SurfaceSpec + render context (rows, columns, etc. — same shape
as the Jinja path's context dict) and produces a Fragment tree. The
FragmentRenderer then emits HTML from the tree.

Plan 3 ships the minimum-viable adapter for `mode: list` only — enough
to render simple_task's task_list surface. Subsequent plans add detail,
form, and dashboard modes.
"""

from typing import Any

from dazzle.core.ir.protocols import SurfaceLike, SurfaceMode
from dazzle.render.fragment import (
    URL,
    Button,
    Combobox,
    CreateButton,
    EmptyState,
    Field,
    FileUpload,
    FilterBar,
    FilterColumn,
    FormSection,
    FormStack,
    Fragment,
    Heading,
    Link,
    Pagination,
    RefPicker,
    Region,
    Row,
    SearchBox,
    Skeleton,
    SortHeader,
    Stack,
    Submit,
    Surface,
    Table,
    TargetSelector,
    Text,
)
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._row_links import _resolve_row_links


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
        title = surface.title or surface.name.replace("_", " ").title()
        items: list[dict[str, Any]] = ctx.get("items", [])
        columns: list[dict[str, Any]] = ctx.get("columns", [])
        entity_name = (getattr(surface, "entity_ref", "") or "").strip()
        create_url = str(ctx.get("create_url", "") or "").strip()
        # Issue #1029 phase 1: per-row drill-down URL.
        detail_url_template = str(ctx.get("detail_url_template", "") or "").strip()
        # Issue #1029 phase 2: pagination footer when total > page_size.
        total = int(ctx.get("total", 0) or 0)
        page = int(ctx.get("page", 1) or 1)
        page_size = int(ctx.get("page_size", 20) or 20)
        endpoint = str(ctx.get("endpoint", "") or "").strip()
        region_name = str(ctx.get("region_name", "") or "").strip()
        # Issue #1029 phase 5: search + filter toolbar.
        search_enabled = bool(ctx.get("search_enabled", False))
        search_fields = list(ctx.get("search_fields", []) or [])
        filter_values = dict(ctx.get("filter_values", {}) or {})
        toolbar_children = self._build_list_toolbar(
            search_enabled=search_enabled,
            search_fields=search_fields,
            filter_values=filter_values,
            columns=columns,
            entity_name=entity_name,
            endpoint=endpoint,
            region_name=region_name,
        )
        # Issue #1029 phase 7: bulk-actions toolbar + per-row checkboxes.
        bulk_actions_enabled = bool(ctx.get("bulk_actions", False)) and bool(items)

        body: Fragment
        if not items:
            # Issue #1029 phase 4: pick the right empty-state message
            # based on `empty_kind` (#807). Priority: typed variant
            # (collection / filtered / forbidden) → generic
            # `empty_message` → framework default.
            empty_title, empty_description = _pick_empty_state(ctx)
            body = EmptyState(title=empty_title, description=empty_description)
        else:
            # Issue #1029 phase 6: sortable columns become SortHeader
            # primitives; non-sortable stay as plain strings. The
            # adapter reads the active `sort_field` / `sort_dir` from
            # ctx so the right column shows its current direction
            # (▲/▼) and its next-click flips, while others always
            # default to ascending.
            sort_field = str(ctx.get("sort_field", "") or "")
            sort_dir_raw = str(ctx.get("sort_dir", "asc") or "asc").lower()
            sort_dir: str = "desc" if sort_dir_raw == "desc" else "asc"
            column_labels = tuple(
                _build_column_header(
                    col=col,
                    endpoint=endpoint,
                    region_name=region_name,
                    current_sort=sort_field,
                    current_direction=sort_dir,
                )
                for col in columns
            )
            rows = tuple(
                tuple(
                    _format_cell(
                        item.get(col["key"]),
                        col.get("type", "text"),
                        col.get("currency_code", ""),
                    )
                    for col in columns
                )
                for item in items
            )
            row_links = (
                _resolve_row_links(items, detail_url_template) if detail_url_template else ()
            )
            # Phase 7: pass per-row ids for bulk-select checkboxes
            # when bulk_actions enabled. Falls back to empty tuple
            # otherwise.
            row_ids = (
                tuple(str(item.get("id", "") or "") for item in items)
                if bulk_actions_enabled
                else ()
            )
            table = Table(
                columns=column_labels,
                rows=rows,
                row_links=row_links,
                bulk_select=bulk_actions_enabled,
                row_ids=row_ids,
            )
            # Append Pagination when total exceeds the current page slice.
            # Region wrapping uses Stack (matches legacy template's parent
            # `<div>` shape; an extra wrapping div is fine here).
            if total > page_size and endpoint and region_name:
                pagination = Pagination(
                    region_name=region_name,
                    endpoint=URL(endpoint),
                    total=total,
                    page=page,
                    page_size=page_size,
                )
                body = Stack(children=(table, pagination), gap="sm")
            else:
                body = table

        # Prepend the search/filter toolbar (Phase 5) to the body when
        # any toolbar primitive is configured. Empty otherwise — the
        # body remains untouched.
        if toolbar_children:
            body = Stack(children=(*toolbar_children, body), gap="sm")

        # Phase 7: prepend the BulkActionToolbar when bulk_actions is
        # on. Visibility is CSS-driven (`[data-dz-bulk-count]`) so
        # the toolbar only shows when at least one row is selected.
        if bulk_actions_enabled:
            from dazzle.render.fragment import BulkActionToolbar

            body = Stack(children=(BulkActionToolbar(), body), gap="sm")

        # Header carries title + optional CreateButton. The Create
        # button is contractually required for the list page (UX
        # contract `rbac:<Entity>:<persona>:create` looks for an
        # `<a href="*create*" data-dazzle-action="<Entity>.create">`
        # visible on the list). Issue #1029 phase 3: switched from a
        # plain Link to CreateButton — adds the data-dazzle-action
        # attribute the RBAC checker keys off plus the 12x12 `+` icon,
        # matching the legacy `filterable_table.html` shape.
        header: Fragment
        if create_url and entity_name:
            header = Row(
                children=(
                    Heading(title, level=1),
                    CreateButton(
                        href=URL(create_url),
                        entity_name=entity_name,
                    ),
                ),
                align="center",
                gap="md",
            )
        else:
            header = Heading(title, level=1)

        return Surface(
            header=header,
            # Region carries `data-dazzle-table` so the UX contract
            # checker + htmx `closest [data-dazzle-table]` selectors
            # find the entity container.
            body=Region(kind="list", body=body, data_table=entity_name),
        )

    def _build_view(self, surface: SurfaceLike, ctx: dict[str, Any]) -> Surface:
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
                        Text(
                            _format_cell(
                                f.get("value"),
                                str(f.get("kind", "text")),
                                str(f.get("currency_code", "")),
                            )
                        ),
                    ),
                    align="start",
                )
                for f in fields
            )
            detail_body = Stack(children=field_rows, gap="sm")

        # Issue #1030: action toolbar — Edit / Delete / transitions /
        # integration / external-link actions. Each action checks its
        # ctx key and emits the corresponding primitive when present.
        actions = self._build_detail_actions(ctx)
        if actions:
            detail_body = Stack(
                children=(Row(children=actions, align="start"), detail_body),
                gap="md",
            )

        related_groups: list[dict[str, Any]] = ctx.get("related_groups", []) or []
        if not related_groups:
            return Surface(
                header=Heading(title, level=1),
                body=Region(kind="detail", body=detail_body),
            )

        # Wrap detail + related-group regions in an outer Stack
        related_regions: list[Fragment] = []
        for group in related_groups:
            group_title = str(group.get("title") or group.get("name", "Related"))
            group_body = Stack(
                children=(
                    Heading(group_title, level=2),
                    Skeleton(lines=3),
                ),
                gap="sm",
            )
            related_regions.append(Region(kind="related", body=group_body))

        wrapper = Stack(
            children=(Region(kind="detail", body=detail_body), *related_regions),
            gap="md",
        )

        # Outer Region uses kind="detail" since the surface IS a detail
        # surface; the inner sub-regions carry kind="related" for CSS.
        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="detail", body=wrapper),
        )

    def _build_list_toolbar(
        self,
        *,
        search_enabled: bool,
        search_fields: list[str],
        filter_values: dict[str, str],
        columns: list[dict[str, Any]],
        entity_name: str,
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
            toolbar.append(
                SearchBox(
                    name=f"{region_name or entity_name}_search",
                    fts_endpoint=URL(f"/_dazzle/fts/{entity_name}?html=1"),
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

    def _build_detail_actions(self, ctx: dict[str, Any]) -> tuple[Fragment, ...]:
        """Issue #1030: build the per-record action row from ctx.

        Order: Edit Link (primary) → state-machine transitions →
        integration actions → external links → Delete Button (danger,
        confirm-gated). Empty tuple when no actions are configured."""
        actions: list[Fragment] = []
        edit_url = ctx.get("edit_url") or ""
        delete_url = ctx.get("delete_url") or ""
        entity_name = ctx.get("entity_name") or "record"
        transitions = ctx.get("transitions") or []
        integration_actions = ctx.get("integration_actions") or []
        external_links = ctx.get("external_link_actions") or []

        if edit_url:
            actions.append(Link(label="Edit", href=URL(str(edit_url))))

        for t in transitions:
            api_url = t.get("api_url") or ""
            label = t.get("label") or ""
            if not api_url or not label:
                continue
            actions.append(
                Button(
                    label=str(label),
                    variant="secondary",
                    hx_post=URL(str(api_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                )
            )

        for a in integration_actions:
            api_url = a.get("api_url") or ""
            label = a.get("label") or ""
            if not api_url or not label:
                continue
            actions.append(
                Button(
                    label=str(label),
                    variant="secondary",
                    hx_post=URL(str(api_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                )
            )

        for link in external_links:
            label = link.get("label") or ""
            url = link.get("url") or ""
            if not label or not url:
                continue
            # External links use Link primitive (no htmx — full nav).
            actions.append(Link(label=str(label), href=URL(str(url))))

        if delete_url:
            actions.append(
                Button(
                    label="Delete",
                    variant="danger",
                    hx_delete=URL(str(delete_url)),
                    hx_target=TargetSelector("body"),
                    hx_swap="innerHTML",
                    hx_confirm=f"Delete this {str(entity_name).lower()}?",
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
) -> "Field | Combobox | RefPicker | FileUpload":
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
    typed_keys = {
        "collection": ("empty_collection", "No items yet"),
        "filtered": ("empty_filtered", "No matches"),
        "forbidden": ("empty_forbidden", "Not available"),
    }
    typed_key, default_title = typed_keys.get(kind, ("empty_collection", "No items yet"))
    typed_value = str(ctx.get(typed_key, "") or "").strip()
    generic_message = str(ctx.get("empty_message", "") or "").strip()
    description = typed_value or generic_message or "Items will appear here when they are added."
    return default_title, description


def _format_cell(value: Any, kind: str, currency_code: str = "") -> str:
    """Stringify a cell value for the typed Table via the pure formatter (#1470).

    Delegates to ``render.fragment.format_cell``, which renders by column kind +
    Python value type (bool→Yes/No, enum→Title Case, money(minor units)→currency,
    float→2dp, datetime→friendly, FK→name) and HTML-escapes once. Replaces the
    old str()-coerce stub — the "Jinja path" it deferred to was removed in #1042,
    so the typed adapter is now the only path and must format properly.
    """
    return format_cell(value, kind, currency_code=currency_code)
