"""Form primitives — FormStack (the form container), Field (single input),
Combobox (typeahead select), Submit (form action button).

InlineEdit lives in `interactive.py` because it's not part of a form-wide
submit cycle — it's a one-field htmx-swap.
"""

from dataclasses import dataclass
from typing import Literal

from dazzle.render.fragment.htmx import URL

_FIELD_KINDS = (
    "text",
    "email",
    "password",
    "number",
    "date",
    "datetime-local",
    "time",
    "textarea",
    "checkbox",
    "radio",
    "url",
    "tel",
)
_METHODS = ("GET", "POST", "PUT")


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    label: str
    kind: Literal[
        "text",
        "email",
        "password",
        "number",
        "date",
        "datetime-local",
        "time",
        "textarea",
        "checkbox",
        "radio",
        "url",
        "tel",
    ] = "text"
    required: bool = False
    placeholder: str = ""
    initial_value: str = ""
    readonly: bool = False
    help: str = ""
    # ADR-0050 Phase 5b (#1517 1a): usage-driven — the entity's most-engaged
    # plain field opens focused. Default False = byte-identical output.
    autofocus: bool = False

    def __post_init__(self) -> None:
        if self.kind not in _FIELD_KINDS:
            raise ValueError(f"invalid field kind {self.kind!r}")


@dataclass(frozen=True, slots=True)
class Combobox:
    name: str
    label: str
    options: tuple[tuple[str, str], ...]
    required: bool = False
    initial_value: str = ""
    placeholder: str = ""
    help: str = ""
    # ADR-0050 Phase 5b (#1517 1a): see Field.autofocus.
    autofocus: bool = False

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("Combobox requires at least one option")


@dataclass(frozen=True, slots=True)
class SearchSelect:
    """Typeahead reference picker for a `source:` field (search_select).

    Distinct from RefPicker: where RefPicker loads the full option list
    client-side from a `ref_api` and renders a `<select>`, SearchSelect
    is a debounced remote-search combobox — a visible text input drives
    `hx-get` typeahead requests against `endpoint`, results swap into a
    listbox, and a hidden `<input name="{name}">` holds the selected id.
    Used for large/external option sets (companies-house, user search).

    Emits the exact DOM contract the fidelity scorer's interaction check
    keys off (`search-input-{name}`, `search-results-{name}`,
    `hx-indicator`, `delay:` debounce, an empty-state prompt, and
    `aria-invalid` error wiring). The Alpine open/close + htmx wiring is
    driven by the delegated HM `dz-search-select.js` controller (state-in-DOM: `data-dz-open` on the widget root).

    `initial_value` is the persisted FK id; `initial_label` the display
    text shown in the visible input on EDIT (matches the legacy
    `_render_search_select` value-resolution)."""

    name: str
    label: str
    endpoint: URL
    required: bool = False
    placeholder: str = ""
    debounce_ms: int = 300
    min_chars: int = 0
    initial_value: str = ""
    initial_label: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SearchSelect requires a non-empty name")
        if not self.label:
            raise ValueError("SearchSelect requires a non-empty label")
        if self.debounce_ms < 0:
            raise ValueError("debounce_ms must be >= 0")
        if self.min_chars < 0:
            raise ValueError("min_chars must be >= 0")


@dataclass(frozen=True, slots=True)
class RefPicker:
    """Reference-field picker — selectable list of related entity rows.

    Distinct from Combobox: where Combobox carries a static option tuple
    (sufficient for enum), RefPicker carries a `ref_api` URL pointing
    at the related entity's list endpoint. Options are populated
    client-side at render time by the existing `dz.filterRefSelect`
    machinery in `dz-alpine.js`.

    `initial_label` lets EDIT forms display the currently-selected
    record's display field without an extra round-trip on render —
    the form-ctx builder fills it from the persisted row.
    """

    name: str
    label: str
    ref_api: URL
    required: bool = False
    initial_value: str = ""
    initial_label: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RefPicker requires a non-empty name")
        if not self.label:
            raise ValueError("RefPicker requires a non-empty label")


