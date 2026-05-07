"""IR-to-Fragment translator for surface rendering.

Takes a SurfaceSpec + render context (rows, columns, etc. — same shape
as the Jinja path's context dict) and produces a Fragment tree. The
FragmentRenderer then emits HTML from the tree.

Plan 3 ships the minimum-viable adapter for `mode: list` only — enough
to render simple_task's task_list surface. Subsequent plans add detail,
form, and dashboard modes.
"""

from typing import Any

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment import (
    URL,
    Combobox,
    EmptyState,
    Field,
    FormStack,
    Fragment,
    Heading,
    Link,
    RefPicker,
    Region,
    Row,
    Skeleton,
    Stack,
    Submit,
    Surface,
    Table,
    Text,
)


class FragmentSurfaceAdapter:
    """Translate a SurfaceSpec + context into a Fragment tree."""

    def build(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Fragment:
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

    def _build_list(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        title = surface.title or surface.name.replace("_", " ").title()
        items: list[dict[str, Any]] = ctx.get("items", [])
        columns: list[dict[str, Any]] = ctx.get("columns", [])
        entity_name = (getattr(surface, "entity_ref", "") or "").strip()
        create_url = str(ctx.get("create_url", "") or "").strip()

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items yet",
                description="Items will appear here when they are added.",
            )
        else:
            column_labels = tuple(col.get("label", col.get("key", "")) for col in columns)
            rows = tuple(
                tuple(
                    _format_cell(item.get(col["key"]), col.get("type", "text")) for col in columns
                )
                for item in items
            )
            body = Table(columns=column_labels, rows=rows)

        # Header carries title + optional Create link. The Create
        # link is contractually required for the list page (UX
        # contract `rbac:<Entity>:<persona>:create` looks for an
        # <a href="*create*"> visible on the list).
        header: Fragment
        if create_url:
            header = Row(
                children=(
                    Heading(title, level=1),
                    Link(label=f"Create {entity_name or 'item'}", href=URL(create_url)),
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

    def _build_view(self, surface: SurfaceSpec, ctx: dict[str, Any]) -> Surface:
        """Detail surface — single record's fields as a definition-list-shaped Region.

        Plan 8: each field renders as a Row of (Heading-level-4 label,
        Text value). Stack groups them inside Region(kind="detail").
        Plan 10: when ctx carries `related_groups`, additional
        Region(kind="related") entries are appended after the detail
        body — each emits a Heading (group title) + Skeleton placeholder
        (the actual related-entity rows arrive via a separate htmx fetch
        post-Plan-11).
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
                        Text(_format_cell(f.get("value"), str(f.get("kind", "text")))),
                    ),
                    align="start",
                )
                for f in fields
            )
            detail_body = Stack(children=field_rows, gap="sm")

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

    def _build_form(
        self,
        surface: SurfaceSpec,
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
        if not fields_in:
            body = EmptyState(
                title="No fields",
                description="This form has no inputs.",
            )
        else:
            primitives = tuple(_field_to_primitive(f) for f in fields_in)
            method_lit = method if method in ("GET", "POST") else "POST"
            body = FormStack(
                action=URL(action),
                fields=primitives,
                method=method_lit,  # type: ignore[arg-type]
                submit=Submit(label=submit_label),
            )

        return Surface(
            header=Heading(title, level=1),
            body=Region(kind="form", body=body),
        )


def _field_to_primitive(field_dict: dict[str, Any]) -> "Field | Combobox | RefPicker":
    """Map a field-shape dict to the right Fragment form primitive.

    The `kind` carried in field_dict is the *widget* kind — matching
    `FieldContext.type` from `dazzle_ui.runtime.template_context` (text,
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


def _format_cell(value: Any, kind: str) -> str:
    """Stringify a cell value for the typed Table.

    Plan 3 supports the most basic types only — text, str-coerced. Plan 6
    or later adds badge/bool/date/currency/ref support. Until then, we
    str-coerce everything and lose type-specific formatting; this is
    acceptable because the Jinja path remains the default for any surface
    that needs the richer formatting.
    """
    if value is None:
        return ""
    return str(value)
