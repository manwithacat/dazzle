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
    ColorField,
    Combobox,
    DatePickerField,
    Field,
    FileUpload,
    FormSection,
    FormStack,
    MoneyField,
    RefPicker,
    RichTextField,
    SearchSelect,
    SliderField,
    Submit,
    TagsField,
    WidgetCombobox,
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
        `fs.method`), `hx-target="body"`, `hx-swap="innerHTML"`. The
        body is submitted **form-urlencoded** (htmx's default): the
        `json-enc` extension was dropped in the htmx 4 migration, so
        handlers must read fields via `Form()`/`request.form()`, not
        JSON. The RBAC contract checker requires `hx-post` on the form."""
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

    def _emit_search_select(self, s: SearchSelect, ctx: RenderContext) -> str:
        """Render a SearchSelect (`source:` typeahead) reproducing the legacy
        `_render_search_select` DOM contract the fidelity scorer keys off:
        `search-input-{name}` + `search-results-{name}` ids, `hx-indicator`,
        a `delay:` debounce in `hx-trigger`, an empty-state prompt, and
        `aria-invalid` error wiring. Alpine open/close is self-contained
        (`x-data="{ open: false }"`); no external controller."""
        name = ctx.escape_attr(s.name)
        label_text = ctx.escape(s.label)
        placeholder = ctx.escape_attr(s.placeholder or f"Search {s.label}...")
        endpoint = ctx.escape_attr(str(s.endpoint))
        init_id = ctx.escape_attr(s.initial_value)
        init_display = ctx.escape_attr(s.initial_label or s.initial_value)
        required_attr = ' required aria-required="true"' if s.required else ""
        hx_min_chars = f" hx-vals='{{\"min_chars\": {s.min_chars}}}'" if s.min_chars else ""
        return (
            '<div class="dz-search-select" x-data="{ open: false }" '
            'data-dz-widget="search_select">'
            f'<input type="hidden" name="{name}" id="field-{name}" '
            f'data-dazzle-field="{name}" value="{init_id}"{required_attr}>'
            '<input type="text" '
            f'id="search-input-{name}" '
            'class="dz-search-select-input" '
            f'placeholder="{placeholder}" '
            'autocomplete="off" role="combobox" '
            ':aria-expanded="open" '
            f'aria-controls="search-results-{name}" '
            'aria-autocomplete="list" aria-haspopup="listbox" '
            f'value="{init_display}" '
            f'hx-get="{endpoint}" '
            f'hx-trigger="keyup changed delay:{s.debounce_ms}ms" '
            f'hx-target="#search-results-{name}" '
            f'hx-indicator="#search-spinner-{name}" '
            f'hx-params="q"{hx_min_chars} '
            '@focus="open = true" '
            '@blur="setTimeout(() => { open = false }, 200)">'
            f'<span id="search-spinner-{name}" '
            'class="htmx-indicator dz-search-select-spinner" '
            'role="status" aria-label="Searching">'
            '<svg class="dz-search-select-spinner-icon" fill="none" viewBox="0 0 24 24" '
            'aria-hidden="true">'
            '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" '
            'stroke-width="4"></circle>'
            '<path class="opacity-75" fill="currentColor" '
            'd="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>'
            "</svg></span>"
            f'<div id="search-results-{name}" '
            'x-show="open" x-cloak role="listbox" '
            f'aria-label="{label_text} suggestions" '
            'class="dz-search-select-results">'
            '<div class="dz-search-select-prompt" role="option" aria-disabled="true">'
            f"Type at least {s.min_chars} characters to search..."
            "</div></div></div>"
        )

    def _emit_money(self, m: MoneyField, ctx: RenderContext) -> str:
        """Render a MoneyField reproducing the legacy `_render_money` dzMoney
        contract — a major-unit text input + hidden `{name}_minor` carrier,
        in fixed (symbol prefix + hidden currency) or selector mode."""
        name = ctx.escape_attr(m.name)
        label_text = ctx.escape(m.label)
        minor_attr = ctx.escape_attr(m.minor_initial)
        required_attr = ' required aria-required="true"' if m.required else ""

        if m.currency_fixed:
            return (
                '<div x-data="dzMoney" '
                f'data-dz-currency="{ctx.escape_attr(m.currency_code)}" '
                f'data-dz-scale="{ctx.escape_attr(m.scale)}">'
                '<div class="dz-form-money-group">'
                f'<span class="dz-form-money-prefix" aria-hidden="true">'
                f"{ctx.escape(m.symbol)}</span>"
                f'<input type="text" inputmode="decimal" id="field-{name}" '
                f'data-dazzle-field="{name}" '
                'x-model="displayValue" @input="onInput()" @blur="onBlur()" '
                'class="dz-form-input dz-form-input-trailing" '
                'placeholder="0.00" '
                f'aria-label="{label_text} ({ctx.escape(m.currency_code)})"'
                f"{required_attr}>"
                "</div>"
                f'<input type="hidden" name="{name}_minor" x-model="minorValue" '
                f"x-init=\"minorValue = '{minor_attr}'\">"
                f'<input type="hidden" name="{name}_currency" '
                f'value="{ctx.escape_attr(m.currency_code)}">'
                "</div>"
            )
        currency_opts = "".join(
            f'<option value="{ctx.escape_attr(code)}" '
            f'data-scale="{ctx.escape_attr(opt_scale)}" '
            f'data-symbol="{ctx.escape_attr(opt_symbol)}"'
            + (" selected" if code == m.currency_code else "")
            + f">{ctx.escape(opt_symbol)} {ctx.escape(code)}</option>"
            for code, opt_scale, opt_symbol in m.currency_options
        )
        return (
            f'<div x-data="dzMoney" data-dz-scale="{ctx.escape_attr(m.scale)}">'
            '<div class="dz-form-money-group">'
            f'<select name="{name}_currency" '
            '@change="onCurrencyChange($event)" '
            'class="dz-form-money-select" '
            f'aria-label="Currency for {label_text}">'
            f"{currency_opts}"
            "</select>"
            f'<input type="text" inputmode="decimal" id="field-{name}" '
            f'data-dazzle-field="{name}" '
            'x-model="displayValue" @input="onInput()" @blur="onBlur()" '
            'class="dz-form-input dz-form-input-trailing" '
            'placeholder="0.00" '
            f'aria-label="{label_text}"'
            f"{required_attr}>"
            "</div>"
            f'<input type="hidden" name="{name}_minor" x-model="minorValue" '
            f"x-init=\"minorValue = '{minor_attr}'\">"
            "</div>"
        )

    @staticmethod
    def _widget_label(label_html: str, name: str, inner: str) -> str:
        """Common substrate field wrapper for `widget=`-driven primitives —
        the label + the widget element the client controller mounts on."""
        return (
            f'<label class="dz-field" for="field-{name}">'
            f'<span class="dz-field__label">{label_html}</span>{inner}</label>'
        )

    def _emit_widget_combobox(self, c: WidgetCombobox, ctx: RenderContext) -> str:
        name = ctx.escape_attr(c.name)
        placeholder_html = ctx.escape(c.placeholder or "Select...")
        placeholder_attr = (
            f' placeholder="{ctx.escape_attr(c.placeholder)}"' if c.placeholder else ""
        )
        required_attr = ' required aria-required="true"' if c.required else ""
        opts = [f'<option value="">{placeholder_html}</option>']
        for value, label in c.options:
            sel = " selected" if value == c.initial_value else ""
            opts.append(
                f'<option value="{ctx.escape_attr(value)}"{sel}>{ctx.escape(label)}</option>'
            )
        inner = (
            f'<select id="field-{name}" name="{name}" '
            "data-dz-widget=\"combobox\" data-dz-options='{}' "
            f'class="dz-form-input"{placeholder_attr}{required_attr}>'
            f"{''.join(opts)}</select>"
        )
        return self._widget_label(ctx.escape(c.label), name, inner)

    def _emit_tags_field(self, t: TagsField, ctx: RenderContext) -> str:
        name = ctx.escape_attr(t.name)
        placeholder_attr = (
            f' placeholder="{ctx.escape_attr(t.placeholder)}"' if t.placeholder else ""
        )
        required_attr = ' required aria-required="true"' if t.required else ""
        inner = (
            f'<input id="field-{name}" name="{name}" type="text" '
            'data-dz-widget="tags" '
            'data-dz-options=\'{"create":true,"plugins":["remove_button"]}\' '
            f'class="dz-form-input" value="{ctx.escape_attr(t.initial_value)}"'
            f"{placeholder_attr}{required_attr}>"
        )
        return self._widget_label(ctx.escape(t.label), name, inner)

    def _emit_date_picker(self, d: DatePickerField, ctx: RenderContext) -> str:
        name = ctx.escape_attr(d.name)
        date_format = "Y-m-d H:i" if d.is_datetime else "Y-m-d"
        enable_time = ',"enableTime":true' if d.is_datetime else ""
        placeholder_attr = (
            f' placeholder="{ctx.escape_attr(d.placeholder)}"' if d.placeholder else ""
        )
        required_attr = ' required aria-required="true"' if d.required else ""
        inner = (
            f'<input id="field-{name}" name="{name}" type="text" '
            'data-dz-widget="datepicker" '
            f'data-dz-options=\'{{"dateFormat":"{date_format}"{enable_time}}}\' '
            f'class="dz-form-input" value="{ctx.escape_attr(d.initial_value)}"'
            f"{placeholder_attr}{required_attr}>"
        )
        return self._widget_label(ctx.escape(d.label), name, inner)

    def _emit_color_field(self, c: ColorField, ctx: RenderContext) -> str:
        name = ctx.escape_attr(c.name)
        init_attr = ctx.escape_attr(c.initial_value)
        required_attr = ' required aria-required="true"' if c.required else ""
        inner = (
            f'<div class="dz-form-color-group" x-data="{{ value: \'{init_attr}\' }}">'
            f'<input type="color" id="field-{name}" name="{name}" '
            f'class="dz-form-color-input" x-model="value"{required_attr}>'
            '<span class="dz-form-color-hex" aria-hidden="true" '
            f'x-text="value">{ctx.escape(c.initial_value)}</span>'
            "</div>"
        )
        return self._widget_label(ctx.escape(c.label), name, inner)

    def _emit_slider_field(self, s: SliderField, ctx: RenderContext) -> str:
        name = ctx.escape_attr(s.name)
        required_attr = ' required aria-required="true"' if s.required else ""
        inner = (
            '<div data-dz-widget="range-tooltip" class="dz-form-slider-group">'
            f'<input id="field-{name}" name="{name}" type="range" '
            'data-dz-slider class="dz-form-slider" '
            f'min="{ctx.escape_attr(s.min_val)}" '
            f'max="{ctx.escape_attr(s.max_val)}" '
            f'step="{ctx.escape_attr(s.step)}" '
            f'value="{ctx.escape_attr(s.initial_value)}"{required_attr}>'
            '<span data-dz-range-value class="dz-form-slider-value" '
            f'aria-hidden="true">{ctx.escape(s.initial_value)}</span>'
            "</div>"
        )
        return self._widget_label(ctx.escape(s.label), name, inner)

    def _emit_rich_text(self, r: RichTextField, ctx: RenderContext) -> str:
        import json

        name = ctx.escape_attr(r.name)
        required_attr = ' required aria-required="true"' if r.required else ""
        rt_opts: dict[str, object] = {}
        if r.toolbar:
            rt_opts["toolbar"] = r.toolbar
        if r.max_length:
            rt_opts["maxLength"] = r.max_length
        rt_opts_json = ctx.escape_attr(json.dumps(rt_opts))
        inner = (
            '<div data-dz-widget="richtext" '
            f"data-dz-options='{rt_opts_json}' "
            'class="dz-form-richtext">'
            f'<input type="hidden" id="field-{name}" name="{name}" '
            f'value="{ctx.escape_attr(r.initial_value)}"{required_attr}>'
            "<div data-dz-editor></div>"
            "</div>"
        )
        return self._widget_label(ctx.escape(r.label), name, inner)

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