@dataclass(frozen=True, slots=True)
class FileUpload:
    """File-upload widget for `field type: file` (issue #1033).

    Renders as a `<div data-dz-widget="file-upload">` carrying a
    hidden `<input>` that holds the FK to a stored Document (or any
    file-resource entity) once upload completes. The drop-zone UI
    + multipart POST to `upload_url` is wired by Alpine
    (`dz.fileUpload` in `dz-alpine.js`); this primitive emits the
    DOM contract the legacy Jinja path already produces.

    `initial_value` carries the persisted file URL/key in EDIT mode
    so the widget can show the existing filename. `initial_label` is
    the human-readable display text (typically the original
    filename); when present, displays alongside the drop-zone."""

    name: str
    label: str
    upload_url: URL
    required: bool = False
    accept: str = ""  # comma-separated MIME types or extensions
    max_size_bytes: int = 0  # 0 = no client-side limit
    initial_value: str = ""
    initial_label: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("FileUpload requires a non-empty name")
        if not self.label:
            raise ValueError("FileUpload requires a non-empty label")
        if self.max_size_bytes < 0:
            raise ValueError("max_size_bytes must be >= 0")


@dataclass(frozen=True, slots=True)
class MoneyField:
    """Money input for a first-class `: money` field — at parity with the
    legacy `_render_money` widget.

    Renders the HM `data-dz-money` controller contract: a major-unit text
    input (`inputmode="decimal"`, `x-model="displayValue"`) backed by a
    hidden `{name}_minor` input (the integer minor units the controller
    keeps in sync) plus a `{name}_currency` carrier. Two modes:

    - **fixed** (`currency_fixed=True`): a static symbol prefix +
      `data-dz-currency`/`data-dz-scale` on the controller + a hidden
      `{name}_currency`.
    - **selector** (`currency_fixed=False`): a `<select name="{name}_currency">`
      of `currency_options` (each `(code, scale, symbol)`) driving
      `onCurrencyChange`.

    The delegated `dz-money.js` controller ships in the HM dist; this primitive
    only emits the mount attributes it reads."""

    name: str
    label: str
    currency_code: str = ""
    scale: str = ""
    symbol: str = ""
    currency_fixed: bool = True
    currency_options: tuple[tuple[str, str, str], ...] = ()
    required: bool = False
    minor_initial: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("MoneyField requires a non-empty name")
        if not self.label:
            raise ValueError("MoneyField requires a non-empty label")


@dataclass(frozen=True, slots=True)
class WidgetCombobox:
    """TomSelect enum picker (`widget=combobox`) — at parity with the legacy
    `_render_combobox`. Distinct from the plain `Combobox` (a vanilla
    `<select>`): this emits `data-dz-widget="combobox"` so the client TomSelect
    controller mounts. A leading empty/placeholder option is always rendered."""

    name: str
    label: str
    options: tuple[tuple[str, str], ...] = ()
    required: bool = False
    placeholder: str = ""
    initial_value: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("WidgetCombobox requires a non-empty name")


@dataclass(frozen=True, slots=True)
class TagsField:
    """Free-form tag entry (`widget=tags`) — TomSelect with create + remove
    plugins. Parity with the legacy `_render_tags`."""

    name: str
    label: str
    required: bool = False
    placeholder: str = ""
    initial_value: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("TagsField requires a non-empty name")


@dataclass(frozen=True, slots=True)
class DatePickerField:
    """Flatpickr date/datetime picker (`widget=picker`). Parity with the legacy
    `_render_date_picker` — `data-dz-widget="datepicker"` + a `data-dz-options`
    JSON carrying `dateFormat` (+ `enableTime` for datetime)."""

    name: str
    label: str
    is_datetime: bool = False
    required: bool = False
    placeholder: str = ""
    initial_value: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("DatePickerField requires a non-empty name")


@dataclass(frozen=True, slots=True)
class ColorField:
    """Native colour input with a live hex readout (`widget=color`). Parity
    with the legacy `_render_color` (`x-data`/`x-model` self-contained)."""

    name: str
    label: str
    required: bool = False
    initial_value: str = "#3b82f6"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ColorField requires a non-empty name")


