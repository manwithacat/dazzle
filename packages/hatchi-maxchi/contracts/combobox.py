"""HYPERPART: combobox — progressive-enhancement select contract.

Server renders a real <select data-dz-combobox> with options; the controller
enhances on first interaction. The native select remains the submit value.

Optional on the <select>:
  data-dz-focus-after-select = blur | keep | select
    blur   (default) — after a pick, blur the overlay input (committed select UX)
    keep   — keep focus for immediate re-filter typing
    select — keep focus and select-all the label (next keystroke replaces filter)
"""

import html

from pydantic import BaseModel, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="combobox",
    root="[data-dz-combobox]",
    nodes=(
        Node(
            "[data-dz-combobox]",
            attrs={"name": Present()},  # form field name required for submit
        ),
    ),
)


class ComboboxOption(BaseModel):
    value: str
    label: str


class ComboboxField(BaseModel):
    """Server-rendered seed for a combobox (pre-enhancement markup)."""

    name: str
    field_id: str
    label: str
    options: list[ComboboxOption]
    selected: str = ""
    placeholder: str = ""

    @field_validator("options", mode="before")
    @classmethod
    def _pairs(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        out = []
        for o in v:
            if isinstance(o, dict):
                out.append({"value": str(o.get("value", "")), "label": str(o.get("label", ""))})
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append({"value": str(o[0]), "label": str(o[1])})
            else:
                out.append({"value": str(o), "label": str(o)})
        return out


EXEMPLARS: list[ComboboxField] = [
    ComboboxField(
        name="priority",
        field_id="cb-priority",
        label="Priority",
        placeholder="Select…",
        selected="medium",
        options=[
            ("", "Select…"),
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
        ],
    ),
    ComboboxField(
        name="lane",
        field_id="cb-lane",
        label="Lane",
        options=[{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
        selected="a",
    ),
]


def render(field: ComboboxField) -> str:
    opts = []
    for o in field.options:
        sel = " selected" if o.value == field.selected and o.value != "" else ""
        # bare-string producer shape lands as value==label after validator
        opts.append(
            f'<option value="{html.escape(o.value, quote=True)}"{sel}>'
            f"{html.escape(o.label)}</option>"
        )
    return (
        f'<label class="dz-field" for="{html.escape(field.field_id, quote=True)}">'
        f'<span class="dz-field__label">{html.escape(field.label)}</span>'
        f'<select id="{html.escape(field.field_id, quote=True)}" '
        f'name="{html.escape(field.name, quote=True)}" data-dz-combobox '
        f'class="dz-form-input">{"".join(opts)}</select></label>'
    )


__all__ = ["DOM_CONTRACT", "ComboboxField", "ComboboxOption", "EXEMPLARS", "render"]
