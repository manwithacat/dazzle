"""Forms-family render mixin.

Houses the 9 form primitives:

  - _emit_form_section
  - _emit_form_stack
  - _emit_field
  - _emit_combobox
  - _emit_file_upload
  - _emit_ref_picker
  - _emit_submit
  - _emit_card_picker
  - _emit_add_card_row

All methods only call `self._emit(child, ctx)` for child recursion;
dispatch goes back through the match block in `_emit.py`.

See issue #1064 for the full decomposition plan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    AddCardRow,
    CardPicker,
    Combobox,
    Field,
    FileUpload,
    FormSection,
    FormStack,
    RefPicker,
    Submit,
)

if TYPE_CHECKING:
    from dazzle.render.fragment.primitives import Fragment


class _RenderFormsMixin:
    """Mixin adding the 9 forms-family `_emit_*` methods to
    `FragmentRenderer`. Same pattern as `_RenderLayoutMixin`.
    """

    if TYPE_CHECKING:

        def _emit(self, fragment: Fragment, ctx: RenderContext) -> str: ...

    def _emit_form_section(self, s: FormSection, ctx: RenderContext) -> str:
        """Render a FormSection inside a FormStack — `<section
        class="dz-form-section">` with a `<h3>` title and an optional
        muted-note paragraph (matches `components/form.html`)."""
        note_html = f'<p class="dz-form-section-note">{ctx.escape(s.note)}</p>' if s.note else ""
        fields_html = "".join(self._emit(f, ctx) for f in s.fields)  # type: ignore[arg-type]
        return (
            f'<section class="dz-form-section">'
            f'<h3 class="dz-form-section-title">{ctx.escape(s.title)}</h3>'
            f"{note_html}"
            f"{fields_html}"
            f"</section>"
        )

    def _emit_form_stack(self, fs: FormStack, ctx: RenderContext) -> str:
        """Render `<form>` with htmx-driven submission per legacy
        `components/form.html` contract — `hx-post` / `hx-put` (by
        `fs.method`), `hx-target="body"`, `hx-swap="innerHTML"`,
        `hx-ext="json-enc"` for JSON payload encoding. The RBAC
        contract checker requires `hx-post` on the form element."""
        action = ctx.escape_attr(str(fs.action))
        fields_html = "".join(self._emit(f, ctx) for f in fs.fields)  # type: ignore[arg-type]
        submit_html = self._emit(fs.submit, ctx) if fs.submit is not None else ""
        if fs.method == "GET":
            method_attrs = f'action="{action}" method="GET"'
        else:
            hx_verb = "hx-put" if fs.method == "PUT" else "hx-post"
            method_attrs = f'{hx_verb}="{action}" hx-target="body" hx-swap="innerHTML"'
        data_parts: list[str] = []
        if fs.entity_name:
            data_parts.append(f'data-dazzle-form="{ctx.escape_attr(fs.entity_name)}"')
        if fs.mode:
            data_parts.append(f'data-dazzle-form-mode="{ctx.escape_attr(fs.mode)}"')
        data_attrs = (" " + " ".join(data_parts)) if data_parts else ""
        return (
            f'<form class="dz-form-stack" {method_attrs}{data_attrs}>'
            f"{fields_html}{submit_html}"
            f"</form>"
        )

    def _emit_field(self, f: Field, ctx: RenderContext) -> str:
        # Field labels are developer-supplied; values may be user-supplied —
        # escape both as a safety net.
        label = ctx.escape(f.label)
        name = ctx.escape_attr(f.name)
        placeholder = ctx.escape_attr(f.placeholder)
        initial = ctx.escape_attr(f.initial_value)
        required_attr = " required" if f.required else ""
        readonly_attr = " readonly" if f.readonly else ""

        if f.kind == "textarea":
            inner = (
                f'<textarea class="dz-field__input" name="{name}" '
                f'placeholder="{placeholder}"{required_attr}{readonly_attr}>'
                f"{ctx.escape(f.initial_value)}</textarea>"
            )
        elif f.kind == "checkbox":
            checked = " checked" if f.initial_value == "true" else ""
            inner = (
                f'<input class="dz-field__input" type="checkbox" name="{name}"'
                f"{checked}{required_attr}{readonly_attr}>"
            )
        else:
            inner = (
                f'<input class="dz-field__input" type="{f.kind}" name="{name}" '
                f'value="{initial}" placeholder="{placeholder}"{required_attr}{readonly_attr}>'
            )
        return (
            f'<label class="dz-field"><span class="dz-field__label">{label}</span>{inner}</label>'
        )

    def _emit_combobox(self, c: Combobox, ctx: RenderContext) -> str:
        options = "".join(
            f'<option value="{ctx.escape_attr(value)}"'
            + (" selected" if value == c.initial_value else "")
            + f">{ctx.escape(label)}</option>"
            for value, label in c.options
        )
        required_attr = " required" if c.required else ""
        label = ctx.escape(c.label)
        name = ctx.escape_attr(c.name)
        return (
            f'<label class="dz-combobox">'
            f'<span class="dz-combobox__label">{label}</span>'
            f'<select class="dz-combobox__select" name="{name}"{required_attr}>{options}</select>'
            f"</label>"
        )

    def _emit_file_upload(self, f: FileUpload, ctx: RenderContext) -> str:
        """Render a FileUpload matching legacy file-widget shape (#1033).

        `<div data-dz-widget="file-upload">` carries a hidden FK input
        (the source of truth for the form post) plus the data-attrs
        the Alpine `dz.fileUpload` controller reads to wire up the
        drop-zone and POST to the multipart upload endpoint."""
        name = ctx.escape_attr(f.name)
        label = ctx.escape(f.label)
        upload_attr = ctx.escape_attr(str(f.upload_url))
        accept_attr = f' data-dz-accept="{ctx.escape_attr(f.accept)}"' if f.accept else ""
        max_attr = f' data-dz-max-size="{f.max_size_bytes}"' if f.max_size_bytes > 0 else ""
        required_attr = " required" if f.required else ""
        value_attr = ctx.escape_attr(f.initial_value)
        initial_label_attr = (
            f' data-dz-initial-label="{ctx.escape_attr(f.initial_label)}"'
            if f.initial_label
            else ""
        )
        return (
            f'<label class="dz-field"><span class="dz-field__label">{label}</span>'
            f'<div data-dz-widget="file-upload" '
            f'data-dz-target="{upload_attr}"'
            f"{accept_attr}{max_attr}{initial_label_attr}>"
            f'<input type="hidden" name="{name}" id="field-{name}" '
            f'data-dazzle-field="{name}" data-dz-file-value '
            f'value="{value_attr}"{required_attr}>'
            f"</div>"
            f"</label>"
        )

    def _emit_ref_picker(self, r: RefPicker, ctx: RenderContext) -> str:
        name = ctx.escape_attr(r.name)
        label = ctx.escape(r.label)
        ref_api = ctx.escape_attr(r.ref_api.value)
        initial_value = ctx.escape_attr(r.initial_value)
        required_attr = " required" if r.required else ""
        if r.initial_value:
            initial_option = (
                f'<option value="{initial_value}" selected>'
                f"{ctx.escape(r.initial_label or r.initial_value)}</option>"
            )
        else:
            initial_option = ""
        return (
            f'<label class="dz-ref-picker">'
            f'<span class="dz-ref-picker__label">{label}</span>'
            f'<select class="dz-ref-picker__select" name="{name}" '
            f'data-ref-api="{ref_api}" '
            f'data-selected-value="{initial_value}" '
            f'x-init="dz.filterRefSelect($el)"{required_attr}>'
            f"{initial_option}"
            f"</select>"
            f"</label>"
        )

    def _emit_submit(self, s: Submit, ctx: RenderContext) -> str:
        cls = f"dz-submit dz-submit--variant-{s.variant}"
        return f'<button type="submit" class="{cls}">{ctx.escape(s.label)}</button>'

    def _emit_card_picker(self, p: CardPicker, ctx: RenderContext) -> str:
        """Render a CardPicker matching legacy `workspace/_card_picker.html`
        byte-for-byte (Phase 4B.5.a).

        Single-quoted `data-card-catalog` attribute carries the
        opaque JSON blob the JS reads on `addCard()` (matches legacy
        #963 — Markup from `tojson` bypasses autoescape, so embedded
        `"` chars would terminate a double-quoted attribute mid-value).

        `@click='addCard("name")'` per entry — also single-quoted for
        the same reason. The legacy template uses Jinja's `tojson` to
        emit the name argument; we replicate that with `json.dumps`."""
        from json import dumps as _json_dumps

        title = '<h4 class="dz-card-picker-title">Add a card</h4>'

        if p.entries:
            entries_html = "".join(
                f"<button @click='addCard({_json_dumps(e.name)})' "
                f'data-test-id="dz-card-picker-entry" '
                f'data-test-region="{ctx.escape_attr(e.name)}" '
                f'class="dz-card-picker-entry">'
                f'<span class="dz-card-picker-display-tag">'
                f"{ctx.escape((e.display or '').lower())}</span>"
                f'<span class="dz-card-picker-title-text">{ctx.escape(e.title)}</span>'
                f'<span class="dz-card-picker-entity">{ctx.escape(e.entity)}</span>'
                f"</button>"
                for e in p.entries
            )
            body = title + entries_html
        else:
            body = title + '<div class="dz-card-picker-empty">No widgets available.</div>'

        # `data-card-catalog` is opaque JSON the adapter has already
        # serialised. Single-quoted to permit embedded `"` chars.
        return f"<div data-card-catalog='{p.catalog_json}' class=\"dz-card-picker\">{body}</div>"

    def _emit_add_card_row(self, r: AddCardRow, ctx: RenderContext) -> str:
        """Render an AddCardRow matching legacy `_content.html` add-card
        section byte-for-byte (Phase 4B.5.b.2.iii).

        `<div class="dz-add-card-row">` with a `+` button toggling
        `showPicker` on the parent `dzDashboardBuilder()` x-data
        (`@click="showPicker = !showPicker"`), then the embedded
        CardPicker — visibility CSS-driven per #982 via
        `[data-show-picker="1"]` on the workspace ancestor."""
        picker_html = self._emit(r.picker, ctx)
        return (
            f'<div class="dz-add-card-row">'
            f'<button @click="showPicker = !showPicker" '
            f'data-test-id="dz-add-card-trigger" '
            f'class="dz-add-card-button">'
            f'<svg width="16" height="16" fill="none" stroke="currentColor" '
            f'viewBox="0 0 24 24">'
            f'<path stroke-linecap="round" stroke-linejoin="round" '
            f'stroke-width="2" d="M12 4v16m8-8H4"/>'
            f"</svg>"
            f"Add Card"
            f"</button>"
            f"{picker_html}"
            f"</div>"
        )
