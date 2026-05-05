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
    "datetime",
    "time",
    "textarea",
    "checkbox",
    "radio",
    "url",
    "tel",
)
_METHODS = ("GET", "POST")


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
        "datetime",
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
class Submit:
    label: str
    variant: Literal["primary", "secondary", "danger"] = "primary"


@dataclass(frozen=True, slots=True)
class FormStack:
    action: URL
    fields: tuple[object, ...]  # Field | Combobox
    method: Literal["GET", "POST"] = "POST"
    submit: Submit | None = None

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("FormStack requires at least one field")
        if self.method not in _METHODS:
            raise ValueError(f"invalid method {self.method!r}")
