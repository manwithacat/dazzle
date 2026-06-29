"""Pure form-field rendering — FieldContext → dispatch dict → Fragment.

This is the render-layer home for the form-field mapping (ADR-0049 Phase 3b
delete). It lives below http so BOTH the http form dispatch
(`fragment_adapter._build_form` via `_build_dispatch_ctx`) AND the page-layer
experience-flow form-step renderer can map a `FieldContext` to a typed
substrate primitive — without the page layer importing http (page ↛ http).

- `field_context_to_dict` — FieldContext → the flat dispatch dict (the shape
  `_build_dispatch_ctx`'s form branch used to build inline).
- `field_dict_to_primitive` — dispatch dict → Fragment form primitive (moved
  verbatim from `fragment_adapter._field_to_primitive`).
- `render_field_context` — convenience: FieldContext → HTML, used by the
  experience renderer in place of the deleted `form_renderer.render_form_field`.
"""

from typing import Any

from dazzle.render.fragment import (
    URL,
    ColorField,
    Combobox,
    DatePickerField,
    Field,
    FileUpload,
    FragmentRenderer,
    MoneyField,
    RefPicker,
    RichTextField,
    SearchSelect,
    SliderField,
    TagsField,
    WidgetCombobox,
)


def field_context_to_dict(field: Any, initial_values: dict[str, Any]) -> dict[str, Any]:
    """Map a FieldContext (+ the form's initial_values) to the flat dispatch
    dict `field_dict_to_primitive` consumes. Pure — no I/O, no http deps."""
    fname = getattr(field, "name", "")
    kind = getattr(field, "type", None) or "str"
    raw_value = initial_values.get(fname, "")
    entry: dict[str, Any] = {
        "name": fname,
        "label": getattr(field, "label", "") or fname,
        "kind": str(kind).lower(),
        "required": bool(getattr(field, "required", False)),
        "value": raw_value or "",
        "placeholder": getattr(field, "placeholder", "") or "",
    }
    options = getattr(field, "options", None)
    if options:
        entry["options"] = [
            (str(o.get("value", "")), str(o.get("label", o.get("value", "")))) for o in options
        ]
    help_text = str(getattr(field, "help", "") or "")
    if help_text:
        entry["help"] = help_text
    widget = getattr(field, "widget", None)
    if widget:
        entry["widget"] = str(widget)
    field_default = getattr(field, "default", None)
    if field_default not in (None, ""):
        entry["default"] = str(field_default)
    field_extra_all = getattr(field, "extra", None) or {}
    if field_extra_all and "extra" not in entry:
        entry["extra"] = field_extra_all
    if str(kind).lower() == "money":
        field_extra = getattr(field, "extra", None) or {}
        if field_extra:
            entry["extra"] = field_extra
        minor_initial = str(initial_values.get(f"{fname}_minor", "") or "")
        if minor_initial:
            entry["minor_initial"] = minor_initial
    source = getattr(field, "source", None)
    source_endpoint = str(getattr(source, "endpoint", "") or "") if source else ""
    if source_endpoint:
        entry["source"] = {
            "endpoint": source_endpoint,
            "debounce_ms": int(getattr(source, "debounce_ms", 300) or 300),
            "min_chars": int(getattr(source, "min_chars", 0) or 0),
        }
    ref_api = str(getattr(field, "ref_api", "") or "")
    if ref_api:
        entry["ref_api"] = ref_api
    initial_label_value = str(getattr(field, "initial_label", "") or "")
    if initial_label_value:
        entry["initial_label"] = initial_label_value
    # Issue #1027: ref-typed fields in EDIT mode receive an eagerly-expanded
    # related-record dict; coerce to the FK scalar + lift a display value.
    if ref_api and isinstance(raw_value, dict):
        entry["value"] = str(raw_value.get("id", "") or "")
        if not entry.get("initial_label"):
            for label_key in ("__display__", "name", "title", "label", "email", "code"):
                if raw_value.get(label_key):
                    entry["initial_label"] = str(raw_value[label_key])
                    break
    return entry