@dataclass(frozen=True, slots=True)
class SliderField:
    """Range slider with a tooltip value readout (`widget=slider`). Parity with
    the legacy `_render_slider` — `data-dz-widget="range-tooltip"` mounts the
    dzRangeTooltip controller; `min`/`max`/`step` come from the field `extra`."""

    name: str
    label: str
    min_val: str = "0"
    max_val: str = "100"
    step: str = "1"
    required: bool = False
    initial_value: str = "50"

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SliderField requires a non-empty name")


@dataclass(frozen=True, slots=True)
class RichTextField:
    """Rich-text editor (`widget=rich_text`). Parity with the legacy
    `_render_rich_text` — a hidden input holds the HTML, `data-dz-editor`
    mounts the editor, and `data-dz-options` carries `toolbar`/`maxLength`."""

    name: str
    label: str
    required: bool = False
    initial_value: str = ""
    toolbar: str = ""
    max_length: int = 0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("RichTextField requires a non-empty name")


@dataclass(frozen=True, slots=True)
class FormStepper:
    """Wizard stage-tabs for a multi-section experience form (`widget`-free).
    Parity with the legacy `form_renderer.render_form_stepper` — an
    `<ol class="dz-form-stepper">` whose items are dzWizard-driven
    (`isActive()`/`isCurrent()`/`goToStep()` live on the surrounding
    `x-data="dzWizard"` scope). Only the experience-flow form path renders a
    stepper; the main CREATE/EDIT form path groups sections without one."""

    sections: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("FormStepper requires at least one section title")


@dataclass(frozen=True, slots=True)
class Submit:
    label: str
    variant: Literal["primary", "secondary", "danger"] = "primary"


@dataclass(frozen=True, slots=True)
class FormSection:
    """A labelled group of form fields rendered inside a FormStack.

    Issue #1031: multi-section forms previously rendered as one flat
    FormStack with no group headings. This primitive wraps a section's
    fields in a `<section class="dz-form-section">` block carrying a
    `<h3 class="dz-form-section-title">` and an optional muted-note
    paragraph (matches `components/form.html` byte-for-byte).

    The whole form remains one `<form>` — sections live INSIDE the
    FormStack, not as separate forms — so a single Submit at the
    bottom commits all fields together."""

    title: str
    fields: tuple[object, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FormSection requires at least one field")


@dataclass(frozen=True, slots=True)
class FormStack:
    """The `<form>` container — emits htmx-driven submission per the
    legacy `components/form.html` contract: `hx-post`/`hx-put` (chosen
    by `method`), `hx-target="body"`, `hx-swap="innerHTML"`. The body
    posts **form-urlencoded** (htmx's default; the `json-enc` extension
    was dropped in the htmx 4 migration), so the controller reads fields
    via `Form()`/`request.form()`, not JSON.

    `entity_name` + `mode` thread `data-dazzle-form="<entity>"` and
    `data-dazzle-form-mode="<create|edit>"` onto the `<form>` —
    contract attrs the RBAC checker (`_check_create_form` in
    `testing/ux/contract_checker.py`) keys off.

    #1494 (2c, Slice 2 — inline save-and-stay): when `peek_target` is
    set, the form is rendered inside a list-row peek panel. Instead of
    swapping the whole page on submit, it (1) appends `?peek=1` to the
    action so the API route suppresses `HX-Redirect`, (2) uses
    `hx-swap="none"` so the JSON mutation result is ignored, and (3)
    re-fetches the read-only view (`peek_view_url`) back into the panel
    cell (`peek_target`) on a successful request via a native htmx
    `hx-on:htmx:after:request` handler — no page reload, no bespoke JS
    module. Empty `peek_target` ⇒ byte-identical legacy `hx-target="body"`
    behaviour."""

    action: URL
    fields: tuple[object, ...]  # Field | Combobox | FormSection
    method: Literal["GET", "POST", "PUT"] = "POST"
    submit: Submit | None = None
    entity_name: str = ""
    mode: Literal["", "create", "edit"] = ""
    peek_target: str = ""  # CSS selector of the peek panel cell, e.g. "#peek-content-{id}"
    peek_view_url: str = ""  # read-only view URL to re-fetch after a save-and-stay

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FormStack requires at least one field")
        if self.method not in _METHODS:
            raise ValueError(f"invalid method {self.method!r}")
        if self.peek_target and self.method == "GET":
            raise ValueError("peek save-and-stay is unsupported for GET forms")
