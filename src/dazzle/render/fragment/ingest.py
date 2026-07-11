"""Typed ingestion boundary for HM Hyperpart seams.

Runtime copies of the HaTchi-MaXchi contract models (the wheel cannot ship
``packages/``, so no runtime import crosses the dist-only boundary). The
copies are locked to the HM contract modules by
``tests/unit/test_hm_contract_schema_parity.py`` — field-for-field schema
equality — and the emitted DOM is locked by
``tests/unit/test_hm_contract_dom_conformance.py``.

Seam models: ``GridEditCell``, ``ComboboxField``, ``TagsField``, ``MoneyField``.

Source of truth: ``packages/hatchi-maxchi/contracts/<part>.py``.
"""

from __future__ import annotations

import html as _html
import json
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

Kind = Literal["text", "date", "bool", "select"]


class GridEditCell(BaseModel):
    """One editable cell's seam data — the single canonical ingestion shape.

    Mirrors ``contracts/grid_edit.py`` (schema-parity gated). The options
    field validator is THE one normalisation boundary for the #1573 class:
    producers may hold dicts ({"value","label"}), pairs, or bare strings;
    all become pairs here — never at a consumer.
    """

    col: str
    kind: Kind
    value: str
    label: str  # a11y label for the editor
    options: list[tuple[str, str]] | None = None  # [(value, label), …] — select only

    @field_validator("options", mode="before")
    @classmethod
    def _normalise_options(cls, v: object) -> object:
        if v is None:
            return v
        out: list[tuple[str, str]] = []
        for o in v:  # type: ignore[attr-defined]
            if isinstance(o, dict):
                out.append((str(o.get("value", "")), str(o.get("label", ""))))
            elif isinstance(o, (tuple, list)) and len(o) >= 2:
                out.append((str(o[0]), str(o[1])))
            else:
                out.append((str(o), str(o)))
        return out

    @model_validator(mode="after")
    def _select_requires_options(self) -> GridEditCell:
        if self.kind == "select" and not self.options:
            raise ValueError("kind='select' requires options")
        if self.kind != "select" and self.options:
            raise ValueError(f"kind={self.kind!r} must not carry options")
        return self


def edit_span_attrs(cell: GridEditCell) -> str:
    """The ONLY place in src/dazzle that assembles data-dz-edit-* attributes
    (gated by test_hm_contract_dom_conformance.py::test_typed_path_is_sole_emitter)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f' data-dz-edit-options="{_html.escape(pairs, quote=True)}"'
    return (
        f'data-dz-grid-edit="{_html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{_html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{_html.escape(cell.label, quote=True)}"{opts}'
    )


# ── Combobox / tags / money seam copies ──────────────────────────────
# Mirrors packages/hatchi-maxchi/contracts/{combobox,tags,money}.py.
# Name collision note: dazzle.render.fragment.TagsField / MoneyField are
# form *primitives* (dataclasses). These Pydantic seam models are only
# importable as dazzle.render.fragment.ingest.TagsField / MoneyField.


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


class TagsField(BaseModel):
    name: str
    field_id: str
    label: str
    tags: list[str] = []
    placeholder: str = ""

    @field_validator("tags", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return v


class MoneyField(BaseModel):
    name: str
    currency: str = "GBP"
    scale: int = 2
    major_display: str = "0.00"
    minor_value: int = 0
    field_id: str = "money-field"