def field_dict_to_primitive(
    field_dict: dict[str, Any],
) -> "Field | Combobox | RefPicker | SearchSelect | MoneyField | FileUpload | WidgetCombobox | TagsField | DatePickerField | ColorField | SliderField | RichTextField":
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
    help_text = str(field_dict.get("help", "") or "")
    # CREATE-mode default (#3b review): on create `value` is empty; the DSL
    # `default:` must seed the field. `value or default` honours the persisted
    # value in EDIT and the default in CREATE — matching legacy
    # `render_form_field`'s `values.get(name, field.default)`.
    field_default = str(field_dict.get("default", "") or "")
    initial_value = str(field_dict.get("value", "") or "") or field_default
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

    # MONEY: a first-class `: money` field. The currency config (code/scale/
    # symbol/fixed/options) rides in `extra`, threaded by `_build_dispatch_ctx`;
    # `minor_initial` is the persisted integer minor units. Routed BEFORE the
    # widget_to_field_kind fallback (which would degrade money → plain number).
    if kind == "money":
        extra = field_dict.get("extra") or {}
        raw_opts = extra.get("currency_options") or []
        currency_options = tuple(
            (
                str(o.get("code", "") if isinstance(o, dict) else getattr(o, "code", "")),
                str(o.get("scale", "") if isinstance(o, dict) else getattr(o, "scale", "")),
                str(o.get("symbol", "") if isinstance(o, dict) else getattr(o, "symbol", "")),
            )
            for o in raw_opts
        )
        return MoneyField(
            name=name,
            label=label,
            currency_code=str(extra.get("currency_code", "") or ""),
            scale=str(extra.get("scale", "") or ""),
            symbol=str(extra.get("symbol", "") or ""),
            currency_fixed=bool(extra.get("currency_fixed", True)),
            currency_options=currency_options,
            required=required,
            minor_initial=str(field_dict.get("minor_initial", "") or ""),
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

    # WIDGET overrides (ADR-0049 Phase 3a): a `widget=` clause selects a
    # client-controller widget (combobox/tags/picker/color/slider/rich_text).
    # Routed before the plain enum/select branch — `widget=combobox` is a
    # TomSelect-enhanced select, not the vanilla Combobox. `multi_select` and
    # `range`/date_range are intentionally unported (zero fleet usage).
    widget = str(field_dict.get("widget", "") or "").strip()
    extra = field_dict.get("extra") or {}
    default = str(field_dict.get("default", "") or "")
    widget_initial = initial_value or default
    if widget == "combobox":
        opts = tuple((str(v), str(label_)) for v, label_ in (field_dict.get("options") or []))
        return WidgetCombobox(
            name=name,
            label=label,
            options=opts,
            required=required,
            placeholder=placeholder,
            initial_value=initial_value,
        )
    if widget == "tags":
        return TagsField(
            name=name,
            label=label,
            required=required,
            placeholder=placeholder,
            initial_value=initial_value,
        )
    if widget == "picker":
        return DatePickerField(
            name=name,
            label=label,
            is_datetime=(kind == "datetime"),
            required=required,
            placeholder=placeholder,
            initial_value=widget_initial,
        )
    if widget == "color":
        return ColorField(
            name=name,
            label=label,
            required=required,
            initial_value=widget_initial or "#3b82f6",
        )
    if widget == "slider":
        return SliderField(
            name=name,
            label=label,
            min_val=str(extra.get("min", 0)),
            max_val=str(extra.get("max", 100)),
            step=str(extra.get("step", 1)),
            required=required,
            initial_value=widget_initial or "50",
        )
    if widget == "rich_text":
        return RichTextField(
            name=name,
            label=label,
            required=required,
            initial_value=initial_value,
            toolbar=str(extra.get("rich_text_toolbar", "") or ""),
            max_length=int(extra.get("rich_text_max_length", 0) or 0),
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
            placeholder=placeholder,
            help=help_text,
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
        help=help_text,
    )


_DEFAULT_RENDERER = FragmentRenderer()


def render_field_context(field: Any, initial_values: dict[str, Any]) -> str:
    """FieldContext → rendered HTML for one form field, via the typed substrate.
    The page-layer replacement for `form_renderer.render_form_field` (ADR-0049
    Phase 3b)."""
    primitive = field_dict_to_primitive(field_context_to_dict(field, initial_values))
    return _DEFAULT_RENDERER.render(primitive)
