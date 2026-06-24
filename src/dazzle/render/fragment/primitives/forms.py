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

    def __post_init__(self) -> None:
        if not self.options:
            raise ValueError("Combobox requires at least one option")


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
    `testing/ux/contract_checker.py`) keys off."""

    action: URL
    fields: tuple[object, ...]  # Field | Combobox | FormSection
    method: Literal["GET", "POST", "PUT"] = "POST"
    submit: Submit | None = None
    entity_name: str = ""
    mode: Literal["", "create", "edit"] = ""

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FormStack requires at least one field")
        if self.method not in _METHODS:
            raise ValueError(f"invalid method {self.method!r}")
