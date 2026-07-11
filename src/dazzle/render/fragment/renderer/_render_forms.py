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

import json
from typing import TYPE_CHECKING

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.primitives import (
    AddCardRow,
    CardPicker,
    ColorField,
    Combobox,
    Field,
    FileUpload,
    FormSection,
    FormStack,
    FormStepper,
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
        fields_html = "".join(self._emit(f, ctx) for f in fs.fields)  # type: ignore[arg-type]
        submit_html = self._emit(fs.submit, ctx) if fs.submit is not None else ""
        peek_attrs = ""
        if fs.method == "GET":
            action = ctx.escape_attr(str(fs.action))
            method_attrs = f'action="{action}" method="GET"'
        elif fs.peek_target:
            # #1494 (2c, Slice 2): inline save-and-stay inside a peek panel.
            # The submit posts `?peek=1` (→ API suppresses HX-Redirect),
            # discards the JSON body (`hx-swap="none"`), and on success
            # re-fetches the read-only view back into the panel cell — a
            # native htmx after-request hook, no page reload, no JS module.
            raw_action = str(fs.action)
            sep = "&" if "?" in raw_action else "?"
            action = ctx.escape_attr(f"{raw_action}{sep}peek=1")
            hx_verb = "hx-put" if fs.method == "PUT" else "hx-post"
            target = ctx.escape_attr(fs.peek_target)
            # The re-fetch lives in an `hx-on` inline JS string, so the
            # URL/selector cross TWO contexts: a JS string literal nested in a
            # double-quoted HTML attribute. `json.dumps` safely encodes the
            # JS-string layer (quotes/backslashes), then `escape_attr` encodes
            # the outer HTML-attribute layer — defense-in-depth that holds even
            # if a future caller routes a slug/display-name into these values,
            # not just the server-derived uuid/path they carry today.
            view_url_js = ctx.escape_attr(json.dumps(fs.peek_view_url))
            target_js = ctx.escape_attr(json.dumps(fs.peek_target))
            refetch = (
                "if(event.detail.successful){"
                f"htmx.ajax('GET',{view_url_js},"
                f"{{target:{target_js},swap:'innerHTML'}})}}"
            )
            method_attrs = (
                f'{hx_verb}="{action}" hx-target="{target}" hx-swap="none" '
                f'hx-on:htmx:after:request="{refetch}"'
            )
            peek_attrs = ' data-dz-peek-save="1"'
        else:
            action = ctx.escape_attr(str(fs.action))
            hx_verb = "hx-put" if fs.method == "PUT" else "hx-post"
            method_attrs = f'{hx_verb}="{action}" hx-target="body" hx-swap="innerHTML"'
        data_parts: list[str] = []
        if fs.entity_name:
            data_parts.append(f'data-dazzle-form="{ctx.escape_attr(fs.entity_name)}"')
        if fs.mode:
            data_parts.append(f'data-dazzle-form-mode="{ctx.escape_attr(fs.mode)}"')
        data_attrs = (" " + " ".join(data_parts)) if data_parts else ""
        return (
            f'<form class="dz-form-stack" {method_attrs}{data_attrs}{peek_attrs}>'
            f"{fields_html}{submit_html}"
            f"</form>"
        )

    @staticmethod
    def _form_required_indicator(required: bool) -> str:
        """The `*` + visually-hidden `(required)` marker (legacy
        `_required_indicator`), rendered only for required fields."""
        return (
            (
                '<span class="dz-form-required" aria-hidden="true">*</span>'
                '<span class="visually-hidden">(required)</span>'
            )
            if required
            else ""
        )

    def _form_label_block(self, ctx: RenderContext, name: str, label: str, required: bool) -> str:
        """`<label for="field-{name}" class="dz-form-label">` + required marker
        (legacy `_label_block`)."""
        return (
            f'<label for="field-{ctx.escape_attr(name)}" class="dz-form-label">'
            f"{ctx.escape(label)}{self._form_required_indicator(required)}</label>"
        )

    def _form_hint(self, ctx: RenderContext, name: str, help_text: str) -> str:
        """Optional `<p class="dz-form-hint">` help paragraph (legacy
        `_hint_paragraph`)."""
        if not help_text:
            return ""
        return (
            f'<p id="hint-{ctx.escape_attr(name)}" class="dz-form-hint">{ctx.escape(help_text)}</p>'
        )

    @staticmethod
    def _form_field_a11y(name_attr: str, required: bool, help_text: str) -> str:
        """Inline ` required aria-required` + ` aria-describedby="hint-{name}"`
        on the input (legacy `_required_attrs` + `_describedby_attr`)."""
        req = ' required aria-required="true"' if required else ""
        describedby = f' aria-describedby="hint-{name_attr}"' if help_text else ""
        return req + describedby

    def _emit_field(self, f: Field, ctx: RenderContext) -> str:
        """Render a plain form field at parity with the legacy
        `render_form_field` standard-field contract: a `<div class="dz-form-field">`
        wrapping a `<label for>` (+ required marker), an optional help paragraph,
        and the input — which carries `id`/`data-dazzle-field` (QA-harness +
        a11y selectors), `dz-form-input`, and `aria-required`/`aria-describedby`."""
        name = ctx.escape_attr(f.name)
        a11y = self._form_field_a11y(name, f.required, f.help)
        readonly_attr = " readonly" if f.readonly else ""
        # ADR-0050 Phase 5b: usage-driven autofocus (default False = no attr).
        autofocus_attr = " autofocus" if f.autofocus else ""

        if f.kind == "checkbox":
            # Checkbox keeps its own label structure (input nested in the label);
            # the hint sits after, both inside the dz-form-field wrapper.
            checked = " checked" if f.initial_value == "true" else ""
            return (
                '<div class="dz-form-field">'
                '<label class="dz-form-checkbox-label">'
                f'<input type="checkbox" name="{name}" id="field-{name}" '
                f'data-dazzle-field="{name}" class="dz-form-checkbox"'
                f"{a11y}{checked}{readonly_attr}{autofocus_attr}>"
                f"<span>{ctx.escape(f.label)}</span></label>"
                f"{self._form_hint(ctx, f.name, f.help)}"
                "</div>"
            )

        if f.kind == "textarea":
            inner = (
                f'<textarea id="field-{name}" name="{name}" data-dazzle-field="{name}" '
                f'class="dz-form-input dz-form-textarea" '
                f'placeholder="{ctx.escape_attr(f.placeholder)}"'
                f'{a11y}{readonly_attr}{autofocus_attr} rows="4">{ctx.escape(f.initial_value)}</textarea>'
            )
        else:
            # Native date/datetime inputs suppress the placeholder (legacy parity).
            placeholder = (
                ""
                if f.kind in ("date", "datetime-local")
                else f' placeholder="{ctx.escape_attr(f.placeholder)}"'
            )
            inner = (
                f'<input id="field-{name}" type="{f.kind}" name="{name}" '
                f'data-dazzle-field="{name}" class="dz-form-input" '
                f'value="{ctx.escape_attr(f.initial_value)}"'
                f"{placeholder}{a11y}{readonly_attr}{autofocus_attr}>"
            )
        return (
            '<div class="dz-form-field">'
            f"{self._form_label_block(ctx, f.name, f.label, f.required)}"
            f"{self._form_hint(ctx, f.name, f.help)}"
            f"{inner}</div>"
        )

    def _emit_combobox(self, c: Combobox, ctx: RenderContext) -> str:
        """Render a plain enum `<select>` at parity with the legacy
        `_render_select` — a leading disabled placeholder option so a *required*
        select starts unselected (without it the first real option auto-selects
        and `required` is a no-op → silent wrong-default writes)."""
        name = ctx.escape_attr(c.name)
        a11y = self._form_field_a11y(name, c.required, c.help)
        placeholder_text = c.placeholder or f"Select {c.label}"
        opts = [
            f'<option value="" disabled{" selected" if not c.initial_value else ""}>'
            f"{ctx.escape(placeholder_text)}</option>"
        ]
        for value, label in c.options:
            sel = " selected" if value == c.initial_value else ""
            opts.append(
                f'<option value="{ctx.escape_attr(value)}"{sel}>{ctx.escape(label)}</option>'
            )
        autofocus_attr = " autofocus" if c.autofocus else ""
        inner = (
            f'<select id="field-{name}" name="{name}" data-dazzle-field="{name}" '
            f'class="dz-form-input"{a11y}{autofocus_attr}>{"".join(opts)}</select>'
        )
        return (
            '<div class="dz-form-field">'
            f"{self._form_label_block(ctx, c.name, c.label, c.required)}"
            f"{self._form_hint(ctx, c.name, c.help)}"
            f"{inner}</div>"
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
            # auto-mounted by dz-utils.js off data-ref-api (was x-init)
            f"{required_attr}>"
            f"{initial_option}"
            f"</select>"
            f"</label>"
        )

    def _emit_search_select(self, s: SearchSelect, ctx: RenderContext) -> str:
        """Render a SearchSelect (`source:` typeahead) reproducing the legacy
        `_render_search_select` DOM contract the fidelity scorer keys off:
        `search-input-{name}` + `search-results-{name}` ids, `hx-indicator`,
        a `delay:` debounce in `hx-trigger`, an empty-state prompt, and
        `aria-invalid` error wiring. Open/close is state-in-DOM (Tier
        F4b): the input SSRs `aria-expanded="false"`, the delegated HM
        `dz-search-select.js` flips it on focusin/focusout (with the
        200ms blur grace so a result-row click lands first), and CSS
        hides the results panel off the attribute. Replaces the Alpine
        `{ open }` island."""
        name = ctx.escape_attr(s.name)
        label_text = ctx.escape(s.label)
        placeholder = ctx.escape_attr(s.placeholder or f"Search {s.label}...")
        # #1547: the endpoint is per-SOURCE; the emitter is the only
        # place field name and endpoint meet. URL params survive
        # hx-params="q", so the search endpoint can key its result rows
        # + select links to the WIDGET's field-name ids.
        from urllib.parse import quote_plus as _qp

        sep = "&" if "?" in str(s.endpoint) else "?"
        endpoint = ctx.escape_attr(f"{s.endpoint}{sep}field_name={_qp(str(s.name))}")
        init_id = ctx.escape_attr(s.initial_value)
        init_display = ctx.escape_attr(s.initial_label or s.initial_value)
        required_attr = ' required aria-required="true"' if s.required else ""
        hx_min_chars = f" hx-vals='{{\"min_chars\": {s.min_chars}}}'" if s.min_chars else ""
        return (
            '<div class="dz-search-select" '
            'data-dz-widget="search_select">'
            f'<input type="hidden" name="{name}" id="field-{name}" '
            f'data-dazzle-field="{name}" value="{init_id}"{required_attr}>'
            '<input type="text" '
            f'id="search-input-{name}" '
            'class="dz-search-select-input" '
            f'placeholder="{placeholder}" '
            'autocomplete="off" role="combobox" '
            'aria-expanded="false" '
            f'aria-controls="search-results-{name}" '
            'aria-autocomplete="list" aria-haspopup="listbox" '
            f'value="{init_display}" '
            f'hx-get="{endpoint}" '
            f'hx-trigger="keyup changed delay:{s.debounce_ms}ms" '
            f'hx-target="#search-results-{name}" '
            f'hx-indicator="#search-spinner-{name}" '
            f'hx-params="q"{hx_min_chars}>'
            f'<span id="search-spinner-{name}" '
            'class="htmx-indicator dz-search-select-spinner" '
            'role="status" aria-label="Searching">'
            '<svg class="dz-search-select-spinner-icon" fill="none" viewBox="0 0 24 24" '
            'aria-hidden="true">'
            '<circle class="dz-spinner-track" cx="12" cy="12" r="10" stroke="currentColor" '
            'stroke-width="4"></circle>'
            '<path class="dz-spinner-head" fill="currentColor" '
            'd="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>'
            "</svg></span>"
            f'<div id="search-results-{name}" '
            'role="listbox" '
            f'aria-label="{label_text} suggestions" '
            'class="dz-search-select-results">'
            '<div class="dz-search-select-prompt" role="option" aria-disabled="true">'
            f"Type at least {s.min_chars} characters to search..."
            "</div></div></div>"
        )

    def _emit_money(self, m: MoneyField, ctx: RenderContext) -> str:
        """Render a MoneyField — a major-unit text input + hidden
        `{name}_minor` carrier, in fixed (symbol prefix + hidden currency)
        or selector mode. State-in-DOM (Tier F4c): the delegated HM
        `dz-money.js` keys off the root `data-dz-money` marker, reads the
        scale from `data-dz-scale`, and keeps the hidden minor carrier in
        sync on input/blur/currency-change. The edit-mode display value is
        SERVER-computed from the minor carrier (no client init pass).
        Replaces the Alpine `dzMoney` island."""
        name = ctx.escape_attr(m.name)
        label_text = ctx.escape(m.label)
        minor_attr = ctx.escape_attr(m.minor_initial)
        required_attr = ' required aria-required="true"' if m.required else ""
        # Edit mode: precompute the major-unit display from the minor
        # carrier server-side ("1500" @ scale 2 -> "15.00").
        display = ""
        if m.minor_initial:
            try:
                display = f"{int(m.minor_initial) / (10 ** int(m.scale)):.{int(m.scale)}f}"
            except (ValueError, TypeError):
                display = ""
        display_attr = ctx.escape_attr(display)

        if m.currency_fixed:
            return (
                '<div class="dz-money" data-dz-money '
                f'data-dz-currency="{ctx.escape_attr(m.currency_code)}" '
                f'data-dz-scale="{ctx.escape_attr(m.scale)}">'
                '<div class="dz-form-money-group">'
                f'<span class="dz-form-money-prefix" aria-hidden="true">'
                f"{ctx.escape(m.symbol)}</span>"
                f'<input type="text" inputmode="decimal" id="field-{name}" '
                f'data-dazzle-field="{name}" '
                f'value="{display_attr}" '
                'class="dz-form-input dz-form-input-trailing" '
                'placeholder="0.00" '
                f'aria-label="{label_text} ({ctx.escape(m.currency_code)})"'
                f"{required_attr}>"
                "</div>"
                f'<input type="hidden" name="{name}_minor" value="{minor_attr}">'
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
            '<div class="dz-money" data-dz-money '
            f'data-dz-currency="{ctx.escape_attr(m.currency_code)}" '
            f'data-dz-scale="{ctx.escape_attr(m.scale)}">'
            '<div class="dz-form-money-group">'
            f'<select name="{name}_currency" '
            'class="dz-form-money-select" '
            f'aria-label="Currency for {label_text}">'
            f"{currency_opts}"
            "</select>"
            f'<input type="text" inputmode="decimal" id="field-{name}" '
            f'data-dazzle-field="{name}" '
            f'value="{display_attr}" '
            'class="dz-form-input dz-form-input-trailing" '
            'placeholder="0.00" '
            f'aria-label="{label_text}"'
            f"{required_attr}>"
            "</div>"
            f'<input type="hidden" name="{name}_minor" value="{minor_attr}">'
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
        # HM-native searchable single-select (HMC-018 slice 1): emit a real
        # native <select data-dz-combobox> carrying the placeholder + all enum
        # options. With JS off it is a fully usable select (submits, native
        # required); controllers/dz-combobox.js progressively enhances it into
        # a searchable role=combobox overlay on first interaction. No
        # data-dz-widget hook — that was the retired TomSelect mount.
        name = ctx.escape_attr(c.name)
        placeholder_html = ctx.escape(c.placeholder or "Select...")
        required_attr = ' required aria-required="true"' if c.required else ""
        opts = [f'<option value="">{placeholder_html}</option>']
        for value, label in c.options:
            sel = " selected" if value == c.initial_value else ""
            opts.append(
                f'<option value="{ctx.escape_attr(value)}"{sel}>{ctx.escape(label)}</option>'
            )
        inner = (
            f'<select id="field-{name}" name="{name}" data-dazzle-field="{name}" '
            f'data-dz-combobox class="dz-form-input"{required_attr}>'
            f"{''.join(opts)}</select>"
        )
        return self._widget_label(ctx.escape(c.label), name, inner)

    def _emit_tags_field(self, t: TagsField, ctx: RenderContext) -> str:
        # HM-native multi-value chips (HMC-018 slice 2): emit a plain native
        # <input type="text" data-dz-tags> carrying a COMMA-JOINED value. With
        # JS off it is a usable comma-separated text field (the server splits
        # on comma); controllers/dz-tags.js progressively enhances it into a
        # chips UI on first interaction, keeping the native input as the
        # submitted value. No data-dz-widget hook — that was the retired
        # TomSelect mount.
        name = ctx.escape_attr(t.name)
        placeholder_attr = (
            f' placeholder="{ctx.escape_attr(t.placeholder)}"' if t.placeholder else ""
        )
        required_attr = ' required aria-required="true"' if t.required else ""
        inner = (
            f'<input id="field-{name}" name="{name}" type="text" '
            f'data-dazzle-field="{name}" data-dz-tags '
            f'class="dz-form-input" value="{ctx.escape_attr(t.initial_value)}"'
            f"{placeholder_attr}{required_attr}>"
        )
        return self._widget_label(ctx.escape(t.label), name, inner)

    def _emit_color_field(self, c: ColorField, ctx: RenderContext) -> str:
        name = ctx.escape_attr(c.name)
        init_attr = ctx.escape_attr(c.initial_value)
        required_attr = ' required aria-required="true"' if c.required else ""
        # State-in-DOM (Tier F4e): the hex readout SSRs the initial value
        # and dz-color.js mirrors future input — the x-data island retired
        # with the Alpine runtime.
        inner = (
            f'<div class="dz-form-color-group">'
            f'<input type="color" id="field-{name}" name="{name}" '
            f'class="dz-form-color-input" value="{init_attr}"{required_attr}>'
            '<span class="dz-form-color-hex" aria-hidden="true">'
            f"{ctx.escape(c.initial_value)}</span>"
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

    def _emit_form_stepper(self, fs: FormStepper, ctx: RenderContext) -> str:
        """Render the wizard stage-tabs (Tier F4d: the HM dz-wizard.js
        state-in-DOM contract). Each `<li>` carries `data-dz-step-to`
        (the delegated controller's navigation anchor) and
        `data-dz-state="current|pending|complete"`; the completed
        checkmark is CSS keyed off the state attribute; the
        visually-hidden span mirrors the state for screen readers. SSR:
        first item current, the rest pending. Replaces the Alpine
        dzWizard bindings — which were production-dead (nothing ever
        mounted `x-data="dzWizard"` after the Jinja teardown)."""
        n = len(fs.sections)
        items: list[str] = []
        for idx, title in enumerate(fs.sections):
            title_html = ctx.escape(title)
            is_last = idx == n - 1
            not_last_cls = "" if is_last else " is-not-last"
            state = "current" if idx == 0 else "pending"
            active_cls = " is-active" if idx == 0 else ""
            current_attr = ' aria-current="step"' if idx == 0 else ""
            connector = (
                ""
                if is_last
                else ('<span class="dz-form-stepper-connector" aria-hidden="true"></span>')
            )
            # A real <button> so keyboard users can operate the wizard —
            # the li itself is not focusable (F4d review catch: the
            # wizard's first LIVE release must not be mouse-only).
            items.append(
                f'<li class="dz-form-stepper-item{not_last_cls}" '
                f'data-dz-state="{state}"{current_attr}>'
                f'<button type="button" class="dz-form-stepper-button" '
                f'data-dz-step-to="{idx}">'
                f'<span class="dz-form-stepper-circle{active_cls}">'
                f"<span>{idx + 1}</span>"
                "</span>"
                f'<span class="dz-form-stepper-label{active_cls}">{title_html}</span>'
                f'<span class="visually-hidden" data-dz-step-status>{state}</span>'
                "</button>"
                f"{connector}"
                "</li>"
            )
        return (
            '<ol class="dz-form-stepper" role="list" aria-label="Form progress">'
            f"{''.join(items)}</ol>"
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
        title = '<h4 class="dz-card-picker-title">Add a card</h4>'

        if p.entries:
            entries_html = "".join(
                f'<button data-dz-add-region="{ctx.escape_attr(e.name)}" '
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
        `showPicker` on the workspace's dashboard-builder controller
        (`data-dz-action="toggle-picker"`, root delegation), then the embedded
        CardPicker — visibility CSS-driven per #982 via
        `[data-show-picker="1"]` on the workspace ancestor."""
        picker_html = self._emit(r.picker, ctx)
        return (
            f'<div class="dz-add-card-row">'
            f'<button data-dz-action="toggle-picker" '
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
